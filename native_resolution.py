"""Strict, bounded read-only receiver for installed native resolution algorithms.

No SessionDB is constructed or patched. Native functions/SQL run on one snapshot;
helper and cursor errors stay sticky even when the native caller suppresses them.
"""
from contextlib import contextmanager
from pathlib import Path
import functools
import json
import sqlite3
import time
from typing import Any, NoReturn


class ResolutionError(RuntimeError):
    pass


class _Cursor:
    def __init__(self, owner, cursor, frontier=None):
        self.owner, self.cursor, self.frontier = owner, cursor, frontier

    def _read(self, method, *args):
        try:
            result = getattr(self.cursor, method)(*args)
            if result is not None:
                self.owner.bytes_read += sum(len(v.encode('utf-8')) if isinstance(v, str) else len(v) if isinstance(v, bytes) else 8 for v in result)
                if self.owner.bytes_read > 8 * 1024 * 1024:
                    self.owner.fail('native snapshot byte budget exceeded')
            if self.frontier:
                self.owner.frontiers.setdefault(self.frontier[0], []).append((self.frontier[1], result))
            return result
        except Exception as exc:
            self.owner.fail(exc)

    def fetchone(self):
        return self._read('fetchone')

    def fetchall(self):
        rows = []
        while (row := self.fetchone()) is not None:
            if len(rows) >= 1000:
                self.owner.fail('native snapshot row budget exceeded')
            rows.append(row)
        return rows

    def __iter__(self):
        return iter(self.fetchall())


class _Connection:
    def __init__(self, owner):
        self.owner = owner

    def execute(self, sql, params=()):
        owner = self.owner
        try:
            owner.check()
            if not sql.lstrip().upper().startswith('SELECT'):
                owner.fail('snapshot accepts SELECT only')
            owner.queries += 1
            if owner.queries > 2048:
                owner.fail('native snapshot query budget exceeded')
            frontier = None
            if 'JOIN sessions child ON child.parent_session_id = parent.id' in sql:
                frontier = ('compression', params[0])
            elif 'SELECT id FROM sessions AS child WHERE child.parent_session_id' in sql:
                frontier = ('resume', params[0])
            if frontier:
                # Reuse the exact native eligibility predicates; do not select a
                # competing candidate when the native LIMIT masks ambiguity.
                rows = owner.conn.execute(sql.rsplit('LIMIT 1', 1)[0], params).fetchmany(2)
                if len(rows) > 1:
                    owner.fail('ambiguous native continuation frontier')
            return _Cursor(owner, owner.conn.execute(sql, params), frontier)
        except Exception as exc:
            owner.fail(exc)


class Snapshot:
    """A request-local receiver, never the native agent's DB handle."""
    def __init__(self, home):
        from hermes_state import SessionDB
        self.native = SessionDB
        self.path = Path(home).resolve() / 'state.db'
        if not self.path.is_file() or self.path.is_symlink():
            raise ResolutionError('native state DB missing or unsafe')
        self.error = None
        self.queries = 0
        self.bytes_read = 0
        self.frontiers = {}
        self.conn = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=0.2)
        self.conn.row_factory = sqlite3.Row
        self.conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4 * 1024 * 1024)
        self.conn.execute('PRAGMA query_only=ON')
        self.conn.execute('BEGIN')
        self.deadline = time.monotonic() + 1.5
        self.conn.set_progress_handler(lambda: int(time.monotonic() > self.deadline), 1000)
        self.connection = _Connection(self)

    def fail(self, error) -> NoReturn:
        self.error = self.error or str(error)
        raise ResolutionError(self.error)

    def check(self):
        if time.monotonic() > self.deadline:
            self.fail('native snapshot deadline exceeded')
        if self.error:
            raise ResolutionError(self.error)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.conn.close()

    @contextmanager
    def _read_ctx(self):
        try:
            self.check()
            yield self.connection
        except Exception as exc:
            self.fail(exc)

    def _read_one(self, sql, params=()):
        return self.connection.execute(sql, params).fetchone()

    def _read_all(self, sql, params=()):
        return self.connection.execute(sql, params).fetchall()

    def get_session(self, session_id):
        # Only structural proof fields, never foreign title/cwd/history payload.
        row = self._read_one('SELECT id,parent_session_id,source,model_config,end_reason,ended_at '
                             'FROM sessions WHERE id=?', (session_id,))
        if row is None:
            return None
        row = dict(row)
        if row['model_config']:
            try:
                config = json.loads(row['model_config'])
                if not isinstance(config, dict):
                    self.fail('non-object native model config')
            except Exception as exc:
                self.fail(exc)
        return row

    def __getattr__(self, name) -> Any:
        import inspect
        descriptor = inspect.getattr_static(self.native, name, None)
        if isinstance(descriptor, (staticmethod, classmethod)):
            function = descriptor.__get__(self, self.native)
        elif callable(descriptor):
            function = functools.partial(descriptor, self)
        elif name.startswith('_') and descriptor is not None:
            return descriptor
        else:
            raise AttributeError(name)

        @functools.wraps(function)
        def bound(*args, **kwargs):
            try:
                self.check()
                return function(*args, **kwargs)
            except Exception as exc:
                self.fail(exc)
        return bound

    def resolve(self, session_id, *, compression_only=False):
        function = self.get_compression_tip if compression_only else self.resolve_resume_session_id
        result = function(session_id)
        self.check()
        for steps in self.frontiers.values():
            ids = [sid for sid, _row in steps]
            if len(ids) != len(set(ids)) or not steps or steps[-1][1] is not None:
                self.fail('native continuation walk lacks terminal no-child proof')
        if 'compression' not in self.frontiers or (not compression_only and 'resume' not in self.frontiers):
            self.fail('native resolver did not execute the verified frontier seams')
        if not isinstance(result, str) or not result:
            self.fail('native resolver returned no durable identity')
        return result

    def ancestry(self, session_id):
        ids = self._resume_lineage_ids(session_id)
        self.check()
        if not ids or len(ids) >= 100 or len(ids) != len(set(ids)) or ids[-1] != session_id:
            self.fail('incomplete native history ancestry')
        # Native loop breaks at a repeated parent; that is not terminal proof.
        first = self.get_session(ids[0])
        if first and self._is_compression_child_row(first):
            self.fail('native ancestry stopped before a terminal boundary')
        return tuple(ids)


def resolve(home, session_id, *, compression_only=False):
    with Snapshot(home) as receiver:
        return receiver.resolve(session_id, compression_only=compression_only)
