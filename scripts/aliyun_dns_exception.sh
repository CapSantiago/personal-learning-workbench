#!/usr/bin/env bash
# Only the DNS reply exceptions verified on this Alibaba Cloud host.
set -euo pipefail
action="${1:-apply}"
[[ "$action" == apply || "$action" == check || "$action" == remove ]] || { echo 'Usage: aliyun_dns_exception.sh apply|check|remove' >&2; exit 2; }
[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
command -v iptables >/dev/null
ip link show dev eth0 >/dev/null

if [[ "$action" == apply ]]; then
  # tailscaled may notify systemd before its filter chain is ready.
  for attempt in {1..30}; do
    if iptables -w 5 -S ts-input >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi
iptables -w 5 -S ts-input >/dev/null

for dns in 100.100.2.136 100.100.2.138; do
  for proto in udp tcp; do
    rule=(-i eth0 -s "$dns/32" -p "$proto" --sport 53
      -m conntrack --ctstate ESTABLISHED --ctdir REPLY
      -m comment --comment plw-aliyun-dns -j ACCEPT)
    case "$action" in
      apply)
        if ! iptables -w 5 -C ts-input "${rule[@]}" 2>/dev/null; then
          iptables -w 5 -I ts-input 1 "${rule[@]}"
        fi
        ;;
      check) iptables -w 5 -C ts-input "${rule[@]}" ;;
      remove)
        while iptables -w 5 -C ts-input "${rule[@]}" 2>/dev/null; do
          iptables -w 5 -D ts-input "${rule[@]}"
        done
        ;;
    esac
  done
done
printf 'PLW DNS exceptions: %s OK\n' "$action"
