"""Exact canonical byte pages; caller owns publication lock and prior authorization."""
import base64
import hashlib
import re


def _core():
    if __package__:
        from . import core
    else:
        import core
    return core


def validate(args):
    c = _core()
    offset, limit = args.get('result_offset_bytes', 0), args.get('result_limit_bytes', 8192)
    sha = args.get('result_sha256')
    invalid = (set(args) - {'result_offset_bytes', 'result_limit_bytes', 'result_sha256'}
               or type(offset) is not int or type(limit) is not int)
    if invalid or offset < 0 or not 1 <= limit <= 8192:
        raise c.ProfileDelegateError('invalid result byte bounds', 'invalid_result_slice')
    if ('result_sha256' in args and (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha))
            or offset > 0 and sha is None):
        raise c.ProfileDelegateError('result hash required/invalid', 'invalid_result_slice')
    return offset, limit, sha


def read_slice(run_dir, status, args):
    c = _core()
    offset, limit, expected = validate(args)
    path = run_dir / 'result.json'
    if status.get('status') not in c.TERMINAL_RUN_STATUSES or not path.exists():
        raise c.ProfileDelegateError('terminal result not available', 'result_unavailable')
    candidate, raw = c._read_json_bytes(path)
    if 'result_schema_version' not in candidate:
        raise c.ProfileDelegateError('legacy result is unverified', 'result_unavailable')
    c._validate_terminal_candidate(run_dir, candidate)
    if candidate['execution_status'] != status.get('status'):
        raise c.ProfileDelegateError('conflicting terminal evidence', 'unsafe_artifact')
    sha = hashlib.sha256(raw).hexdigest()
    if expected is not None and expected != sha:
        raise c.ProfileDelegateError('canonical result changed', 'result_changed')
    if offset > len(raw):
        raise c.ProfileDelegateError('offset exceeds canonical bytes', 'invalid_result_slice')
    page = raw[offset:offset + limit]
    following = offset + len(page)
    return dict(task_id=run_dir.name, encoding='base64', offset_bytes=offset,
                length_bytes=len(page), total_bytes=len(raw), sha256=sha,
                data=base64.b64encode(page).decode('ascii'),
                next_offset_bytes=following if following < len(raw) else None,
                eof=following == len(raw), truncated=not (offset == 0 and len(page) == len(raw)))
