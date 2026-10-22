"""Narrow rollback for this deployment; never reset all Tailscale Serve config."""
import json
from pathlib import Path
import subprocess
import sys
from native_https_config import ROOT,SERVICE,HOST,is_original


def run(args,**kwargs):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=20,**kwargs)


def rollback(*,guard=False):
    root=Path(ROOT)
    if guard and (root/'accepted.json').exists():
        try:accepted=json.loads((root/'accepted.json').read_text())
        except (OSError,ValueError):accepted={}
        if accepted.get('native_https_active') is True and accepted.get('client_download_verified') is True:
            return {'accepted':True,'rollback_needed':False}
    before=json.loads((root/'serve-before.json').read_text())
    if not is_original(before):raise RuntimeError('Saved original configuration is not the expected private proxy')
    current=json.loads(run(['tailscale','serve','status','--json']).stdout) or {}
    if current.get('Foreground'):raise RuntimeError('Concurrent foreground Serve session; inspect before rollback')
    original_present=is_original(current)
    if not original_present:
        # Preserve independent ports, but never replace someone else's 443.
        if '443' in current.get('TCP',{}) or HOST+':443' in current.get('Web',{}):
            raise RuntimeError('HTTPS 443 was changed by another client; not overwriting it')
    # Serve maintains a kernel listener for host-local connections too. The new
    # native listener must release 443 BEFORE re-establishing that old listener.
    subprocess.run(['systemctl','disable','--now',SERVICE],capture_output=True,timeout=25)
    result={'original_private_https_restored':True,'native_proxy_active':
            subprocess.run(['systemctl','is-active','--quiet',SERVICE],timeout=5).returncode==0,
            'native_proxy_enabled':subprocess.run(['systemctl','is-enabled','--quiet',SERVICE],timeout=5).returncode==0}
    if result['native_proxy_active'] or result['native_proxy_enabled']:raise RuntimeError('Cannot release new proxy before restoring old HTTPS listener')
    if not original_present:run(['tailscale','serve','--bg','--https=443','http://127.0.0.1:8501'])
    current=json.loads(run(['tailscale','serve','status','--json']).stdout) or {}
    if (current.get('TCP',{}).get('443')!={'HTTPS':True}
        or current.get('Web',{}).get(HOST+':443')!=before['Web'][HOST+':443']):
        raise RuntimeError('Original HTTPS route was not restored')
    (root/'rollback-result.json').write_text(json.dumps(result))
    if (root/'accepted.json').exists():(root/'accepted.json').replace(root/'previous-accepted.json')
    return result


if __name__=='__main__':print(json.dumps(rollback(guard='--guard' in sys.argv)),flush=True)
