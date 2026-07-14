"""Ephemeral, default-deny code execution through a dedicated Docker daemon.

The application talks only to the private Docker-in-Docker daemon provided by
Compose. It never mounts the host Docker socket. Every call creates and then
removes a fresh container with no network, a read-only root filesystem,
no Linux capabilities, and strict CPU/memory/PID/time/output limits.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool = False
    truncated: bool = False


def _request(path: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 10):
    base = settings.SANDBOX_DOCKER_URL.rstrip("/")
    if not base.startswith("http://"):
        raise SandboxError("SANDBOX_DOCKER_URL must be an internal http:// Docker API URL.")
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base}/v1.43{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        return urlopen(request, timeout=timeout)
    except HTTPError as exc:
        detail = exc.read(2048).decode(errors="replace")
        raise SandboxError(f"Sandbox daemon returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise SandboxError(f"Sandbox daemon is unavailable: {exc}") from exc


def _ensure_image() -> None:
    encoded = quote(settings.SANDBOX_IMAGE, safe="")
    try:
        with _request(f"/images/{encoded}/json"):
            return
    except SandboxError as exc:
        if "HTTP 404" not in str(exc):
            raise
    image, separator, tag = settings.SANDBOX_IMAGE.partition(":")
    path = f"/images/create?fromImage={quote(image, safe='')}&tag={quote(tag or 'latest', safe='')}"
    with _request(path, method="POST", timeout=settings.SANDBOX_IMAGE_PULL_TIMEOUT_SECONDS) as response:
        # Consume the daemon's progress stream so the pull is complete.
        response.read()


def _decode_logs(data: bytes) -> tuple[str, str, bool]:
    stdout = bytearray()
    stderr = bytearray()
    offset = 0
    while offset + 8 <= len(data):
        stream = data[offset]
        size = int.from_bytes(data[offset + 4 : offset + 8], "big")
        start, end = offset + 8, offset + 8 + size
        if end > len(data):
            break
        (stderr if stream == 2 else stdout).extend(data[start:end])
        offset = end
    limit = settings.SANDBOX_MAX_OUTPUT_BYTES
    truncated = len(stdout) + len(stderr) > limit
    remaining = limit
    stdout = stdout[:remaining]
    remaining -= len(stdout)
    stderr = stderr[:remaining]
    return stdout.decode(errors="replace"), stderr.decode(errors="replace"), truncated


def run_python(code: str) -> SandboxResult:
    if not code.strip():
        raise SandboxError("execute_code requires non-empty code.")
    if len(code.encode("utf-8")) > settings.SANDBOX_MAX_CODE_BYTES:
        raise SandboxError("Code exceeds the configured sandbox input limit.")

    _ensure_image()
    create_payload = {
        "Image": settings.SANDBOX_IMAGE,
        "Cmd": ["python", "-I", "-c", code],
        "AttachStdout": True,
        "AttachStderr": True,
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Memory": settings.SANDBOX_MEMORY_BYTES,
            "NanoCpus": settings.SANDBOX_NANO_CPUS,
            "PidsLimit": settings.SANDBOX_PIDS_LIMIT,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=16m"},
        },
    }
    with _request("/containers/create", method="POST", payload=create_payload) as response:
        container_id = json.load(response)["Id"]

    timed_out = False
    exit_code: int | None = None
    try:
        with _request(f"/containers/{container_id}/start", method="POST", payload={}):
            pass
        try:
            with _request(
                f"/containers/{container_id}/wait?condition=not-running",
                method="POST",
                payload={},
                timeout=settings.SANDBOX_TIMEOUT_SECONDS,
            ) as response:
                exit_code = json.load(response).get("StatusCode")
        except (SandboxError, TimeoutError, socket.timeout) as exc:
            # Docker may return the chunked wait response headers immediately
            # and only time out while json.load() reads its body, so the socket
            # exceptions must be handled around the whole response context.
            if isinstance(exc, SandboxError) and "unavailable" not in str(exc):
                raise
            timed_out = True
            try:
                with _request(f"/containers/{container_id}/kill", method="POST", payload={}):
                    pass
            except SandboxError:
                pass

        with _request(f"/containers/{container_id}/logs?stdout=1&stderr=1") as response:
            raw_logs = response.read(settings.SANDBOX_MAX_OUTPUT_BYTES * 2 + 8192)
        stdout, stderr, truncated = _decode_logs(raw_logs)
        return SandboxResult(stdout, stderr, exit_code, timed_out, truncated)
    finally:
        try:
            with _request(f"/containers/{container_id}?force=1&v=1", method="DELETE"):
                pass
        except SandboxError:
            pass
