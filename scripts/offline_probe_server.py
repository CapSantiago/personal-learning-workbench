"""Test-only socket guard, local to this Python process. No firewall/config changes.

It exercises this app's Python networking and is not a general OS network sandbox.
Browser network requests are independently guarded by the Playwright smoke test.
"""
from __future__ import annotations
import ipaddress
import json
from pathlib import Path
import runpy
import socket
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / ".sandbox" / "offline-denied.jsonl"
LOG.parent.mkdir(exist_ok=True)
_write_lock = threading.Lock()

def check_host(host: object) -> None:
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if str(host).lower() == "localhost":
        return
    try:
        allowed = ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        allowed = False
    if not allowed:
        with _write_lock:
            with LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"blocked_host": str(host)}, ensure_ascii=False) + "\n")
        raise OSError("PLW offline guard: non-loopback network denied")

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo

def guarded_connect(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        check_host(address[0])
    return _connect(sock, address)

def guarded_connect_ex(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        check_host(address[0])
    return _connect_ex(sock, address)

def guarded_getaddrinfo(host, *args, **kwargs):
    check_host(host)
    return _getaddrinfo(host, *args, **kwargs)

socket.socket.connect = guarded_connect
socket.socket.connect_ex = guarded_connect_ex
socket.getaddrinfo = guarded_getaddrinfo
sys.argv[0] = "streamlit"
runpy.run_module("streamlit", run_name="__main__")
