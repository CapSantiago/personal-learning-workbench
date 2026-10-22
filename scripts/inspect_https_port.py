"""Read-only raw Linux port evidence. No service changes or credential reads."""
import json
import os
from pathlib import Path
import subprocess
import sys


def read_command(args):
    try:
        result=subprocess.run(args,capture_output=True,text=True,timeout=8)
        return {'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    except (OSError,subprocess.TimeoutExpired) as error:return {'error':str(error)}


def proc_port_rows(text,port=443):
    """Keep raw rows as well as inode IDs; don't parse human ss columns."""
    rows=[]
    for line in text.splitlines()[1:]:
        fields=line.split()
        if len(fields)>=10 and fields[1].rpartition(':')[2].upper()==f'{port:04X}':
            rows.append({'raw':line,'local_hex':fields[1],'state_hex':fields[3],'uid':fields[7],'inode':fields[9]})
    return rows


def collect(proc=Path('/proc')):
    result={
        'read_only':True,
        'ss_tcp_443':read_command(['ss','-H','-ltnpe','(','sport','=',':443',')']),
        'ss_tcp_all_listeners':read_command(['ss','-H','-ltnp']),
        'tailscaled_service':read_command(['systemctl','show','tailscaled.service','--property=MainPID','--property=ExecMainPID','--property=ActiveState']),
        'native_proxy_service':read_command(['systemctl','show','plw-native-https.service','--property=LoadState','--property=MainPID','--property=ActiveState']),
        'serve_config':read_command(['tailscale','serve','status','--json']),
        'proc_tcp_443':{},'socket_owners':[]}
    for name in ('tcp','tcp6'):
        try:result['proc_tcp_443'][name]=proc_port_rows((proc/'net'/name).read_text())
        except OSError as error:result['proc_tcp_443'][name]={'error':str(error)}
    inodes={row['inode'] for rows in result['proc_tcp_443'].values() if isinstance(rows,list)
            for row in rows if row['inode']!='0'}
    sockets={'socket:['+inode+']' for inode in inodes}
    # Compare only socket inode symlinks. Never read cmdline, environ, file
    # contents, account configuration, private keys or unrelated FD targets.
    for process in proc.iterdir():
        if not process.name.isdecimal():continue
        try:
            for fd in (process/'fd').iterdir():
                try:target=os.readlink(fd)
                except OSError:continue
                if target not in sockets:continue
                try:comm=(process/'comm').read_text().strip()
                except OSError:comm='unavailable'
                result['socket_owners'].append({'pid':int(process.name),'fd':fd.name,'socket':target,'comm':comm})
        except (OSError,ProcessLookupError):continue
    return result


if __name__=='__main__':
    if not sys.platform.startswith('linux') or os.geteuid()!=0:raise SystemExit('Use existing Linux root SSH account')
    print('PLW_HTTPS_PORT_EVIDENCE '+json.dumps(collect(),ensure_ascii=True),flush=True)
