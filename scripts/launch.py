"""Foreground, loopback-only PLW launcher with an OS-held per-project lock."""
from __future__ import annotations
import argparse
import msvcrt
import os
from pathlib import Path
import runpy
import socket
import sys

PROJECT = Path(__file__).resolve().parents[1]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8501)
    milestone = parser.add_mutually_exclusive_group()
    milestone.add_argument("--m0", action="store_true", help="Open the preserved synthetic M0 probe")
    milestone.add_argument("--m1", action="store_true", help="Open the preserved M1 course workbench")
    milestone.add_argument("--m2", action="store_true", help="Open the preserved M2 synthetic workbench")
    parser.add_argument('--test-workspace', help='Use an isolated .sandbox/test-runs workspace for acceptance')
    parser.add_argument("--offline-probe", action="store_true", help="Test: deny non-loopback Python socket connections")
    args = parser.parse_args()
    if args.test_workspace:
        candidate=Path(args.test_workspace)
        allowed=PROJECT/'.sandbox'/'test-runs'
        if not candidate.is_absolute() or '..' in candidate.parts or candidate==allowed or not candidate.is_relative_to(allowed):
            parser.error('test workspace must be a child of .sandbox/test-runs')
        os.environ['PLW_WORKSPACE']=str(candidate)
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    sandbox = PROJECT / ".sandbox"
    for item in [sandbox, *sandbox.parents]:
        if item.is_symlink() or item.is_junction():
            raise ValueError("The project sandbox must not contain filesystem links.")
    sandbox.mkdir(exist_ok=True)
    lock_path = sandbox / "launcher.lock"
    if lock_path.is_symlink() or lock_path.is_junction():
        raise ValueError("The lock file must not be a link.")
    if lock_path.exists() and lock_path.stat().st_nlink != 1:
        raise ValueError("The lock file must not have additional hard links.")
    with lock_path.open("a+b") as lock:
        if os.fstat(lock.fileno()).st_nlink != 1:
            raise ValueError("The opened lock file must not have additional hard links.")
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("PLW is already running for this project.", file=sys.stderr)
            return 2
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                try:
                    probe.bind(("127.0.0.1", args.port))
                except OSError:
                    print(f"Port {args.port} is unavailable. Choose another port.", file=sys.stderr)
                    return 3
            entry = PROJECT / ("app_m0.py" if args.m0 else "app_m1.py" if args.m1 else "app_m2.py" if args.m2 else "app.py")
            command = ["streamlit", "run", str(entry),
                       "--server.address=127.0.0.1", f"--server.port={args.port}", "--server.headless=true",
                       "--browser.gatherUsageStats=false", "--server.fileWatcherType=none",
                       "--server.enableCORS=true", "--server.enableXsrfProtection=true",
                       "--server.enableStaticServing=false"]
            os.chdir(PROJECT)
            try:
                if args.offline_probe:
                    sys.argv = command
                    runpy.run_path(str(PROJECT / "scripts" / "offline_probe_server.py"), run_name="__main__")
                elif not (args.m0 or args.m1 or args.m2):
                    # Streamlit 1.65 exposes a supported ASGI entry point. Reader
                    # PDFs and PDF.js now use this same address and port, so a
                    # future private website only needs one HTTPS endpoint.
                    if str(PROJECT / 'src') not in sys.path:
                        sys.path.insert(0, str(PROJECT / 'src'))
                    import streamlit as st
                    from plw.reader_runtime import reader_routes
                    st.App(str(entry), routes=reader_routes()).run(config={
                        'server.address': '127.0.0.1', 'server.port': args.port,
                        'server.headless': True, 'browser.gatherUsageStats': False,
                        'server.fileWatcherType': 'none', 'server.enableCORS': True,
                        'server.enableXsrfProtection': True, 'server.enableStaticServing': False,
                    })
                else:
                    sys.argv = command
                    runpy.run_module("streamlit", run_name="__main__")
                return 0
            except SystemExit as exc:
                return int(exc.code or 0)
            except KeyboardInterrupt:
                return 130
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

if __name__ == "__main__":
    raise SystemExit(main())
