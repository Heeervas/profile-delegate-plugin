"""Real-pipe deadline, framing and backpressure regressions (no Hermes required)."""
import json
import select
import subprocess
import sys
import time

import pytest

from tui_rpc import TuiRpcClient, TuiProtocolError, TuiTransportError


def child(code):
    return subprocess.Popen([sys.executable, '-u', '-c', code], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                            start_new_session=True)


@pytest.mark.parametrize('payload,cap,error', [(b'{', 64, TuiTransportError), (b'x'*65, 64, TuiProtocolError)])
def test_partial_deadline_and_bound(payload, cap, error):
    p = child(f'import os,time;os.write(1,{payload!r});time.sleep(1)')
    c = TuiRpcClient(p, max_frame_bytes=cap)
    start = None
    try:
        assert select.select([p.stdout], [], [], 2)[0], 'producer did not publish bytes'
        start = time.monotonic()
        with pytest.raises(error):
            c.read_frame(.1)
        assert time.monotonic()-start < .35
    finally:
        c.close(grace=.01)
    assert p.poll() is not None
    assert p.stdout.closed and p.stderr.closed


def test_fragment_preserved_utf8_and_concatenated_frames():
    raw = (json.dumps({'jsonrpc':'2.0','id':1,'result':{'text':'é'}}, ensure_ascii=False)+'\n').encode()
    split = raw.index(b'\xc3')+1
    p = child(f'import os,time;os.write(1,{raw[:split]!r});time.sleep(.2);os.write(1,{raw[split:]+raw!r})')
    c = TuiRpcClient(p)
    try:
        with pytest.raises(TuiTransportError, match='timed out'):
            c.read_frame(.05)
        assert c.read_frame(1)['result']['text'] == 'é'
        assert c.read_frame(1)['id'] == 1
    finally:
        c.close(grace=.05)


def test_partial_eof_fails_closed():
    p = child("import os;os.write(1,b'{')")
    c = TuiRpcClient(p)
    try:
        with pytest.raises(TuiProtocolError, match='partial'):
            c.read_frame(1)
    finally:
        c.close(grace=.05)


def test_stderr_saturation_ready_and_call():
    p = child('''import os,json,sys
os.write(2,b'x'*1048576)
print(json.dumps({'jsonrpc':'2.0','method':'event','params':{'type':'gateway.ready'}}),flush=True)
r=json.loads(sys.stdin.readline())
os.write(2,b'y'*1048576)
print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':{'ok':True}}),flush=True)
''')
    c = TuiRpcClient(p, max_diagnostic_chars=128)
    try:
        c.wait_ready(2)
        assert c.call('probe', {}, timeout=2) == {'ok':True}
        assert len(c.stderr_tail) <= 128
        assert c.stderr_tail.endswith('y')
    finally:
        c.close(grace=.05)


def test_fragmented_late_response_is_discarded_once():
    p = child('''import os,json,sys,time
r=json.loads(sys.stdin.readline())
raw=(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':{}})+'\\n').encode()
os.write(1,raw[:8]);time.sleep(.15);os.write(1,raw[8:])
r=json.loads(sys.stdin.readline())
print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':{'ok':True}}),flush=True)
''')
    c = TuiRpcClient(p)
    try:
        with pytest.raises(TuiTransportError, match='timed out'):
            c.call('first', {}, timeout=.05)
        assert c.call('second', {}, timeout=1) == {'ok':True}
        assert not c._abandoned_ids
    finally:
        c.close(grace=.05)


def test_event_flood_respects_rpc_deadline():
    p = child('''import json,sys
sys.stdin.readline()
while True:
 print(json.dumps({'jsonrpc':'2.0','method':'event','params':{'type':'status.update'}}),flush=True)
''')
    c = TuiRpcClient(p)
    start = time.monotonic()
    try:
        with pytest.raises(TuiTransportError, match='timed out'):
            c.call('probe', {}, timeout=.1)
        assert time.monotonic()-start < .35
    finally:
        c.close(grace=.01)
    assert p.poll() is not None


def test_invalid_reader_bounds():
    for cap, tail in [(0, 1), (1, -1)]:
        with pytest.raises(ValueError):
            TuiRpcClient(None, max_frame_bytes=cap, max_diagnostic_chars=tail)


def test_continuous_stderr_respects_deadline():
    p = child("import os\nwhile True: os.write(2,b'x'*8192)")
    c = TuiRpcClient(p, max_diagnostic_chars=128)
    start = time.monotonic()
    try:
        with pytest.raises(TuiTransportError, match='timed out'):
            c.read_frame(.1)
        assert time.monotonic()-start < .35
        assert len(c.stderr_tail) <= 128
    finally:
        c.close(grace=.01)
