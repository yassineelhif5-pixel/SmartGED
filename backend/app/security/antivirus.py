"""ClamAV scanning over the clamd INSTREAM protocol.

If no ClamAV daemon is configured the result is ``not_configured`` — the
document is *not* reported as clean.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass
class ScanResult:
    status: str  # clean | infected | not_configured | error
    signature: str | None = None
    detail: str | None = None


def scan_file(path: Path) -> ScanResult:
    settings = get_settings()
    if not settings.clamav_host:
        return ScanResult("not_configured", detail="ClamAV host not configured")
    try:
        with socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=30) as sock:
            sock.sendall(b"zINSTREAM\0")
            with open(path, "rb") as fh:
                while chunk := fh.read(64 * 1024):
                    sock.sendall(struct.pack("!L", len(chunk)) + chunk)
            sock.sendall(struct.pack("!L", 0))
            reply = sock.recv(4096).decode(errors="replace").strip("\0\n ")
    except OSError as exc:
        return ScanResult("error", detail=str(exc))
    if reply.endswith("OK"):
        return ScanResult("clean")
    if "FOUND" in reply:
        return ScanResult("infected", signature=reply.split(":", 1)[-1].replace("FOUND", "").strip())
    return ScanResult("error", detail=reply)
