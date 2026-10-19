"""Focused newline-delimited JSON-RPC client for Hermes TUI Gateway stdio."""
from __future__ import annotations

import io
import codecs
import json
import re
import os
import select
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Optional


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


class TuiRpcClient:
    """Single-owner synchronous RPC client with interleaved event delivery."""

    def __init__(self, process: subprocess.Popen[bytes], *, max_frame_bytes: int = 2_000_000,
                 max_diagnostic_chars: int = 100_000) -> None:
        if max_frame_bytes < 1 or max_diagnostic_chars < 0:
            raise ValueError("frame bound must be positive and diagnostic bound nonnegative")
        self.process = process
        self.max_frame_bytes = max_frame_bytes
        self.max_diagnostic_chars = max_diagnostic_chars
        self._next_id = 1
        self._writer_lock = threading.Lock()
        self._closed = False
        self._stderr_tail = ""
        self._stdout_buffer = bytearray()
        self._stderr_eof = False
        self._stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.last_event_type = "none"
        self._frame_context = "idle"
        # Single-owner client: a locally timed-out RPC may still answer later.
        # Remember that exact id so one late response can be discarded without
        # weakening correlation for any other response.
        self._abandoned_ids: set[int] = set()

    @property
    def stderr_tail(self) -> str:
        self._drain_stderr()
        return self._stderr_tail

    def _finish_stderr(self) -> None:
        if not self._stderr_eof:
            text = self._stderr_decoder.decode(b"", final=True)
            self._stderr_tail = (self._stderr_tail + text)[-self.max_diagnostic_chars:] if self.max_diagnostic_chars else ""
            self._stderr_eof = True

    def _drain_stderr(self) -> None:
        """Bound each poll so a continuous diagnostic producer cannot starve RPC."""
        stream = self.process.stderr
        if stream is None or self._stderr_eof:
            return
        try:
            for _ in range(8):
                if isinstance(stream, io.BytesIO):
                    chunk = stream.read(8192)
                else:
                    fd = stream.fileno()
                    if not select.select([fd], [], [], 0)[0]:
                        break
                    chunk = os.read(fd, 8192)
                text = self._stderr_decoder.decode(chunk, final=not chunk)
                if not chunk:
                    self._stderr_eof = True
                    self._stderr_tail = (self._stderr_tail + text)[-self.max_diagnostic_chars:] if self.max_diagnostic_chars else ""
                    break
                self._stderr_tail = (self._stderr_tail + text)[-self.max_diagnostic_chars:] if self.max_diagnostic_chars > 0 else ""
        except (OSError, ValueError):
            self._finish_stderr()

    def _readline(self, timeout: float) -> bytes:
        stream = self.process.stdout
        if stream is None:
            raise TuiTransportError("TUI stdout unavailable")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            self._drain_stderr()
            newline = self._stdout_buffer.find(b"\n")
            if newline >= 0:
                if newline + 1 > self.max_frame_bytes:
                    raise self._frame_overflow(newline + 1, exact=True)
                raw = bytes(self._stdout_buffer[:newline + 1])
                del self._stdout_buffer[:newline + 1]
                return raw
            if len(self._stdout_buffer) > self.max_frame_bytes:
                raise self._frame_overflow(len(self._stdout_buffer), exact=False)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TuiTransportError("TUI RPC response timed out")
            size = min(8192, self.max_frame_bytes + 1 - len(self._stdout_buffer))
            if isinstance(stream, io.BytesIO):
                chunk = stream.read(size)
            else:
                fd = stream.fileno()
                fds = [fd]
                if self.process.stderr is not None and not self._stderr_eof:
                    fds.append(self.process.stderr.fileno())
                ready = select.select(fds, [], [], remaining)[0]
                if fd not in ready:
                    continue
                chunk = os.read(fd, size)
            if not chunk:
                if self._stdout_buffer:
                    raise TuiProtocolError("TUI stdout EOF with partial frame")
                raise TuiTransportError("TUI stdout EOF")
            self._stdout_buffer.extend(chunk)

    def _frame_overflow(self, observed: int, *, exact: bool) -> TuiProtocolError:
        # Do not parse/log an over-limit frame: it can contain private transcript
        # text, attachments, tool arguments, or an incomplete JSON string.
        size = f"observed={observed}" if exact else f"observed>={observed}"
        return TuiProtocolError(
            f"TUI frame exceeds configured bound: configured={self.max_frame_bytes} bytes, "
            f"{size} bytes; {self._frame_context}; frame_type=unparsed. "
            "Recovery: for session.resume request omit_messages=true "
            "(inline_images=false alone only removes image data); otherwise "
            "reduce or page the emitting event/result before retrying."
        )

    def _write(self, frame: dict[str, Any]) -> None:
        """Dispatch within call's absolute deadline; partial frames poison stdin."""
        if self._closed or self.process.stdin is None or self.process.stdin.closed:
            raise TuiTransportError("TUI RPC client is closed")
        encoded = (json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        stream = self.process.stdin
        with self._writer_lock:
            if isinstance(stream, io.BytesIO):
                stream.write(encoded)
                return
            fd = stream.fileno()
            os.set_blocking(fd, False)
            written = 0
            try:
                while written < len(encoded):
                    remaining = self._dispatch_deadline - time.monotonic()
                    if remaining <= 0:
                        raise TuiTransportError(
                            f"TUI RPC dispatch timed out; {self._frame_context}; "
                            f"budget={self._dispatch_timeout}s; written={written}/{len(encoded)} bytes. "
                            "Recovery: close this transport and start a new gateway."
                        )
                    if not select.select([], [fd], [], remaining)[1]:
                        continue
                    try:
                        written += os.write(fd, memoryview(encoded)[written:])
                    except BlockingIOError:
                        continue
            except Exception as exc:
                # Never append another JSON frame to an incomplete dispatch.
                stream.close()
                if isinstance(exc, TuiTransportError):
                    raise
                raise TuiTransportError(f"TUI stdin write failed: {exc}") from exc

    def _read_raw_frame(self, timeout: float) -> dict[str, Any]:
        if self.process.stdout is None:
            raise TuiTransportError("TUI stdout unavailable")
        raw = self._readline(timeout)
        if not raw:
            self._drain_stderr()
            raise TuiTransportError("TUI stdout EOF")
        try:
            frame = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TuiProtocolError("malformed TUI JSON frame") from exc
        if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
            raise TuiProtocolError("invalid TUI JSON-RPC frame")
        return frame

    @staticmethod
    def _is_event(frame: dict[str, Any]) -> bool:
        """Classify only id-less event notifications as events."""
        return "id" not in frame and frame.get("method") == "event"

    @staticmethod
    def _validate_response(frame: dict[str, Any]) -> int:
        """Validate the strict response shape before correlating or discarding it."""
        if "method" in frame:
            raise TuiProtocolError("TUI RPC response must not include method")
        response_id = frame.get("id")
        if type(response_id) is not int:
            raise TuiProtocolError("TUI RPC response id must be an integer")
        has_result = "result" in frame
        has_error = "error" in frame
        if has_result == has_error:
            raise TuiProtocolError("TUI RPC response must contain exactly one of result or error")
        if has_result and not isinstance(frame["result"], dict):
            raise TuiProtocolError("TUI RPC result must be an object")
        if has_error:
            error = frame["error"]
            if (
                not isinstance(error, dict)
                or type(error.get("code")) is not int
                or not isinstance(error.get("message"), str)
            ):
                raise TuiProtocolError("TUI RPC error must contain integer code and string message")
        return response_id

    def read_frame(self, timeout: float) -> dict[str, Any]:
        """Read one frame, consuming only strictly valid known late responses."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TuiTransportError("TUI RPC response timed out")
            frame = self._read_raw_frame(remaining)
            response_id = frame.get("id")
            if type(response_id) is int and response_id in self._abandoned_ids:
                validated_id = self._validate_response(frame)
                self._abandoned_ids.remove(validated_id)
                continue
            return frame

    def read_event(self, timeout: float) -> dict[str, Any]:
        self._frame_context = "stage=event_polling, request_id=none"
        frame = self.read_frame(timeout)
        if not self._is_event(frame):
            response_id = self._validate_response(frame)
            raise TuiProtocolError(f"unexpected idle response id {response_id!r}")
        return frame

    def wait_ready(self, timeout: float = 15.0, *, on_event: Optional[Callable[[dict], None]] = None) -> dict:
        self._frame_context = "stage=gateway_starting, request_id=none"
        deadline = time.monotonic() + timeout
        while True:
            try:
                frame = self.read_frame(deadline - time.monotonic())
            except TuiTransportError as exc:
                if "timed out" in str(exc).lower():
                    raise TuiTransportError(
                        f"gateway_starting wait for gateway.ready timed out after {timeout:.1f}s; "
                        f"last event={self.last_event_type}"
                    ) from exc
                raise
            if self._is_event(frame):
                self.last_event_type = str((frame.get("params") or {}).get("type") or "unknown")
                if on_event:
                    on_event(frame)
                if (frame.get("params") or {}).get("type") == "gateway.ready":
                    return frame
                continue
            raise TuiProtocolError("unexpected response before gateway.ready")

    def call(self, method: str, params: dict[str, Any], *, timeout: float = 30.0,
             on_event: Optional[Callable[[dict], None]] = None,
             stage: str = "rpc_waiting") -> dict[str, Any]:
        if not method or not isinstance(params, dict):
            raise ValueError("method and object params are required")
        if timeout <= 0:
            raise TuiTransportError(f"{stage} RPC {method} timed out before dispatch")
        request_id = self._next_id
        self._next_id += 1
        self._frame_context = f"stage={stage}, request_id={request_id}, method={method}"
        deadline = time.monotonic() + timeout
        self._dispatch_deadline, self._dispatch_timeout = deadline, timeout
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            try:
                frame = self.read_frame(deadline - time.monotonic())
            except TuiTransportError as exc:
                if "timed out" in str(exc).lower():
                    self._abandoned_ids.add(request_id)
                    raise TuiTransportError(
                        f"{stage} RPC {method} timed out after {timeout:.1f}s; "
                        f"last event={self.last_event_type}"
                    ) from exc
                raise
            if self._is_event(frame):
                self.last_event_type = str((frame.get("params") or {}).get("type") or "unknown")
                if on_event:
                    on_event(frame)
                continue
            response_id = self._validate_response(frame)
            if response_id != request_id:
                raise TuiProtocolError(f"unexpected response id {response_id!r}")
            if "error" in frame:
                error = frame["error"]
                raise TuiRemoteError(error["code"], error["message"])
            return frame["result"]

    def _wait_draining(self, deadline: float) -> bool:
        """Discard stdout and retain only capped stderr while awaiting exit."""
        stdout = self.process.stdout
        stdout_eof = stdout is None
        while True:
            self._drain_stderr()
            exited = self.process.poll() is not None
            # Once reaped, stdout need not be consumed: it is intentionally
            # discarded and close() releases the pipe descriptors.
            if exited:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return exited
            if isinstance(stdout, io.BytesIO):
                stdout_eof = not stdout.read(8192)
                # In-memory process doubles have no OS readiness/reaping path.
                try:
                    self.process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    return False
                continue
            readers = []
            if stdout is not None and not stdout_eof:
                readers.append(stdout.fileno())
            if self.process.stderr is not None and not self._stderr_eof:
                readers.append(self.process.stderr.fileno())
            ready = select.select(readers, [], [], min(0.02, remaining))[0]
            if stdout is not None and not stdout_eof and stdout.fileno() in ready:
                stdout_eof = not os.read(stdout.fileno(), 8192)

    def _signal_group(self, signum, fallback):
        """Signal the owned session, falling back to its direct process."""
        try:
            os.killpg(self.process.pid, signum)
        except (ProcessLookupError, PermissionError, AttributeError):
            try:
                getattr(self.process, fallback)()
            except Exception:
                pass

    def close(self, *, grace: float = 10.0, deadline: Optional[float] = None) -> bool:
        """Close stdin and await gateway session teardown before forced reaping.

        A real Builder turn produced a complete result, then gateway teardown
        exceeded the old 2s grace and our SIGTERM made its exit -15. Keep the
        nonzero-exit safety check: if teardown exceeds this bounded reserve it
        remains a failure, rather than relabelling a killed process as success.
        Cancellation still supplies its shorter explicit deadline. Relative grace
        has a 100ms minimum signal/reap reserve; explicit deadlines are never
        extended. False means the owner must retain the child and reap obligation.
        """
        if self._closed:
            return self.process.poll() is not None
        self._closed = True

        explicit_deadline = deadline is not None
        end = deadline if deadline is not None else time.monotonic() + max(0.1, grace)
        self._stdout_buffer.clear()

        def wait_bounded(*, fraction: float = 1.0) -> bool:
            now = time.monotonic()
            return self._wait_draining(now + max(0.0, end - now) * fraction)

        try:
            try:
                if self.process.stdin is not None:
                    self.process.stdin.close()
            except Exception:
                pass
            # Every close owns one fixed budget, including signal/reap reserves.
            # Drain both pipes during each stage; wait() alone can deadlock a
            # gateway writing shutdown diagnostics larger than pipe capacity.
            if wait_bounded(fraction=0.5 if explicit_deadline else 0.8):
                return True
            for signum, fallback, fraction in (
                (signal.SIGTERM, "terminate", 0.5),
                (signal.SIGKILL, "kill", 1.0),
            ):
                self._signal_group(signum, fallback)
                if signum == signal.SIGKILL:
                    # No writer survives SIGKILL. wait() observes exit promptly;
                    # selecting on inherited pipes can consume the entire reserve.
                    try:
                        self.process.wait(timeout=max(0.0, end - time.monotonic()))
                        return True
                    except subprocess.TimeoutExpired:
                        return False
                if wait_bounded(fraction=fraction):
                    return True
            return self.process.poll() is not None
        finally:
            self._drain_stderr()
            self._finish_stderr()
            # Popen.wait() reaps the process but deliberately leaves the three
            # pipe objects open. Detached workers are short-lived, yet callers
            # and tests may create several transports in one process; close all
            # owned descriptors deterministically instead of relying on GC.
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream is not None:
                    try:
                        stream.close()
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
                  reasoning_effort: str = "", timeout: float = 60.0,
                  on_event: Optional[Callable[[dict], None]] = None) -> dict[str, str]:
    if reasoning_effort and reasoning_effort not in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
        raise TuiProtocolError("reasoning selection must be an effort level, never a display command")
    deadline = time.monotonic() + timeout
    model_value = ""
    select_after_start = mode == "resume" or bool(provider and not model)
    if select_after_start and (model or provider):
        from hermes_cli.model_switch import parse_model_switch_args
        model_value = " ".join(part for part in (model, f"--provider {provider}" if provider else "", "--session") if part)
        parsed = parse_model_switch_args(model_value)
        if (parsed.errors or parsed.model_input != model or parsed.explicit_provider != provider
                or parsed.scope != "session" or parsed.is_global or parsed.is_once or parsed.force_refresh
                or parsed.reasoning_effort):
            raise TuiProtocolError("model/provider cannot contain native command flags")
    common: dict[str, Any] = {"profile": profile, "source": "profile-delegate", "cols": 100}
    if mode == "resume":
        response = client.call(
            "session.resume", {**common, "session_id": session_id,
                               "omit_messages": True, "inline_images": False}, timeout=max(0.0, deadline - time.monotonic()),
            on_event=on_event, stage="session_creating",
        )
        durable = response.get("resumed", session_id)
    else:
        # Resume restores the stored workspace; creation-only overrides must
        # never be sent to session.resume (its installed contract forbids cwd).
        params = {**common, "cwd": cwd, "title": title, "close_on_disconnect": True}
        if model:
            params["model"] = model
        if provider:
            params["provider"] = provider
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        response = client.call(
            "session.create", params, timeout=max(0.0, deadline - time.monotonic()), on_event=on_event,
            stage="session_creating",
        )
        durable = response.get("stored_session_id", response.get("session_key", ""))
    ui_id = response.get("session_id", "")
    if (not isinstance(ui_id, str) or not isinstance(durable, str)
            or not ui_id or not durable
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", ui_id)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", durable)):
        raise TuiProtocolError("session response omitted session identity")
    if select_after_start:
        if provider and not model:
            model = (response.get("info") or {}).get("model", "")
            if not isinstance(model, str) or not model or parse_model_switch_args(model).model_input != model:
                raise TuiProtocolError("provider override requires the session model")
            model_value = f"{model} --provider {provider} --session"
        selections = ([("model", model_value)] if model_value else [])
        if reasoning_effort:
            selections.append(("reasoning", reasoning_effort))
        for key, value in selections:
            reply = client.call(
                "config.set", {"session_id": ui_id, "key": key, "value": value, "scope": "session"},
                timeout=max(0.0, deadline - time.monotonic()), on_event=on_event, stage="session_selection",
            )
            if reply.get("confirm_required"):
                raise TuiRemoteError("selection_confirmation_required", reply.get("confirm_message") or "Selection requires operator confirmation")
            if reply.get("scope") == "global":
                raise TuiProtocolError("selection returned unexpected global scope")
            # Compute-host sessions defer model switching until the next prompt.
            # Acceptance is not observed execution; no actual-model claim is made here.
    return {"ui_session_id": ui_id, "child_session_id": durable}


def submit(client: Any, session_id: str, text: str, *, timeout: float = 60.0,
           on_event: Optional[Callable[[dict], None]] = None) -> dict:
    return client.call(
        "prompt.submit", {"session_id": session_id, "text": text}, timeout=timeout,
        on_event=on_event, stage="agent_initializing",
    )


def steer(client: Any, session_id: str, text: str, *, on_event: Optional[Callable[[dict], None]] = None) -> dict:
    return client.call("session.steer", {"session_id": session_id, "text": text}, timeout=15, on_event=on_event)


def interrupt(client: Any, session_id: str, *, timeout: float = 15.0,
              on_event: Optional[Callable[[dict], None]] = None) -> dict:
    return client.call(
        "session.interrupt", {"session_id": session_id}, timeout=timeout,
        on_event=on_event,
    )
