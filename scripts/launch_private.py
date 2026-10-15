"""Private Windows/Linux entry point; one writer and protected application routes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--local-preview',action='store_true',help='Only a synthetic loopback workspace')
    parser.add_argument('--check',action='store_true',help='Read-only config and runtime preflight')
    args=parser.parse_args()
    from plw.server_config import load_profile,configure_profile
    profile=load_profile(args.config,preview=args.local_preview)
    configure_profile(profile)
    from plw import storage
    storage.safe_path(storage.PRODUCTION_ROOT,directory=True)
    storage.safe_path(storage.BACKUP_ROOT,directory=True)
    result=subprocess.run([profile['pdf_python'],'-B','-c','import pypdf; print(pypdf.__version__)'],capture_output=True,text=True,timeout=30)
    if result.returncode:raise ValueError('PDF Python 缺少 pypdf，请按服务器依赖清单准备独立环境。')
    if args.check:
        print(json.dumps({'valid':True,'origin':profile['origin'],'listener':'127.0.0.1','port':profile['port'],'platform':sys.platform,'pdf_ready':True,'data_created':False}))
        return
    from plw import platform_lock
    import streamlit as st
    from starlette.middleware import Middleware
    from plw.private_auth import PrivateAccess
    from plw.reader_runtime import reader_routes
    from plw.backup_transfer import routes as backup_routes
    from plw.cloud_health import check as health_check
    # One process for this dataset, including sessions and the SQLite writer.
    lock=Path(profile['data_root'])/'control'/'.server.lock'
    storage.safe_path(lock, directory=False)
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        platform_lock.acquire(handle)
        os.chdir(PROJECT)
        app=st.App(str(PROJECT/'app.py'),routes=reader_routes()+backup_routes(),middleware=[Middleware(PrivateAccess,
            username=profile['username'],password_digest=profile['password_digest'],origin=profile['origin'],preview=args.local_preview,health_check=health_check)])
        app.run(config={'server.address':'127.0.0.1','server.port':profile['port'],'server.headless':True,
            'browser.gatherUsageStats':False,'server.fileWatcherType':'none','server.enableCORS':True,
            'server.enableXsrfProtection':True,'server.enableStaticServing':False,'client.toolbarMode':'minimal','client.showErrorDetails':False})


if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as exc:raise SystemExit(str(exc))
