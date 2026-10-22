"""Staged private HTTPS replacement, conditional on client download acceptance."""
import hashlib
import errno
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
from native_https_config import ROOT,SERVICE,HOST,IP,config,unit,is_original
from rollback_native_https import rollback

CLIENT_IPS=[]
PORT=19196
TEST_PORT=19444
GUARD='plw-native-https-rollback'


def command(args,timeout=20):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed: '+' '.join(args)+'; '+result.stderr[-1500:].strip())
    return result.stdout.strip()


def binding_available(port):
    """Match Go's reusable Linux TCP listener; never use SO_REUSEPORT."""
    try:
        with socket.socket() as check:
            check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            check.bind((IP,port))
        return True
    except OSError as error:
        if error.errno==errno.EADDRINUSE:return False
        raise RuntimeError(f'Cannot check {IP}:{port}: {error}') from error


def listener_rows(text,port):
    result=[]
    for line in text.splitlines():
        fields=line.split()
        if len(fields)<5:continue
        address,separator,number=fields[3].rpartition(':')
        # ss includes %interface for device-bound sockets (including IPv4).
        # Keep the raw endpoint in evidence; normalize only for address matching.
        host=address.split('%',1)[0].strip('[]')
        if separator and number==str(port) and host in (IP,'0.0.0.0','*','::'):
            result.append({'address':fields[3],'pids':[int(pid) for pid in re.findall(r'pid=(\d+)',line)]})
    return result


def inspect_ports(ports=None):
    reports=[];listeners=None;tail_pid=None
    for port in ports or (443,PORT,TEST_PORT):
        if binding_available(port):
            reports.append({'address':IP,'port':port,'state':'free'});continue
        if listeners is None:listeners=command(['ss','-H','-ltnp'])
        rows=listener_rows(listeners,port)
        if port==443:
            value=command(['systemctl','show','--property=MainPID','--value','tailscaled.service'])
            tail_pid=int(value) if value.isdecimal() else 0
        expected=(port==443 and tail_pid and rows
                  and all(row['pids'] and set(row['pids'])=={tail_pid} for row in rows))
        reports.append({'address':IP,'port':port,'state':'current-tailscale-serve' if expected else 'blocked',
                        'listeners':rows})
    return reports


def emit(kind,value):print('PLW_NATIVE_'+kind+' '+json.dumps(value,separators=(',',':')),flush=True)


def wait_for(check,timeout=15):
    until=time.monotonic()+timeout;last=None
    while time.monotonic()<until:
        try:
            value=check()
            if value:return value
        except Exception as error:last=error
        time.sleep(.25)
    raise RuntimeError('Readiness check failed: '+str(last))


def local_login(port):
    context=ssl.create_default_context()
    with socket.create_connection((IP,port),timeout=5) as raw:
        with context.wrap_socket(raw,server_hostname=HOST) as sock:
            sock.sendall(('GET /plw-auth/login HTTP/1.1\r\nHost: '+HOST+'\r\nConnection: close\r\n\r\n').encode())
            head=sock.recv(4096)
    return head.startswith(b'HTTP/1.1 200')


def serve_control(payload,nonce,clients):
    actions=queue.Queue();events=[]
    class Server(ThreadingHTTPServer):
        daemon_threads=True
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_GET(self):
            if self.client_address[0] not in {'127.0.0.1',*clients}:
                self.send_error(403);return
            if self.path!='/plw-native-probe/'+nonce:self.send_error(404);return
            start=time.monotonic();sent=0
            try:
                self.connection.settimeout(50)
                self.send_response(200);self.send_header('Content-Length',str(len(payload)))
                self.send_header('Content-Type','application/octet-stream')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Encoding','identity');self.end_headers()
                for offset in range(0,len(payload),65536):
                    chunk=payload[offset:offset+65536];self.wfile.write(chunk);sent+=len(chunk)
            except OSError:pass
            finally:events.append({'seconds':time.monotonic()-start,'socket_bytes':sent})
        def do_POST(self):
            if self.client_address[0]!='127.0.0.1' or self.path!='/control/'+nonce:self.send_error(403);return
            if self.headers.get('Content-Length') not in ('5','6'):self.send_error(400);return
            action=self.rfile.read(int(self.headers['Content-Length'])).decode('ascii','replace')
            if action not in ('stage','accept','finish','abort'):self.send_error(400);return
            actions.put(action);self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
    servers=[]
    try:
        for address in ('127.0.0.1',IP):
            server=Server((address,PORT),Handler);servers.append(server)
        for server in servers:threading.Thread(target=server.serve_forever,daemon=True).start()
    except Exception:
        for server in servers:server.server_close()
        raise
    return servers,actions,events


def main():
    root=Path(ROOT);binary=root/'caddy';created_unit=False;switched=False;accepted=False;candidate=None;servers=[];guard=False
    if not sys.platform.startswith('linux') or os.geteuid()!=0:raise RuntimeError('Linux root required')
    if not CLIENT_IPS:raise RuntimeError('Missing client Tailscale address')
    before=json.loads(command(['tailscale','serve','status','--json']))
    if not is_original(before):raise RuntimeError('Unexpected Serve baseline; left unchanged')
    if command(['docker','inspect','--format','{{.Config.Image}}','plw-plw-1'])!='plw:0.3.1-device-library-20261021-r2':
        raise RuntimeError('Unexpected application image; left unchanged')
    if Path('/etc/systemd/system/'+SERVICE).exists():raise RuntimeError('Native service already exists; inspect before retrying')
    ports=inspect_ports();emit('PORTS',{'ports':ports})
    blocked=[f"{item['address']}:{item['port']}" for item in ports if item['state']=='blocked']
    if blocked:raise RuntimeError('Port occupied by an unverified listener, left unchanged: '+', '.join(blocked))
    if 'tls.get_certificate.tailscale' not in command([str(binary),'list-modules']):raise RuntimeError('Required certificate manager missing')
    (root/'serve-before.json').write_text(json.dumps(before,indent=2));os.chmod(root/'serve-before.json',0o600)
    payload=secrets.token_bytes(8*1024*1024);nonce=secrets.token_urlsafe(32);path='/plw-native-probe/'+nonce
    (root/'candidate.Caddyfile').write_text(config(TEST_PORT,probe_path=path))
    (root/'Caddyfile').write_text(config(443,probe_path=path))
    (root/'final.Caddyfile').write_text(config(443))
    for name in ('candidate.Caddyfile','Caddyfile','final.Caddyfile'):
        command([str(binary),'validate','--config',str(root/name),'--adapter','caddyfile'])
    try:
        servers,actions,events=serve_control(payload,nonce,CLIENT_IPS)
        log=(root/'candidate.log').open('wb')
        candidate=subprocess.Popen(['/usr/bin/timeout','--kill-after=3s','180s',str(binary),'run',
                                    '--config',str(root/'candidate.Caddyfile'),'--adapter','caddyfile'],
                                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                                    env={**os.environ,'XDG_DATA_HOME':str(root/'state'),'XDG_CONFIG_HOME':str(root/'state')})
        wait_for(lambda:local_login(TEST_PORT))
        emit('READY',{'host':HOST,'ip':IP,'port':PORT,'test_port':TEST_PORT,'nonce':nonce,
                      'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
        if actions.get(timeout=150)!='stage':raise RuntimeError('Client candidate check did not pass; production unchanged')
        if json.loads(command(['tailscale','serve','status','--json']))!=before:raise RuntimeError('Concurrent Serve change; production unchanged')
        # Only verify 443 again; the candidate now owns its temporary ports.
        ports=inspect_ports((443,))
        if ports[0]['state']=='blocked':raise RuntimeError('HTTPS 443 listener changed during candidate test')
        candidate.terminate();candidate.wait(timeout=8);candidate=None;log.close()
        unit_path=Path('/etc/systemd/system/'+SERVICE)
        with unit_path.open('x') as output:output.write(unit())
        created_unit=True
        command(['systemctl','daemon-reload'])
        # Independent systemd watchdog restores the old route if SSH/Python dies.
        command(['systemd-run','--quiet','--unit='+GUARD,'--on-active=240s',
                 '/usr/bin/python3',str(root/'rollback_native_https.py'),'--guard'])
        guard=True
        # Set switched before the command: loss of its response must roll back.
        switched=True
        command(['tailscale','serve','--https=443','off'])
        current=json.loads(command(['tailscale','serve','status','--json'])) or {}
        if current.get('TCP',{}).get('443') or current.get('Web',{}).get(HOST+':443'):
            raise RuntimeError('Old Serve 443 route is still present')
        wait_for(lambda:binding_available(443))
        command(['systemctl','start',SERVICE])
        wait_for(lambda:local_login(443))
        emit('SWITCHED',{'private_https_only':True,'confirmation_deadline_seconds':90})
        if actions.get(timeout=90)!='accept':raise RuntimeError('New production HTTPS acceptance failed')
        (root/'Caddyfile').write_bytes((root/'final.Caddyfile').read_bytes())
        command(['systemctl','restart',SERVICE]);wait_for(lambda:local_login(443))
        emit('FINAL',{'probe_route_removed':True,'confirmation_deadline_seconds':45})
        if actions.get(timeout=45)!='finish':raise RuntimeError('Final production authentication check failed')
        command(['systemctl','enable',SERVICE])
        result={'native_https_active':True,'host':HOST,'bind':IP+':443','app_image_unchanged':True,
                'probe_route_removed':True,'client_download_verified':True,'certificate_provider':'local tailscaled',
                'reading_and_ipad_acceptance':'pending real browser check'}
        (root/'accepted.json.tmp').write_text(json.dumps(result,indent=2))
        os.replace(root/'accepted.json.tmp',root/'accepted.json');accepted=True
        # An accepted marker makes the watchdog a no-op. Failure to cancel an
        # already expired timer must not roll back a verified working gateway.
        try:command(['systemctl','stop',GUARD+'.timer']);guard=False
        except Exception:pass
        emit('DONE',result)
    except BaseException as error:
        if (switched or created_unit) and not accepted:
            try:emit('ROLLBACK',rollback())
            except Exception as recovery:emit('ROLLBACK_ERROR',{'error':str(recovery),'watchdog_pending':guard})
        emit('FAILED',{'error':str(error),'production_switched':switched})
        raise
    finally:
        if candidate is not None and candidate.poll() is None:
            candidate.terminate()
            try:candidate.wait(timeout=8)
            except subprocess.TimeoutExpired:candidate.kill();candidate.wait(timeout=3)
        for server in servers:server.shutdown();server.server_close()
        if guard and not accepted:
            # Leave the independent watchdog armed when rollback had a problem.
            pass


if __name__=='__main__':
    for sig in (signal.SIGHUP,signal.SIGTERM):signal.signal(sig,lambda *_:sys.exit(1))
    main()
