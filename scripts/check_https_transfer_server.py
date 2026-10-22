"""Ephemeral Serve comparison, using the frozen, previously tested RAM endpoint.

The launcher injects BASE_SOURCE and CLIENT_IPS. No credentials/courseware are
read. Only a foreground Serve session on an unused tailnet HTTPS port is added.
The production 443 configuration must remain byte-equivalent throughout.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

CLIENT_IPS=[]
HTTPS_PORT=19443
BACKEND_PORT=19194
HOST='plw.tail066864.ts.net'


def canonical(config):
    config=copy.deepcopy(config)
    if not config.get('Foreground'):config.pop('Foreground',None)
    return json.dumps(config,sort_keys=True,separators=(',',':'))


def has_port(config,port):
    if str(port) in config.get('TCP',{}):return True
    if any(key.endswith(':'+str(port)) for key in config.get('Web',{})):return True
    return any(has_port(child,port) for child in config.get('Foreground',{}).values())


def config_read():
    result=subprocess.run(['tailscale','serve','status','--json'],capture_output=True,
                          text=True,timeout=5,check=True)
    config=json.loads(result.stdout)
    if not isinstance(config,dict):raise ValueError('Missing Serve configuration')
    return config


class ForegroundServe:
    def __init__(self,read=config_read,popen=subprocess.Popen):
        self.read=read;self.popen=popen;self.process=None;self.before=None;self.session=None
        self.cleanup=None

    def start(self,backend):
        self.before=self.read()
        if has_port(self.before,HTTPS_PORT):raise RuntimeError('Test HTTPS port already configured; left untouched')
        if not has_port(self.before,443):raise RuntimeError('Production HTTPS configuration missing; left untouched')
        # GNU timeout is a separate bounded supervisor: even abrupt loss of the
        # Python/SSH process cannot leave this CLI session serving indefinitely.
        self.process=self.popen(['/usr/bin/timeout','--kill-after=3s','165s',
                                'tailscale','serve','--bg=false','--https='+str(HTTPS_PORT),
                                'http://127.0.0.1:'+str(backend)],stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise RuntimeError('Temporary Serve failed to start')
            current=self.read()
            added=set(current.get('Foreground',{}))-set(self.before.get('Foreground',{}))
            if len(added)==1:
                session=added.pop();own=current['Foreground'][session]
                without=copy.deepcopy(current);del without['Foreground'][session]
                if canonical(without)!=canonical(self.before):raise RuntimeError('Concurrent Serve configuration change; aborting')
                if (own.get('TCP')=={str(HTTPS_PORT):{'HTTPS':True}}
                    and own.get('Web')=={HOST+':'+str(HTTPS_PORT):{'Handlers':{'/':{'Proxy':'http://127.0.0.1:'+str(backend)}}}}
                    and not any(own.get('AllowFunnel',{}).values())):
                    self.session=session
                    return
                raise RuntimeError('Unexpected temporary Serve configuration; aborting')
            time.sleep(.2)
        raise RuntimeError('Temporary Serve readiness timed out')

    def close(self):
        if self.cleanup is not None:return self.cleanup
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        # Closing the foreground CLI's IPN bus session removes only that session.
        # Never reset/restore a whole Serve config, which could overwrite others.
        matched=False;gone=False
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            current=self.read()
            gone=not has_port(current,HTTPS_PORT)
            matched=canonical(current)==canonical(self.before) if self.before is not None else True
            if gone:break
            time.sleep(.1)
        self.cleanup={'temporary_https_removed':gone,'original_serve_config_unchanged':matched}
        return self.cleanup


def run_probe(base_source,client_ips,*,lease=None,emit=print,tail_ip='100.104.174.9',
              port=BACKEND_PORT,lifetime=180,payload_size=8*1024*1024):
    base={'__name__':'plw_frozen_transfer_base'}
    # Increase the trusted test endpoint's per-write timeout to match this
    # client's 45-second cap; neither modification changes system TCP settings.
    exec(compile(base_source.replace('settimeout(22)','settimeout(50)'),'<frozen-transfer-base>','exec'),base)
    base['PAYLOAD_SIZE']=payload_size
    lease=lease or ForegroundServe()
    def output(line,**kwargs):
        if line.startswith('PLW_TRANSFER_READY '):
            meta=json.loads(line.split(' ',1)[1]);lease.start(meta['port'])
            meta.update(https_port=HTTPS_PORT,host=HOST)
            emit('PLW_TRANSFER_READY '+json.dumps(meta),**kwargs)
        elif line.startswith('PLW_TRANSFER_REPORT '):
            report=json.loads(line.split(' ',1)[1])
            report['read_only']=False
            report['scope']='temporary private foreground Serve session only; no application/data/system-setting writes'
            report['serve_cleanup']=lease.close()
            emit('PLW_TRANSFER_REPORT '+json.dumps(report),**kwargs)
        else:emit(line,**kwargs)
    try:
        base['serve_test'](client_ips,tail_ip=tail_ip,port=port,lifetime=lifetime,emit=output)
    finally:
        cleanup=lease.close()
        if not all(cleanup.values()):emit('PLW_HTTPS_CLEANUP_WARNING '+json.dumps(cleanup),flush=True)


if __name__=='__main__':
    if not sys.platform.startswith('linux') or os.geteuid()!=0:raise SystemExit('Use the existing Linux root SSH account')
    if not CLIENT_IPS or any(not re.fullmatch(r'100(?:\.\d{1,3}){3}',ip) for ip in CLIENT_IPS):raise SystemExit('Missing client tailnet IPv4')
    signal.signal(signal.SIGHUP,lambda *_:sys.exit(1))
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(1))
    if 'BASE_SOURCE' not in globals():BASE_SOURCE=Path(__file__).with_name('transfer_base.py').read_text()
    if hashlib.sha256(BASE_SOURCE.encode()).hexdigest()!='35ee26bcda10845020bb3155cff7a3b0df157e0120fa0fc15f1cbd8dcc1c0c4b':raise SystemExit('Frozen endpoint checksum mismatch')
    run_probe(BASE_SOURCE,CLIENT_IPS)
