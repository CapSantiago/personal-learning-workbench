"""Check isolation/cleanup and the actual synthetic receiver without touching TS."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import build_opener,ProxyHandler

import pytest

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'.sandbox/releases/PLW-HTTPS-Transfer-Check-20261021'
spec=importlib.util.spec_from_file_location('https_check',ROOT/'scripts/check_https_transfer_server.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
BASE={'TCP':{'443':{'HTTPS':True}},'Web':{probe.HOST+':443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8501'}}}}}


def fake_lease(*,existing=None,change_other=False,exit_early=False):
    state={'config':copy.deepcopy(existing or BASE),'args':None,'terminated':False}
    class Process:
        def poll(self):return 1 if exit_early or state['terminated'] else None
        def terminate(self):
            state['terminated']=True
            state['config'].get('Foreground',{}).pop('owned',None)
        def wait(self,timeout):return 0
    def popen(args,**kwargs):
        state['args']=args
        state['config'].setdefault('Foreground',{})['owned']={
            'TCP':{str(probe.HTTPS_PORT):{'HTTPS':True}},
            'Web':{probe.HOST+':'+str(probe.HTTPS_PORT):{'Handlers':{'/':{'Proxy':'http://127.0.0.1:19194'}}}}}
        if change_other:state['config']['TCP']['9999']={'TCPForward':'127.0.0.1:9999'}
        return Process()
    return probe.ForegroundServe(read=lambda:copy.deepcopy(state['config']),popen=popen),state


def test_foreground_only_keeps_443_and_closes_own_session():
    lease,state=fake_lease()
    lease.start(19194)
    assert state['args']==['/usr/bin/timeout','--kill-after=3s','165s','tailscale','serve','--bg=false','--https=19443','http://127.0.0.1:19194']
    assert probe.has_port(state['config'],443)
    assert lease.close()=={'temporary_https_removed':True,'original_serve_config_unchanged':True}
    assert lease.close()==lease.cleanup


@pytest.mark.parametrize('nested',[False,True])
def test_preexisting_listener_is_not_overwritten_or_terminated(nested):
    existing=copy.deepcopy(BASE);target=existing
    if nested:target=existing.setdefault('Foreground',{}).setdefault('someone',{})
    target.setdefault('TCP',{})['19443']={'HTTPS':True}
    lease,state=fake_lease(existing=existing)
    with pytest.raises(RuntimeError,match='already configured'):lease.start(19194)
    assert state['args'] is None and not state['terminated']
    assert probe.canonical(state['config'])==probe.canonical(existing)


def test_concurrent_change_aborts_without_restoring_whole_config():
    lease,state=fake_lease(change_other=True)
    with pytest.raises(RuntimeError,match='Concurrent'):lease.start(19194)
    cleanup=lease.close()
    assert cleanup=={'temporary_https_removed':True,'original_serve_config_unchanged':False}
    assert state['config']['TCP']['9999']=={'TCPForward':'127.0.0.1:9999'}


def test_failed_cli_start_is_not_reported_as_ready():
    lease,state=fake_lease(exit_early=True)
    with pytest.raises(RuntimeError,match='failed to start'):lease.start(19194)
    # OS session closure, represented by the failed CLI disappearing.
    state['config'].get('Foreground',{}).pop('owned',None)
    assert all(lease.close().values())


def test_exact_ps_receiver_and_report_cleanup_with_real_ram_endpoint(tmp_path):
    source=(FOLDER/'transfer_base.py').read_text()
    source+='\ndef command(*args,**kwargs):return ""\ndef snapshot():return {"monotonic":time.monotonic()}\n'
    ready=threading.Event();records=[];failures=[]
    class Lease:
        port=None
        def start(self,port):self.port=port
        def close(self):return {'temporary_https_removed':True,'original_serve_config_unchanged':True}
    lease=Lease()
    def emit(line,**kwargs):
        records.append(line)
        if line.startswith('PLW_TRANSFER_READY '):ready.set()
    def run():
        try:probe.run_probe(source,['100.87.108.3'],lease=lease,emit=emit,
                           tail_ip='127.0.0.2',port=0,lifetime=12,payload_size=2097152)
        except Exception as error:failures.append(error);ready.set()
    thread=threading.Thread(target=run,daemon=True);thread.start();assert ready.wait(5)
    assert not failures
    meta=json.loads(records[0].split(' ',1)[1]);opener=build_opener(ProxyHandler({}))
    try:
        code=(FOLDER/'Check-PLW-HTTPS-Transfer.ps1').read_text(encoding='utf-8-sig')
        function=code[code.index('function Measure-PLWRoute('):code.index("\nWrite-Host '请先")]
        script=tmp_path/'receive.ps1'
        script.write_text("""param($Folder,$Url,$Digest)
$ErrorActionPreference='Stop'
$plwFolder=$Folder
$plwCurl='C:\\Windows\\System32\\curl.exe'
$plwRows=[Collections.Generic.List[object]]::new()
"""+function+"""
Measure-PLWRoute 'https-serve' 1 $Url ([pscustomobject]@{bytes=2097152;sha256=$Digest})
if($plwRows.Count -ne 1 -or !$plwRows[0].complete_and_verified){throw 'Verification failed'}
""",encoding='utf-8-sig')
        result=subprocess.run([r'C:\Program Files\PowerShell\7\pwsh.exe','-NoProfile','-NonInteractive',
            '-File',str(script),str(tmp_path),f"http://127.0.0.1:{meta['port']}/payload/{meta['nonce']}",meta['sha256']],
            capture_output=True,text=True,encoding='utf-8',timeout=10)
        assert result.returncode==0,result.stderr
        row=json.loads((tmp_path/'downloads.json').read_text(encoding='utf-8-sig'))
        assert row['complete_and_verified'] and row['received_bytes']==2097152
    finally:
        with opener.open(f"http://127.0.0.1:{meta['port']}/stop/{meta['nonce']}",timeout=3) as response:response.read()
        thread.join(5)
    assert not failures and not thread.is_alive()
    report=json.loads(next(line for line in records if line.startswith('PLW_TRANSFER_REPORT ')).split(' ',1)[1])
    assert all(report['serve_cleanup'].values()) and report['read_only'] is False
