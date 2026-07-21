"""Focused newline-delimited JSON-RPC client for Hermes TUI Gateway stdio."""
from __future__ import annotations

import json
import os
import queue
import select
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, BinaryIO, Callable, Optional


class TuiRpcError(RuntimeError):
    """Base TUI transport failure."""


class TuiProtocolError(TuiRpcError):
    """Malformed or impossible JSON-RPC traffic."""


class TuiTransportError(TuiRpcError):
    """Transport EOF, timeout, or process failure."""


class TuiRemoteError(TuiRpcError):
    def __init__(self, code: Any, message: str) -> None:
        super().__init__(f"TUI RPC error {code}: {message}")
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _readline_with_timeout(stream: BinaryIO, timeout: float) -> bytes:
    try:
        fd = stream.fileno()
    except (AttributeError, OSError):
        fd = None
    if fd is not None:
        ready, _, _ = select.select([fd], [], [], max(0.001, timeout))
        if not ready:
            raise TuiTransportError("TUI RPC response timed out")
        return stream.readline()
    result: queue.Queue[bytes | BaseException] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            result.put(stream.readline())
        except BaseException as exc:  # surfaced on the caller thread
            result.put(exc)

    thread = threading.Thread(target=read, name="profile-delegate-tui-read", daemon=True)
    thread.start()
    try:
        item = result.get(timeout=max(0.001, timeout))
    except queue.Empty as exc:
        raise TuiTransportError("TUI RPC response timed out") from exc
    if isinstance(item, BaseException):
        raise TuiTransportError(f"TUI stdout read failed: {item}") from item
    return item


class TuiRpcClient:
    """Single-owner synchronous RPC client with interleaved event delivery."""

    def __init__(self, process: subprocess.Popen[bytes], *, max_frame_bytes: int = 2_000_000,
                 max_diagnostic_chars: int = 100_000) -> None:
        self.process = process
        self.max_frame_bytes = max_frame_bytes
        self.max_diagnostic_chars = max_diagnostic_chars
        self._next_id = 1
        self._writer_lock = threading.Lock()
        self._closed = False
        self._stderr_tail = ""

    @property
    def stderr_tail(self) -> str:
        self._drain_stderr()
        return self._stderr_tail

    def _drain_stderr(self) -> None:
        stream = self.process.stderr
        if stream is None:
            return
        try:
            if isinstance(stream, __import__("io").BytesIO):
                data = stream.read()
            else:
                data = b""
                fd = stream.fileno()
                while True:
                    try:
                        chunk = os.read(fd, 8192)
                    except BlockingIOError:
                        break
                    if not chunk:
                        break
                    data += chunk
            if data:
                text = data.decode("utf-8", "replace")
                self._stderr_tail = (self._stderr_tail + text)[-self.max_diagnostic_chars:]
        except Exception:
            pass

    def _write(self, frame: dict[str, Any]) -> None:
        if self._closed or self.process.stdin is None:
            raise TuiTransportError("TUI RPC client is closed")
        encoded = (json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        with self._writer_lock:
            try:
                self.process.stdin.write(encoded)
                self.process.stdin.flush()
            except Exception as exc:
                raise TuiTransportError(f"TUI stdin write failed: {exc}") from exc

    def read_frame(self, timeout: float) -> dict[str, Any]:
        if self.process.stdout is None:
            raise TuiTransportError("TUI stdout unavailable")
        raw = _readline_with_timeout(self.process.stdout, timeout)
        if not raw:
            self._drain_stderr()
            raise TuiTransportError("TUI stdout EOF")
        if len(raw) > self.max_frame_bytes:
            raise TuiProtocolError("TUI frame exceeds configured bound")
        try:
            frame = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TuiProtocolError("malformed TUI JSON frame") from exc
        if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
            raise TuiProtocolError("invalid TUI JSON-RPC frame")
        return frame

    def wait_ready(self, timeout: float = 15.0, *, on_event: Optional[Callable[[dict], None]] = None) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            frame = self.read_frame(deadline - time.monotonic())
            if frame.get("method") == "event":
                if on_event:
                    on_event(frame)
                if (frame.get("params") or {}).get("type") == "gateway.ready":
                    return frame
                continue
            raise TuiProtocolError("unexpected response before gateway.ready")

    def call(self, method: str, params: dict[str, Any], *, timeout: float = 30.0,
             on_event: Optional[Callable[[dict], None]] = None) -> dict[str, Any]:
        if not method or not isinstance(params, dict):
            raise ValueError("method and object params are required")
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            frame = self.read_frame(deadline - time.monotonic())
            if frame.get("method") == "event":
                if on_event:
                    on_event(frame)
                continue
            if frame.get("id") != request_id:
                raise TuiProtocolError(f"unexpected response id {frame.get('id')!r}")
            if "error" in frame:
                error = frame.get("error") or {}
                raise TuiRemoteError(error.get("code"), str(error.get("message") or "unknown error"))
            result = frame.get("result")
            if not isinstance(result, dict):
                raise TuiProtocolError("TUI RPC result must be an object")
            return result

    def close(self, *, grace: float = 2.0) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
        except Exception:
            pass
        try:
            self.process.wait(timeout=grace)
            return
        except Exception:
            pass
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, AttributeError):
            try:
                self.process.terminate()
            except Exception:
                pass
        try:
            self.process.wait(timeout=grace)
            return
        except Exception:
            pass
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError):
            try:
                self.process.kill()
            except Exception:
                pass
        try:
            self.process.wait(timeout=grace)
        except Exception:
            pass


def launch_gateway(*, python: str, cwd: str, env: dict[str, str],
                   command: Optional[list[str]] = None) -> TuiRpcClient:
    proc = subprocess.Popen(
        command or [python, "-m", "tui_gateway.entry"], cwd=cwd, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True, bufsize=0,
    )
    if proc.stderr is not None:
        try:
            os.set_blocking(proc.stderr.fileno(), False)
        except (AttributeError, OSError):
            pass
    return TuiRpcClient(proc)


def start_session(client: Any, *, profile: str, mode: str, session_id: str,
                  title: str, cwd: str, model: str = "", provider: str = "",
                  reasoning_effort: str = "", on_event: Optional[Callable[[dict], None]] = None) -> dict[str, str]:
    common: dict[str, Any] = {"profile": profile, "cwd": cwd, "source": "profile-delegate", "cols": 100}
    if mode == "resume":
        response = client.call("session.resume", {**common, "session_id": session_id}, timeout=60, on_event=on_event)
        durable = str(response.get("resumed") or session_id)
    else:
        params = {**common, "title": title, "close_on_disconnect": True}
        if model:
            params["model"] = model
        if provider:
            params["provider"] = provider
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        response = client.call("session.create", params, timeout=60, on_event=on_event)
        durable = str(response.get("stored_session_id") or response.get("session_key") or "")
    ui_id = str(response.get("session_id") or "")
    if not ui_id or not durable:
        raise TuiProtocolError("session response omitted session identity")
    return {"ui_session_id": ui_id, "child_session_id": durable}


def submit(client: Any, session_id: str, text: str, *, on_event: Optional[Callable[[dict], None]] = None) -> dict:
    return client.call("prompt.submit", {"session_id": session_id, "text": text}, timeout=60, on_event=on_event)


def steer(client: Any, session_id: str, text: str, *, on_event: Optional[Callable[[dict], None]] = None) -> dict:
    return client.call("session.steer", {"session_id": session_id, "text": text}, timeout=15, on_event=on_event)


def interrupt(client: Any, session_id: str, *, on_event: Optional[Callable[[dict], None]] = None) -> dict:
    return client.call("session.interrupt", {"session_id": session_id}, timeout=15, on_event=on_event)


def wait_for_completion(events: queue.Queue[dict], session_id: str, *, timeout: float,
                        poll: Optional[Callable[[], None]] = None) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        if poll:
            poll()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TuiTransportError("delegated TUI turn timed out")
        try:
            frame = events.get(timeout=min(0.1, remaining))
        except queue.Empty:
            continue
        params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
        if params.get("session_id") != session_id:
            continue
        event_type = params.get("type")
        payload = params.get("payload") if isinstance(params.get("payload"), dict) else {}
        if event_type == "message.complete":
            return {"text": str(payload.get("text") or ""), "status": str(payload.get("status") or "complete")}
        if event_type == "error":
            raise TuiTransportError(str(payload.get("message") or "TUI turn failed"))
