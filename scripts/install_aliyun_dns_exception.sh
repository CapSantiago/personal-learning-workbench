#!/usr/bin/env bash
# Host-side fix, separate from the immutable application bundle and learning data.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(id -u)" == 0 ]] || { echo 'Run on the Linux host as root.' >&2; exit 1; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
helper=/usr/local/sbin/plw-aliyun-dns-exception
dropdir=/etc/systemd/system/tailscaled.service.d
dropin="$dropdir/90-plw-aliyun-dns.conf"
[[ -f "$ROOT/aliyun_dns_exception.sh" && ! -L "$ROOT/aliyun_dns_exception.sh" ]] || { echo 'Missing independent helper file.' >&2; exit 1; }
for target in /usr/local/sbin /etc/systemd/system "$dropdir"; do
  [[ ! -L "$target" && ( ! -e "$target" || -d "$target" ) ]] || { echo "Unsafe directory: $target" >&2; exit 1; }
done
for target in "$helper" "$dropin"; do
  [[ ! -e "$target" && ! -L "$target" ]] || { echo "Existing file; refusing to overwrite: $target" >&2; exit 1; }
done
systemctl is-active --quiet tailscaled
# Confirm the existing temporary fix before installing a startup hook.
bash "$ROOT/aliyun_dns_exception.sh" check
install -d -m 0755 /usr/local/sbin "$dropdir"
install -m 0755 "$ROOT/aliyun_dns_exception.sh" "$helper"
(
  umask 022
  set -o noclobber
  cat > "$dropin" <<'UNIT'
[Service]
ExecStartPost=/usr/local/sbin/plw-aliyun-dns-exception apply
UNIT
)
systemctl daemon-reload
"$helper" check
printf '%s\n' 'Installed. Keep public SSH/VNC connected before testing a Tailscale restart.'
printf '%s\n' 'Next: systemctl restart tailscaled; /usr/local/sbin/plw-aliyun-dns-exception check'
