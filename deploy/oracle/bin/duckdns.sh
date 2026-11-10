#!/usr/bin/env bash
# Points <DUCKDNS_DOMAIN>.duckdns.org at this VM's public IP
# (f1ai-duckdns.timer, every 5 minutes). DuckDNS takes the address the request
# comes from. The token is read from the env file and handed to curl on stdin,
# so it appears in no process list and no log.
#
#   bin/duckdns.sh
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  local domain token answer
  domain=$(env_value DUCKDNS_DOMAIN)
  domain=${domain,,}
  domain=${domain%.duckdns.org}
  token=$(env_value DUCKDNS_TOKEN)
  [[ $domain =~ ^[a-z0-9-]+$ ]] || die "DUCKDNS_DOMAIN in $F1AI_ENV_FILE is empty or not a DuckDNS subdomain"
  [[ $token =~ ^[0-9A-Fa-f-]{36}$ ]] || die "DUCKDNS_TOKEN in $F1AI_ENV_FILE is empty or not a DuckDNS token"

  answer=$(curl --fail --silent --show-error --max-time 30 --retry 2 --config - \
    <<<"url = \"https://www.duckdns.org/update?domains=$domain&token=$token&ip=\"")
  [[ $answer == OK ]] || die "DuckDNS refused the update (answered '${answer:0:10}'); check DUCKDNS_DOMAIN and DUCKDNS_TOKEN"
  log "$domain.duckdns.org updated"
}

main "$@"; exit $?
