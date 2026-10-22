"""Synthetic loopback test of the exact diagnostic endpoint and curl receiver."""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import build_opener,ProxyHandler

import pytest

REPO=Path(__file__).resolve().parents[1]
FOLDER=REPO/'.sandbox/releases/PLW-Transfer-Check-20261021'
spec=importlib.util.spec_from_file_location('transfer_check',FOLDER/'transfer_server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)


@pytest.fixture
def running(monkeypatch):
    monkeypatch.setattr(server,'command',lambda *_args,**_kwargs:'')
    monkeypatch.setattr(server,'snapshot',lambda:{'monotonic':time.monotonic()})
    ready=threading.Event();records=[]
    def emit(line,**_):
        records.append(line)
        if line.startswith('PLW_TRANSFER_READY '):ready.set()
    thread=threading.Thread(target=server.serve_test,args=(['100.87.108.3'],),
        kwargs=dict(tail_ip='127.0.0.2',port=0,lifetime=12,emit=emit),daemon=True)
    thread.start();assert ready.wait(5)
    meta=json.loads(records[0].split(' ',1)[1]);opener=build_opener(ProxyHandler({}))
    try:yield meta,records,opener
    finally:
        if thread.is_alive():
            with opener.open(f"http://127.0.0.1:{meta['port']}/stop/{meta['nonce']}",timeout=3) as response:response.read()
        thread.join(5);assert not thread.is_alive()


def test_same_bytes_from_both_listeners_and_no_unscoped_download(running):
    meta,records,opener=running
    for address in ('127.0.0.1','127.0.0.2'):
        with opener.open(f"http://{address}:{meta['port']}/payload/{meta['nonce']}",timeout=3) as response:
            body=response.read();assert response.status==200
            assert response.headers['Content-Encoding']=='identity'
            assert len(body)==meta['bytes']==2097152 and hashlib.sha256(body).hexdigest()==meta['sha256']
        with pytest.raises(HTTPError) as error:opener.open(f"http://{address}:{meta['port']}/payload/wrong",timeout=3)
        assert error.value.code==404


def test_port_collision_exits_without_stopping_or_hanging_existing_listener(monkeypatch):
    monkeypatch.setattr(server,'command',lambda *_args,**_kwargs:'')
    occupied=socket.socket();occupied.bind(('127.0.0.1',0));occupied.listen()
    errors=[]
    def run():
        try:server.serve_test([],tail_ip='127.0.0.2',port=occupied.getsockname()[1],lifetime=.1)
        except OSError as error:errors.append(error)
    thread=threading.Thread(target=run,daemon=True)
    try:
        thread.start();thread.join(2);assert not thread.is_alive() and errors
        assert occupied.fileno()!=-1
    finally:occupied.close()


def test_exact_powershell_receiver_runs_curl_and_verifies_received_digest(running,tmp_path):
    meta,_,_=running
    launcher=FOLDER/'Check-PLW-Transfer.ps1'
    # Extract only the trusted measurement function, never execute its SSH body.
    code=launcher.read_text(encoding='utf-8-sig')
    function=code[code.index('function Measure-PLWRoute('):code.index("\nWrite-Host '请先")]
    script=tmp_path/'receiver.ps1'
    script.write_text('''param($Folder,$Url,$Digest)
$ErrorActionPreference='Stop'
$plwFolder=$Folder
$plwCurl='C:\\Windows\\System32\\curl.exe'
$plwRows=[Collections.Generic.List[object]]::new()
'''+function+'''
Measure-PLWRoute 'public-ssh' 1 $Url ([pscustomobject]@{bytes=2097152;sha256=$Digest})
if($plwRows.Count -ne 1 -or !$plwRows[0].complete_and_verified){throw 'Receiver verification failed'}
''',encoding='utf-8-sig')
    result=subprocess.run([r'C:\Program Files\PowerShell\7\pwsh.exe','-NoProfile','-NonInteractive','-File',str(script),
        str(tmp_path),f"http://127.0.0.1:{meta['port']}/payload/{meta['nonce']}",meta['sha256']],capture_output=True,text=True,encoding='utf-8',timeout=10)
    assert result.returncode==0,result.stderr
    report=json.loads((tmp_path/'downloads.json').read_text(encoding='utf-8-sig'))
    assert report['complete_and_verified'] and report['received_bytes']==2097152
