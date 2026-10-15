"""R0-only launcher. The existing M2 launcher and database are untouched."""
import argparse
import msvcrt
import os
import runpy
import socket
import sys
from probe_core import BASE,PROJECT,confined,run_root

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True)
    args=parser.parse_args();root=run_root(args.run)
    lock_path=confined(BASE/'reader.lock',BASE)
    with lock_path.open('a+b') as lock:
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit('R0 probe is already running')
        try:
            for port in [8503,8504]:
                with socket.socket() as s:
                    s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);s.bind(('127.0.0.1',port))
            os.chdir(PROJECT)
            sys.argv=['streamlit','run',str(PROJECT/'scripts/reader_probe/app.py'),
                '--server.address=127.0.0.1','--server.port=8503','--server.headless=true',
                '--browser.gatherUsageStats=false','--server.enableCORS=true','--server.enableXsrfProtection=true',
                '--server.enableStaticServing=false','--server.fileWatcherType=none','--','--run',root.name]
            runpy.run_module('streamlit',run_name='__main__')
        finally:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':main()
