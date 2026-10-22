"""Private kernel TCP HTTPS front end; no application or auth changes."""
HOST='plw.tail066864.ts.net'
IP='100.104.174.9'
SERVICE='plw-native-https.service'
ROOT='/opt/plw-native-https-20261021-r3'


def config(port=443,*,probe_path=None,probe_port=19196,bind=IP,host=HOST,
           upstream='127.0.0.1:8501',tls='get_certificate tailscale'):
    test=''
    if probe_path:
        if not probe_path.startswith('/plw-native-probe/') or any(c not in '/-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in probe_path):
            raise ValueError('Invalid synthetic probe path')
        test=f'''    handle {probe_path} {{
        reverse_proxy 127.0.0.1:{probe_port}
    }}
'''
    return f'''{{
    admin off
    auto_https disable_redirects
    persist_config off
    servers {{
        protocols h1 h2
    }}
}}
https://{host}:{port} {{
    bind {bind}
    tls {{
        {tls}
    }}
{test}    handle {{
        reverse_proxy {upstream} {{
            header_up Host {host}
            header_up X-Forwarded-Proto https
        }}
    }}
}}
'''


def unit():
    return f'''[Unit]
Description=PLW private native HTTPS proxy
After=network-online.target tailscaled.service
Requires=tailscaled.service
PartOf=tailscaled.service
[Service]
Type=simple
User=root
ExecStart={ROOT}/caddy run --config {ROOT}/Caddyfile --adapter caddyfile
Restart=on-failure
RestartSec=3
Environment=XDG_DATA_HOME=/var/lib/plw-native-https
Environment=XDG_CONFIG_HOME=/var/lib/plw-native-https
StateDirectory=plw-native-https
StateDirectoryMode=0700
UMask=0077
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
InaccessiblePaths=/srv/plw/private /srv/plw/data /srv/plw/backups /etc/shadow /etc/gshadow
TimeoutStopSec=10
[Install]
WantedBy=multi-user.target
'''


def is_original(config):
    """Only the known existing private root proxy is an acceptable baseline."""
    allowed={'TCP','Web','AllowFunnel','Foreground'}
    return (set(config)<=allowed and config.get('TCP')=={'443':{'HTTPS':True}}
            and config.get('Web')=={HOST+':443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8501'}}}}
            and not any(config.get('AllowFunnel',{}).values()) and not config.get('Foreground'))
