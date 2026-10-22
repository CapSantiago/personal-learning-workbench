"""Real Caddy TLS/HTTP/WebSocket verification, plus narrow rollback checks."""
import asyncio
import copy
import hashlib
import http.client
import importlib
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import os
import queue
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
import uvicorn
from websockets.sync.client import connect
from plw.private_auth import PrivateAccess,password_hash

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import native_https_config as conf
import rollback_native_https as recovery
import install_native_https as installer
import prepare_native_https_resume as resume

CADDY=ROOT/'.sandbox/native-https-vendor-2.11.7/caddy.exe'
OPENSSL=Path(r'E:\Git\usr\bin\openssl.exe')
HOST='study.example.test'
ORIGIN='https://'+HOST
PASSWORD='Native-proxy-synthetic-2026'


def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def test_baseline_accepts_only_original_private_proxy():
    expected={'TCP':{'443':{'HTTPS':True}},'Web':{conf.HOST+':443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8501'}}}}}
    assert conf.is_original(expected)
    for mutate in (
        lambda x:x.update(AllowFunnel={conf.HOST+':443':True}),
        lambda x:x['Web'][conf.HOST+':443']['Handlers']['/'].update(Proxy='http://127.0.0.1:9999'),
        lambda x:x['TCP'].update({'80':{'HTTP':True}}),
        lambda x:x.update(Foreground={'other':{}})):
        changed=copy.deepcopy(expected);mutate(changed);assert not conf.is_original(changed)
    final=conf.config()
    assert 'bind 100.104.174.9' in final and 'get_certificate tailscale' in final
    assert 'protocols h1 h2' in final and 'admin off' in final
    assert 'plw-native-probe' not in final and ':80' not in final


def test_control_endpoint_rejects_control_from_tailnet(monkeypatch):
    monkeypatch.setattr(installer,'IP','127.0.0.2');monkeypatch.setattr(installer,'PORT',free_port())
    servers,actions,events=installer.serve_control(b'synthetic','token',['127.0.0.2'])
    try:
        # Bound source is deliberately different from loopback-only 127.0.0.1.
        client=http.client.HTTPConnection('127.0.0.2',installer.PORT,source_address=('127.0.0.2',0),timeout=2)
        client.request('POST','/control/token',body='stage')
        try:assert client.getresponse().status==403
        except (ConnectionAbortedError,ConnectionResetError,http.client.RemoteDisconnected):
            # Windows may reset a rejected POST with unread bytes. It still
            # must never enqueue the external control action.
            pass
        finally:client.close()
        assert actions.empty()
        client=http.client.HTTPConnection('127.0.0.1',installer.PORT,timeout=2)
        client.request('POST','/control/token',body='stage');assert client.getresponse().status==200;client.close()
        assert actions.get_nowait()=='stage'
    finally:
        for server in servers:server.shutdown();server.server_close()


@pytest.fixture(scope='module')
def gateway(tmp_path_factory):
    assert CADDY.is_file() and OPENSSL.is_file()
    work=tmp_path_factory.mktemp('native-https');crt=work/'test.crt';key=work/'test.key'
    subprocess.run([str(OPENSSL),'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-subj','/CN='+HOST,'-addext','subjectAltName=DNS:'+HOST+',IP:127.0.0.1',
        '-keyout',str(key),'-out',str(crt)],check=True,capture_output=True,timeout=15)
    async def app(scope,receive,send):
        if scope['type']=='websocket':
            await receive();await send({'type':'websocket.accept'})
            message=await receive()
            await send({'type':'websocket.send','text':message.get('text','')})
            await send({'type':'websocket.close','code':1000});return
        body=b'%PDF-'+b'courseware'*1048576
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/pdf'),(b'content-length',str(len(body)).encode()),(b'content-encoding',b'identity')]})
        await send({'type':'http.response.body','body':body})
    gate=PrivateAccess(app,username='student',password_digest=password_hash(PASSWORD),origin=ORIGIN)
    backend=free_port();front=free_port()
    server=uvicorn.Server(uvicorn.Config(gate,host='127.0.0.1',port=backend,log_level='error',lifespan='off'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    assert server.started
    path=work/'Caddyfile'
    native=conf.config(front,bind='127.0.0.1',host=HOST,upstream='127.0.0.1:'+str(backend))
    # Test-only trust anchor passed directly to clients; never install a CA.
    native=native.replace('tls {\n        get_certificate tailscale\n    }',f'tls "{crt.as_posix()}" "{key.as_posix()}"')
    path.write_text(native)
    subprocess.run([str(CADDY),'validate','--config',str(path),'--adapter','caddyfile'],check=True,capture_output=True,timeout=12)
    log=(work/'caddy.log').open('wb')
    process=subprocess.Popen([str(CADDY),'run','--config',str(path),'--adapter','caddyfile'],stdout=log,stderr=log)
    context=ssl.create_default_context(cafile=str(crt))
    def request(url,method='GET',body=None,headers=None):
        client=http.client.HTTPSConnection('127.0.0.1',front,context=context,timeout=10)
        client.request(method,url,body=body,headers={'Host':HOST,**(headers or {})})
        response=client.getresponse();result=(response.status,dict(response.getheaders()),response.read());client.close();return result
    try:
        for _ in range(100):
            try:
                if request('/plw-auth/login')[0]==200:break
            except OSError:pass
            time.sleep(.05)
        else:raise AssertionError((work/'caddy.log').read_text())
        yield front,context,request
    finally:
        process.terminate();process.wait(timeout=10);log.close();server.should_exit=True;thread.join(5)


def login(request):
    status,headers,body=request('/plw-auth/login');assert status==200
    csrf=re.search(rb'name="csrf" value="([^"]+)"',body)[1].decode()
    # Preserve the login CSRF cookie, if this implementation sets one.
    cookies=headers.get('Set-Cookie','').split(';')[0]
    status,headers,_=request('/plw-auth/login','POST',urlencode({'username':'student','password':PASSWORD,'csrf':csrf}),
        {'Content-Type':'application/x-www-form-urlencoded','Origin':ORIGIN,'Cookie':cookies})
    assert status==303
    return headers['Set-Cookie'].split(';')[0]


def test_real_caddy_tls_auth_cross_origin_and_complete_pdf(gateway):
    _,_,request=gateway
    assert request('/private.pdf')[0] in (303,401)
    assert request('/private.pdf',headers={'Origin':'https://evil.example'})[0]==403
    cookie=login(request)
    status,headers,body=request('/private.pdf',headers={'Cookie':cookie,'Origin':ORIGIN,'X-Forwarded-Proto':'http'})
    assert status==200 and body==b'%PDF-'+b'courseware'*1048576
    assert headers.get('Content-Encoding')=='identity'
    assert request('/private.pdf',headers={'Cookie':cookie,'Sec-Fetch-Site':'cross-site'})[0]==403


def test_real_caddy_preserves_authenticated_websocket(gateway):
    front,context,request=gateway;cookie=login(request)
    raw=socket.create_connection(('127.0.0.1',front),timeout=5)
    with connect('wss://'+HOST+':'+str(front)+'/ws',sock=raw,ssl=context,origin=ORIGIN,
                 additional_headers={'Cookie':cookie},proxy=None,open_timeout=5) as ws:
        ws.send('synthetic annotation round trip');assert ws.recv()=='synthetic annotation round trip'


def test_production_configuration_validates_with_pinned_caddy(tmp_path):
    for port in (443,19444):
        path=tmp_path/('Caddyfile-'+str(port))
        path.write_text(conf.config(port,probe_path='/plw-native-probe/synthetic'))
        result=subprocess.run([str(CADDY),'validate','--config',str(path),'--adapter','caddyfile'],capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stderr


def test_rollback_does_not_overwrite_someone_elses_443(tmp_path,monkeypatch):
    baseline={'TCP':{'443':{'HTTPS':True}},'Web':{conf.HOST+':443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8501'}}}}}
    (tmp_path/'serve-before.json').write_text(json.dumps(baseline));calls=[]
    monkeypatch.setattr(recovery,'ROOT',str(tmp_path))
    def run(args):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,stdout=json.dumps({'TCP':{'443':{'TCPForward':'another-service'}}}))
    monkeypatch.setattr(recovery,'run',run)
    with pytest.raises(RuntimeError,match='another client'):recovery.rollback()
    assert len(calls)==1 and calls[0]==['tailscale','serve','status','--json']


def test_accepted_guard_never_rolls_back(tmp_path,monkeypatch):
    (tmp_path/'accepted.json').write_text('{"native_https_active":true,"client_download_verified":true}');monkeypatch.setattr(recovery,'ROOT',str(tmp_path))
    monkeypatch.setattr(recovery,'run',lambda *_:pytest.fail('Accepted deployment must not be changed'))
    assert recovery.rollback(guard=True)=={'accepted':True,'rollback_needed':False}


def test_rollback_releases_native_socket_before_restoring_known_root(tmp_path,monkeypatch):
    baseline={'TCP':{'443':{'HTTPS':True}},'Web':{conf.HOST+':443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8501'}}}}}
    (tmp_path/'serve-before.json').write_text(json.dumps(baseline))
    monkeypatch.setattr(recovery,'ROOT',str(tmp_path));state={'config':None,'calls':[],'native_stopped':False}
    native=socket.socket();native.bind(('127.0.0.1',0));native.listen()
    occupied_port=native.getsockname()[1]
    def run(args):
        state['calls'].append(args)
        if args==['tailscale','serve','--bg','--https=443','http://127.0.0.1:8501']:
            assert state['native_stopped']
            # A real occupied socket proves the listener must be released,
            # rather than treating the old/new port collision as hypothetical.
            with socket.socket() as restored:
                restored.bind(('127.0.0.1',occupied_port));restored.listen()
            state['config']=copy.deepcopy(baseline)
        return subprocess.CompletedProcess(args,0,stdout=json.dumps(state['config']))
    monkeypatch.setattr(recovery,'run',run)
    def systemctl(args,**_):
        if args[:3]==['systemctl','disable','--now']:
            native.close();state['native_stopped']=True
        return subprocess.CompletedProcess(args,3 if 'is-active' in args or 'is-enabled' in args else 0)
    monkeypatch.setattr(recovery.subprocess,'run',systemctl)
    try:result=recovery.rollback()
    finally:native.close()
    assert result=={'original_private_https_restored':True,'native_proxy_active':False,'native_proxy_enabled':False}
    assert ['tailscale','serve','reset'] not in state['calls']
    assert state['config']==baseline


@pytest.mark.parametrize('scenario',['success','interface_suffix','off_null','client_abort','off_response_lost','unknown_listener'])
def test_staged_installer_keeps_old_route_until_verified_and_arms_rollback(tmp_path,monkeypatch,scenario):
    baseline={'TCP':{'443':{'HTTPS':True}},'Web':{conf.HOST+':443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8501'}}}}}
    state={'serve':copy.deepcopy(baseline),'calls':[],'rollback':False};messages=[]
    fake_unit=tmp_path/'unit.service'
    monkeypatch.setattr(installer,'ROOT',str(tmp_path))
    monkeypatch.setattr(installer,'Path',lambda value:fake_unit if str(value)=='/etc/systemd/system/'+conf.SERVICE else Path(value))
    monkeypatch.setattr(installer,'IP','127.0.0.1')
    monkeypatch.setattr(installer,'PORT',free_port());monkeypatch.setattr(installer,'TEST_PORT',free_port())
    monkeypatch.setattr(installer,'sys',SimpleNamespace(platform='linux'))
    monkeypatch.setattr(installer,'os',SimpleNamespace(geteuid=lambda:0,environ=os.environ,replace=os.replace,chmod=os.chmod))
    monkeypatch.setattr(installer,'CLIENT_IPS',['100.87.108.3'])
    monkeypatch.setattr(installer,'emit',lambda kind,value:messages.append((kind,value)))
    monkeypatch.setattr(installer,'local_login',lambda _:True)
    # Model the real Serve kernel listener, which the first installer missed.
    monkeypatch.setattr(installer,'binding_available',lambda port:not(port==443 and bool(state['serve'])))
    actions=queue.Queue()
    for action in (['abort'] if scenario=='client_abort' else ['stage','accept','finish']):actions.put(action)
    monkeypatch.setattr(installer,'serve_control',lambda *_:([],actions,[]))
    def command(args,**_):
        state['calls'].append(args)
        if args==['tailscale','serve','status','--json']:return json.dumps(state['serve'])
        if args[:2]==['docker','inspect']:return 'plw:0.3.1-device-library-20261021-r2'
        if args[-1:] == ['list-modules']:return 'tls.get_certificate.tailscale'
        if args==['ss','-H','-ltnp']:
            pid=9999 if scenario=='unknown_listener' else 2468
            zone='%tailscale0' if scenario=='interface_suffix' else ''
            return f'LISTEN 0 128 127.0.0.1{zone}:443 0.0.0.0:* users:(("tailscaled",pid={pid},fd=7))'
        if args==['systemctl','show','--property=MainPID','--value','tailscaled.service']:return '2468'
        if args==['systemctl','start',conf.SERVICE]:assert not state['serve'], 'Old kernel listener must release 443 before Caddy starts'
        if args==['tailscale','serve','--https=443','off']:
            assert any(call[0]=='systemd-run' for call in state['calls'])
            state['serve']=None if scenario=='off_null' else {}
            if scenario=='off_response_lost':raise RuntimeError('lost off response')
        return ''
    monkeypatch.setattr(installer,'command',command)
    class Process:
        ended=False
        def poll(self):return 0 if self.ended else None
        def terminate(self):self.ended=True
        def wait(self,timeout):return 0
    monkeypatch.setattr(installer,'subprocess',SimpleNamespace(Popen=lambda *a,**kw:Process(),DEVNULL=subprocess.DEVNULL,TimeoutExpired=subprocess.TimeoutExpired))
    def rollback():state['rollback']=True;state['serve']=baseline;return {'restored':True}
    monkeypatch.setattr(installer,'rollback',rollback)
    if scenario in ('success','interface_suffix','off_null'):
        installer.main()
        assert [kind for kind,_ in messages]==['PORTS','READY','SWITCHED','FINAL','DONE']
        assert messages[0][1]['ports'][0]['state']=='current-tailscale-serve'
        assert json.loads((tmp_path/'accepted.json').read_text())['client_download_verified']
        assert not state['rollback'] and 'plw-native-probe' not in (tmp_path/'Caddyfile').read_text()
    else:
        with pytest.raises(RuntimeError):installer.main()
        assert not (tmp_path/'accepted.json').exists()
        assert state['serve']==baseline
        assert state['rollback']==(scenario=='off_response_lost')
        if scenario in ('client_abort','unknown_listener'):assert not fake_unit.exists()


def test_release_checksums_and_payload_are_exact():
    import zipfile
    releases=ROOT/'.sandbox/releases'
    archive=releases/'PLW-Native-HTTPS-20261021.zip'
    bootstrap=releases/'native-https-bootstrap-20261021.py'
    entry=(releases/'Install-PLW-Native-HTTPS-20261021.ps1').read_text(encoding='utf-8-sig')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() in bootstrap.read_text(encoding='utf-8')
    assert hashlib.sha256(bootstrap.read_bytes()).hexdigest() in entry
    assert hashlib.sha256(archive.read_bytes()).hexdigest() in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('manifest.json'))
        for name,digest in manifest.items():
            if name!='vendor':assert hashlib.sha256(z.read(name)).hexdigest()==digest
        # First package is immutable evidence, not the new resumed installer.
        for name,expected in resume.PREVIOUS.items():assert hashlib.sha256(z.read(name)).hexdigest()==expected


def test_occupied_unknown_temporary_port_is_reported_not_stopped(monkeypatch):
    calls=[]
    monkeypatch.setattr(installer,'binding_available',lambda port:port!=installer.TEST_PORT)
    def command(args):
        calls.append(args)
        assert args==['ss','-H','-ltnp']
        return f'LISTEN 0 16 {conf.IP}:{installer.TEST_PORT} 0.0.0.0:* users:(("unrelated",pid=99,fd=3))'
    monkeypatch.setattr(installer,'command',command)
    rows=installer.inspect_ports()
    assert rows[0]['state']=='free' and rows[-1]['state']=='blocked'
    assert rows[-1]['listeners'][0]['pids']==[99]
    assert len(calls)==1


def test_reusable_bind_check_does_not_request_reuseport(monkeypatch):
    options=[]
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def setsockopt(self,*args):options.append(args)
        def bind(self,address):assert address==(conf.IP,443)
    monkeypatch.setattr(installer.socket,'socket',Socket)
    assert installer.binding_available(443)
    assert options==[(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)]


@pytest.fixture
def previous_stub(tmp_path,monkeypatch):
    old=tmp_path/'old';old.mkdir()
    contents={'caddy':b'original-executable','CADDY-LICENSE':b'license','README.md':b'old-notes'}
    expected={name:hashlib.sha256(body).hexdigest() for name,body in contents.items()}
    monkeypatch.setattr(resume,'PREVIOUS',expected)
    for name,body in contents.items():(old/name).write_bytes(body)
    (old/'manifest.json').write_text(json.dumps(expected))
    return old,tmp_path/'new',contents


def test_resume_reuses_verified_binary_without_importing_old_bytecode(previous_stub):
    old,new,contents=previous_stub
    cache=old/'__pycache__';cache.mkdir();(cache/'unexpected.pyc').write_bytes(b'never execute')
    result=resume.prepare(old,new,{'install.py':b'new installer'})
    assert result['previous_folder_preserved']
    assert (new/'caddy').read_bytes()==contents['caddy']
    assert (new/'install.py').read_bytes()==b'new installer'
    assert not (new/'__pycache__').exists() and (cache/'unexpected.pyc').exists()
    for name,body in contents.items():assert (old/name).read_bytes()==body


@pytest.mark.parametrize('change',['modified_binary','progressed_attempt'])
def test_resume_rejects_changed_or_progressed_previous_attempt(previous_stub,change):
    old,new,_=previous_stub
    if change=='modified_binary':(old/'caddy').write_bytes(b'changed')
    else:(old/'serve-before.json').write_text('{}')
    with pytest.raises(RuntimeError):resume.prepare(old,new,{'install.py':b'new'})
    assert not new.exists()


@pytest.mark.parametrize('revision',['r2','r3'])
def test_resume_release_checksums_and_current_sources_are_exact(revision):
    import zipfile
    releases=ROOT/'.sandbox/releases'
    archive=releases/f'PLW-Native-HTTPS-20261021-{revision}.zip'
    bootstrap=releases/f'native-https-bootstrap-20261021-{revision}.py'
    entry=(releases/f'Resume-PLW-Native-HTTPS-20261021-{revision}.ps1').read_text(encoding='utf-8-sig')
    zh=hashlib.sha256(archive.read_bytes()).hexdigest()
    if revision=='r2':assert zh=='d376700dd0e68e82c8b3ab56aec7d00f4db6665b7c538d7c792a9f44a63f99a4'
    assert zh in bootstrap.read_text(encoding='utf-8') and zh in entry
    assert hashlib.sha256(bootstrap.read_bytes()).hexdigest() in entry
    assert '18 MB' not in entry and "'python3 -B -'" in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('payload.json'))
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
        if revision=='r3':
            for name in ('install_native_https.py','rollback_native_https.py','native_https_config.py','prepare_native_https_resume.py'):
                assert z.read(name)==(ROOT/'scripts'/name).read_bytes()


@pytest.mark.parametrize('pid_mode',['correct','wrong','missing','mixed'])
def test_actual_cloud_interface_bound_listener_keeps_strict_pid_check(monkeypatch,pid_mode):
    evidence=json.loads((ROOT/'tests/fixtures/https-port-20261021.json').read_text(encoding='utf-8'))
    raw=evidence['ss_tcp_all_listeners']['stdout']
    # This fixture is verbatim cloud output, not a reconstruction of ss columns.
    assert '100.104.174.9%tailscale0:443' in raw
    if pid_mode=='wrong':raw=raw.replace('pid=832','pid=999')
    elif pid_mode=='missing':raw=raw.replace('pid=832','process=832')
    elif pid_mode=='mixed':raw+='\nLISTEN 0 128 0.0.0.0:443 0.0.0.0:* users:(("other",pid=999,fd=4))'
    monkeypatch.setattr(installer,'binding_available',lambda port:port!=443)
    def command(args):
        if args==['ss','-H','-ltnp']:return raw
        assert args==['systemctl','show','--property=MainPID','--value','tailscaled.service']
        return evidence['tailscaled_service']['stdout'].splitlines()[0].split('=',1)[1]
    monkeypatch.setattr(installer,'command',command)
    result=installer.inspect_ports()
    assert result[0]['state']==('current-tailscale-serve' if pid_mode=='correct' else 'blocked')
    assert result[0]['listeners'][0]['address']=='100.104.174.9%tailscale0:443'
    assert all(row['state']=='free' for row in result[1:])
    assert not any('fd7a:' in row['address'] for row in result[0]['listeners'])


def test_listener_normalization_does_not_accept_another_local_address():
    assert installer.listener_rows('LISTEN 0 128 100.104.174.90%tailscale0:443 0.0.0.0:* users:(("tailscaled",pid=832,fd=28))',443)==[]
