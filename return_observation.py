"""Bounded, live-only native receipt/containing-turn evidence. Never dispatches work."""
from __future__ import annotations

import hashlib
import json
import time
from contextlib import closing
from pathlib import Path

MAX_ROWS = 20_000
MAX_BYTES = 8 * 1024 * 1024
MAX_FRAMES = 256


class UncertainReturn(ValueError):
    """Missing or contradictory evidence cannot retire a child obligation."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ReturnObservation:
    """One coordinator owns this ephemeral cursor; native DB remains authoritative."""

    def __init__(self, home, session_id, ui_id, epoch, deadline, *, cursor=0, unpersisted_new=False):
        self.path = Path(home) / 'state.db'
        self.session_id, self.ui_id, self.epoch = session_id, ui_id, epoch
        self.deadline = deadline
        self.identity = self.file_identity()
        self.rows, self.cursors, self.uids = {}, {}, {}
        self.frames, self.sequences, self.joins = {}, {}, {}
        self.typed_receipts = {}
        self.retained_bytes = 0
        if type(cursor) is not int or cursor < 0 or not epoch:
            raise UncertainReturn('native startup cursor/epoch unavailable')
        self.last_seq = cursor
        self.segments = {session_id}
        self.latest_complete = None
        self.settled = False
        self.latest_started = False
        self.refresh(allow_unpersisted=unpersisted_new)
        self.baseline = set(self.uids)

    def file_identity(self):
        if self.path.is_symlink() or time.monotonic() >= self.deadline:
            raise UncertainReturn('native DB unavailable/deadline')
        info = self.path.stat()
        return info.st_dev, info.st_ino

    def read_rows(self, db, segment):
        cursor = self.cursors.get(segment, 0)
        while True:
            page = db.get_messages(segment, include_inactive=True, after_id=cursor, limit=128)
            if not page:
                break
            for row in page:
                self.retain(segment, row)
                if type(row.get('id')) is not int or row['id'] <= cursor:
                    raise UncertainReturn('native row cursor regression')
                cursor = row['id']
            self.cursors[segment] = cursor
        # Metadata can be stamped after insertion and even after complete.
        # Re-read retained addresses via the raw native getter, never display history.
        for address in [a for a in self.rows if a[0] == segment]:
            page = db.get_messages(segment, include_inactive=True, after_id=address[1] - 1, limit=1)
            if not page or page[0].get('id') != address[1]:
                raise UncertainReturn('native addressed row disappeared')
            self.retain(segment, page[0])

    def retain(self, segment, row):
        from agent.message_metadata import message_uid_or_none
        uid = message_uid_or_none(row)
        if not uid:
            raise UncertainReturn('native row UID missing')
        address = segment, row['id']
        immutable = digest({k: row.get(k) for k in ('role', 'content', 'tool_calls', 'tool_call_id')})
        prior = self.rows.get(address)
        if prior and (prior[0], prior[1]) != (uid, immutable):
            raise UncertainReturn('native occurrence changed')
        if uid in self.uids and self.uids[uid] != immutable:
            raise UncertainReturn('native UID conflicts')
        self.bind_typed_receipt(uid, row, prior[2] if prior else {})
        self.uids[uid] = immutable
        self.retained_bytes += len(json.dumps(row, ensure_ascii=False).encode())
        if prior:
            self.retained_bytes -= len(json.dumps(prior[2], ensure_ascii=False).encode())
        if self.retained_bytes > MAX_BYTES:
            raise UncertainReturn('native byte evidence cap')
        self.rows[address] = uid, immutable, row
        if len(self.rows) > MAX_ROWS:
            raise UncertainReturn('native row evidence cap')

    def bind_typed_receipt(self, uid, row, prior):
        """Separate occurrence typing transitions from UID-wide typed consistency."""
        metadata = row.get('display_metadata')
        child = metadata.get('delegation_id') if isinstance(metadata, dict) else None
        typed = row.get('display_kind') == 'async_delegation_complete'
        binding = (child, digest(row.get('content'))) if typed and isinstance(child, str) and child else None
        # An older clone may have always been untyped. Only a previously typed
        # occurrence loses evidence when it becomes untyped; a UID is not a row.
        prior_metadata = prior.get('display_metadata')
        prior_child = prior_metadata.get('delegation_id') if isinstance(prior_metadata, dict) else None
        if (binding is None and prior.get('display_kind') == 'async_delegation_complete'
                and isinstance(prior_child, str) and prior_child):
            raise UncertainReturn('conflicting typed native receipt')
        if binding is not None:
            if uid in self.typed_receipts and self.typed_receipts[uid] != binding:
                raise UncertainReturn('conflicting typed native receipt')
            self.typed_receipts[uid] = binding

    def refresh(self, *, allow_unpersisted=False):
        from hermes_state import SessionDB
        if self.file_identity() != self.identity:
            raise UncertainReturn('native DB generation changed')
        before = self.file_identity()
        with closing(SessionDB(self.path, read_only=True)) as db:
            lineage = db.get_compression_lineage(self.session_id)
            # A native new draft has no row until its first prompt. Only the
            # pre-submission baseline may be empty; subsequent reads stay strict.
            if allow_unpersisted and not lineage and db.get_session(self.session_id) is None:
                lineage = [self.session_id]
            if self.session_id not in lineage or len(lineage) > MAX_ROWS:
                raise UncertainReturn('native lineage incomplete')
            for segment in lineage[:lineage.index(self.session_id) + 1]:
                if time.monotonic() >= self.deadline:
                    raise UncertainReturn('native return deadline')
                self.read_rows(db, segment)
        if self.file_identity() != before:
            raise UncertainReturn('native DB replaced during observation')

    def retain_sequence(self, params):
        """Return false only for an identical frame already seen in this epoch."""
        seq = params.get('seq')
        if type(seq) is not int:
            raise UncertainReturn('native sequence missing')
        signature = digest(params)
        if seq in self.sequences:
            if self.sequences[seq] != signature:
                raise UncertainReturn('conflicting native sequence')
            return False
        if self.last_seq is not None and seq != self.last_seq + 1:
            raise UncertainReturn('native stream gap')
        self.last_seq = seq
        self.sequences[seq] = signature
        if len(self.sequences) > MAX_ROWS:
            raise UncertainReturn('native frame evidence cap')
        return True

    def continue_session(self, proposed):
        """Accept only a native-proven forward compression edge, preserving baseline."""
        if proposed == self.session_id:
            return
        if __package__:
            from .core import compression_continuation
        else:
            from core import compression_continuation
        if not compression_continuation(self.path.parent, self.session_id, proposed, ui_correlated=True):
            raise UncertainReturn('native parent identity changed')
        self.session_id = proposed
        self.segments.add(proposed)

    def event(self, params):
        if params.get('session_id') != self.ui_id or not self.retain_sequence(params):
            return False
        seq = params['seq']
        kind, payload = params.get('type'), params.get('payload') or {}
        if kind == 'message.start':
            self.settled = False
            self.latest_started = True
        elif kind == 'message.complete':
            if len(self.frames) >= MAX_FRAMES:
                raise UncertainReturn('native completed frame cap')
            self.frames[seq] = payload
            self.latest_complete, self.settled = seq, False
            self.latest_started = False
        elif kind == 'session.info' and self.latest_complete is not None:
            self.continue_session(payload.get('stored_session_id'))
            self.settled = payload.get('running') is False and not self.latest_started
        return True

    def addressed_turn(self, payload):
        """Validate the native committed address envelope before occurrence lookup."""
        receipt = payload.get('persisted_turn')
        if payload.get('status') != 'complete' or not isinstance(receipt, dict) or receipt.get('complete') is not True:
            return None
        ids = receipt.get('row_ids')
        if (not isinstance(ids, list) or len(ids) < 2 or any(type(v) is not int for v in ids)
                or ids != sorted(set(ids)) or ids[0] != receipt.get('user_row_id')
                or ids[-1] != receipt.get('final_assistant_row_id')):
            raise UncertainReturn('invalid containing-turn addresses')
        addressed = self.lookup_addresses(ids)
        if any(value is None for value in addressed):
            return None
        return addressed

    def lookup_addresses(self, ids):
        """Native row IDs are DB-global; never choose between conflicting segments."""
        addressed = []
        for rid in ids:
            matches = [value for (segment, row_id), value in self.rows.items() if row_id == rid]
            if len(matches) > 1:
                raise UncertainReturn('ambiguous native row address')
            addressed.append(matches[0] if matches else None)
        return addressed

    def containing_child(self, payload):
        addressed = self.addressed_turn(payload)
        if addressed is None:
            return None
        user, final = addressed[0], addressed[-1]
        if any(not value[2].get('active') for value in addressed):
            raise UncertainReturn('inactive containing-turn member')
        urow, frow = user[2], final[2]
        if urow.get('display_kind') != 'async_delegation_complete':
            return None
        valid = all((user[0] not in self.baseline, final[0] not in self.baseline,
                     urow.get('role') == 'user', frow.get('role') == 'assistant',
                     not frow.get('tool_calls'), frow.get('content') == payload.get('text')))
        if not valid:
            raise UncertainReturn('stale/inactive/conflicting native return')
        if sum(v[2].get('role') == 'user' for v in addressed) != 1:
            raise UncertainReturn('ambiguous native receipt membership')
        metadata = urow.get('display_metadata')
        child = metadata.get('delegation_id') if isinstance(metadata, dict) else None
        if not isinstance(child, str) or not child:
            return None
        return child, user[0], digest(urow.get('content'))

    def joined(self, required):
        self.refresh()
        anchors = {}
        for seq, payload in self.frames.items():
            turn = self.addressed_turn(payload)
            if turn is not None:
                anchor, final = turn[0][0], turn[-1][0]
                if anchor in anchors and anchors[anchor] != final:
                    raise UncertainReturn('ambiguous repeated containing turn')
                anchors[anchor] = final
            found = self.containing_child(payload)
            if found is None or found[0] not in required:
                continue
            child, uid, body = found
            previous = self.joins.get(child)
            if previous and previous['body_digest'] != body:
                raise UncertainReturn('conflicting repeated child receipt')
            if not previous:
                self.joins[child] = {'seq': seq, 'receipt_uid': uid, 'body_digest': body}
        latest = self.frames.get(self.latest_complete, {})
        current_turn = self.addressed_turn(latest)
        current_valid = current_turn is not None and all(v[2].get('active') for v in current_turn)
        return self.settled and current_valid and required.issubset(self.joins)
