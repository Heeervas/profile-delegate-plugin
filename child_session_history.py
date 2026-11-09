"""Narrow request-owned history receiver; never transferred to a native agent."""
import functools
from typing import Any, cast

if __package__:
    from . import native_resolution
else:
    import native_resolution


class _HistorySnapshot(native_resolution.Snapshot):
    def __init__(self, owner):
        super().__init__(owner.pin.home)
        self.owner = owner
        # Bound decoded native cells before SQLite returns them to Python.
        import sqlite3
        self.conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4 * 1024 * 1024)

    def get_session(self, session_id):
        if session_id not in self.owner.allowed:
            self.owner.pin.fail('history attempted foreign metadata')
        return super().get_session(session_id)

    def _resume_lineage_ids(self, session_id):
        ids = self.native._resume_lineage_ids(cast(Any, self), session_id)
        if tuple(ids) != self.owner.allowed:
            self.owner.pin.fail('native history ancestry changed')
        return ids

    def _fetch_conversation_rows(self, session_ids, active_clause, *, with_session_id):
        self.owner.check()
        if not session_ids or not set(session_ids).issubset(self.owner.allowed):
            self.owner.pin.fail('native payload scope changed')
        return self.native._fetch_conversation_rows(
            cast(Any, self), session_ids, active_clause, with_session_id=with_session_id)


class History:
    PUBLIC = frozenset({'assert_resume_safe', 'get_messages_as_conversation',
                        'get_resume_conversations', 'get_ancestor_display_prefix',
                        'get_latest_todo_result'})

    def __init__(self, pin, db, check_record=None):
        self.pin, self.original, self.check_record = pin, db, check_record
        self.allowed = tuple(pin.boundary['allowed_history_ids'])
        self.db_path = db.db_path
        self._reopen = db.reopen_session

    def check(self):
        self.pin.check(self.original)
        self.pin.prehistory_ownership()
        if self.check_record is not None:
            self.check_record()

    def reopen_session(self, session_id):
        self.check()
        if session_id != self.pin.session_id:
            self.pin.fail('history attempted foreign reopen')
        return self._reopen(session_id)

    def close(self):
        return self.original.close()

    def __getattr__(self, name):
        if name not in self.PUBLIC:
            self.pin.fail('unsupported native history operation: ' + name)

        @functools.wraps(getattr(self.original, name))
        def read(session_id, *args, **kwargs):
            self.check()
            if session_id != self.pin.session_id:
                self.pin.fail('history attempted foreign durable identity')
            try:
                with _HistorySnapshot(self) as receiver:
                    result = getattr(receiver, name)(session_id, *args, **kwargs)
                    receiver.check()
                self.check()
                return result
            except Exception as exc:
                self.pin.fail(exc)
        return read
