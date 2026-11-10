#!/usr/bin/env bash
# One-time setup of the Oracle VM (docs/deploy/ORACLE.md, cutover). Run as
# root on Ubuntu 24.04, with the deploy key's public half (one line) as the
# argument:
#
#   curl -fsSLO https://raw.githubusercontent.com/amurark3/F1-AI/main/deploy/oracle/bootstrap.sh
#   sudo bash bootstrap.sh "ssh-ed25519 AAAA… f1ai-deploy"
#
# Every step checks before it changes anything, so running it again is safe:
# that is also how to install changed systemd units or rotate the deploy key.
# Without the argument, an existing deploy key is kept.
#
# What it does: Docker Engine + Compose from Docker's apt repository; a 2 GB
# swap file; the block volume formatted (only if blank) and mounted at
# /srv/f1ai; the data directories; ports 80/443 opened in the image's iptables
# rules; unattended upgrades; SSH keys only; the deploy user and its
# forced-command key; deploy/oracle checked out at /srv/f1ai/app; the systemd
# units installed and their timers enabled.
set -euo pipefail

REPO_URL="https://github.com/amurark3/F1-AI.git"
REPO_BRANCH="main"
ROOT="/srv/f1ai"
APP_DIR="$ROOT/app"
DEPLOY_USER="deploy"
APP_UID=10001        # the API image's user (backend/Dockerfile)
POSTGRES_UID=999     # the postgres user in pgvector/pgvector:pg17
SWAPFILE="/swapfile"
SWAP_SIZE="2G"
FS_LABEL="f1ai-data"
TIMERS=(f1ai-pu-ingest.timer f1ai-pu-ingest-daily.timer f1ai-backup.timer f1ai-restore-check.timer f1ai-duckdns.timer)

export DEBIAN_FRONTEND=noninteractive
# A fresh VM runs unattended-upgrades at first boot; wait for its lock.
APT_GET=(apt-get -o DPkg::Lock::Timeout=600)

log() {
  printf '[bootstrap] %s\n' "$*"
}

die() {
  printf '[bootstrap] error: %s\n' "$*" >&2
  exit 1
}

check_host() {
  [[ $(id -u) -eq 0 ]] || die "run as root: sudo bash $0 \"<deploy public key>\""
  # shellcheck source=/dev/null
  source /etc/os-release
  [[ ${ID:-} == ubuntu ]] || die "this script is for Ubuntu (found ${ID:-unknown})"
  [[ ${VERSION_ID:-} == 24.04 ]] || log "warning: written for Ubuntu 24.04; this is ${VERSION_ID:-unknown}"
}

install_packages() {
  log "apt packages"
  "${APT_GET[@]}" update -qq
  # iptables-persistent ships on Oracle's images; preseeded so a fresh install
  # never stops to ask, and never saves the running rules (Docker's among them).
  echo "iptables-persistent iptables-persistent/autosave_v4 boolean false" | debconf-set-selections
  echo "iptables-persistent iptables-persistent/autosave_v6 boolean false" | debconf-set-selections
  "${APT_GET[@]}" install -y -qq ca-certificates curl git iptables-persistent unattended-upgrades >/dev/null
}

install_docker() {
  if dpkg -s docker-ce docker-compose-plugin >/dev/null 2>&1; then
    log "Docker already installed: $(docker --version)"
  else
    log "Docker Engine + Compose from download.docker.com"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    # shellcheck source=/dev/null
    source /etc/os-release
    cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    "${APT_GET[@]}" update -qq
    "${APT_GET[@]}" install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  fi
  systemctl enable --now docker.service >/dev/null
  docker compose version >/dev/null || die "the Docker Compose plugin is not working"
}

setup_swap() {
  # Output captured, never piped into grep -q: under pipefail, grep quitting
  # early kills the writer with SIGPIPE and fails the test.
  local active
  active=$(swapon --show=NAME --noheadings)
  if grep -qxF "$SWAPFILE" <<<"$active"; then
    log "swap: $SWAPFILE already on"
  else
    if [[ ! -f $SWAPFILE ]]; then
      log "swap: creating $SWAP_SIZE at $SWAPFILE"
      fallocate -l "$SWAP_SIZE" "$SWAPFILE"
      chmod 600 "$SWAPFILE"
      mkswap "$SWAPFILE" >/dev/null
    fi
    swapon "$SWAPFILE"
  fi
  if ! grep -qE "^$SWAPFILE\s" /etc/fstab; then
    echo "$SWAPFILE none swap sw 0 0" >>/etc/fstab
  fi
  # Swap is a cushion for a burst, not working memory.
  echo "vm.swappiness=10" >/etc/sysctl.d/99-f1ai-swap.conf
  sysctl -q -p /etc/sysctl.d/99-f1ai-swap.conf
}

# The attached block volume: F1AI_DATA_DEVICE if set, else the console's
# /dev/oracleoci/oraclevdb path, else the one whole disk that is not the boot
# disk and has nothing mounted. More than one candidate stops the script.
find_data_disk() {
  if [[ -n ${F1AI_DATA_DEVICE:-} ]]; then
    printf '%s' "$F1AI_DATA_DEVICE"
    return
  fi
  if [[ -e /dev/oracleoci/oraclevdb ]]; then
    readlink -f /dev/oracleoci/oraclevdb
    return
  fi
  local boot_disk name type candidates=()
  boot_disk=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)")
  while read -r name type; do
    [[ $type == disk && $name != "$boot_disk" ]] || continue
    if [[ -n $(lsblk -nro MOUNTPOINT "/dev/$name" | tr -d '[:space:]') ]]; then
      continue
    fi
    candidates+=("/dev/$name")
  done < <(lsblk -dnro NAME,TYPE)
  case ${#candidates[@]} in
    1) printf '%s' "${candidates[0]}" ;;
    0) die "no unmounted data disk; attach the block volume first (ORACLE.md §1.4)" ;;
    *) die "several candidate disks (${candidates[*]}); rerun with F1AI_DATA_DEVICE=/dev/<disk>" ;;
  esac
}

setup_data_volume() {
  if mountpoint -q "$ROOT"; then
    log "data volume: $ROOT already mounted ($(findmnt -no SOURCE "$ROOT"))"
    return
  fi
  local dev rc=0 fstype uuid
  dev=$(find_data_disk)
  [[ -b $dev ]] || die "$dev is not a block device"

  # blkid -p probes the device itself: 0 = it holds a filesystem or partition
  # table, 2 = nothing found. Only a disk with nothing on it is formatted.
  blkid -p "$dev" >/dev/null 2>&1 || rc=$?
  case $rc in
    2)
      log "data volume: $dev is blank; formatting it ext4 ($FS_LABEL)"
      mkfs.ext4 -q -L "$FS_LABEL" "$dev"
      ;;
    0) log "data volume: $dev already has a filesystem; not formatting" ;;
    *) die "blkid could not probe $dev (exit $rc); not touching it" ;;
  esac
  fstype=$(blkid -p -s TYPE -o value "$dev" || true)
  [[ $fstype == ext4 ]] || die "$dev holds ${fstype:-a partition table}, not ext4; set F1AI_DATA_DEVICE to the right disk"
  uuid=$(blkid -p -s UUID -o value "$dev")

  if [[ -d $ROOT ]] && [[ -n $(ls -A "$ROOT") ]]; then
    die "$ROOT is not mounted but has files in it; move them aside first"
  fi
  mkdir -p "$ROOT"
  # Nothing can write into the bare mount point if the volume is ever missing.
  chattr +i "$ROOT" || log "warning: could not make the bare $ROOT immutable"

  local existing
  existing=$(awk -v mp="$ROOT" '$1 !~ /^#/ && $2 == mp {print $1}' /etc/fstab)
  if [[ -z $existing ]]; then
    # nofail: the VM still boots (and SSH works) if the volume is detached.
    echo "UUID=$uuid $ROOT ext4 defaults,_netdev,nofail 0 2" >>/etc/fstab
  elif [[ $existing != "UUID=$uuid" ]]; then
    die "/etc/fstab already mounts $existing at $ROOT, not UUID=$uuid"
  fi
  systemctl daemon-reload
  mount "$ROOT"
  log "data volume: UUID=$uuid mounted at $ROOT"
}

# Docker must not start before the volume is mounted: Postgres would initialise
# an empty database on the boot disk. With this, a missing volume stops Docker.
docker_waits_for_volume() {
  install -d /etc/systemd/system/docker.service.d
  printf '[Unit]\nRequiresMountsFor=%s\n' "$ROOT" >/etc/systemd/system/docker.service.d/f1ai-data.conf
  systemctl daemon-reload
}

setup_deploy_user() {
  if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    log "user: creating $DEPLOY_USER"
    useradd --create-home --shell /bin/bash --user-group "$DEPLOY_USER"
  fi
  usermod -aG docker "$DEPLOY_USER"
}

make_directories() {
  log "directories under $ROOT"
  chmod 755 "$ROOT"
  install -d -m 750 -o "$APP_UID" -g "$APP_UID" "$ROOT/f1_cache" "$ROOT/huggingface" "$ROOT/f1db"
  install -d -m 700 -o "$POSTGRES_UID" -g "$POSTGRES_UID" "$ROOT/pgdata"
  install -d -m 755 -o root -g root "$ROOT/caddy"
  install -d -m 700 -o root -g root "$ROOT/caddy/data" "$ROOT/caddy/config"
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$ROOT/backups"
  install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$ROOT/state" "$APP_DIR"
}

# Oracle's Ubuntu images end the INPUT chain with a REJECT, in the running
# rules and in /etc/iptables/rules.v4. The ACCEPT rules go just before it in
# both. The file is edited rather than `netfilter-persistent save`d, which would
# also persist Docker's own rules; and never reloaded, which would flush them.
open_firewall() {
  local rules_file=/etc/iptables/rules.v4 spec proto port position line
  local -a specs=("tcp 80" "tcp 443" "udp 443") args
  for spec in "${specs[@]}"; do
    read -r proto port <<<"$spec"
    args=(-p "$proto" -m conntrack --ctstate NEW -m "$proto" --dport "$port" -j ACCEPT)
    if ! iptables -C INPUT "${args[@]}" 2>/dev/null; then
      position=$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')
      if [[ -n $position ]]; then
        iptables -I INPUT "$position" "${args[@]}"
      else
        iptables -A INPUT "${args[@]}"
      fi
      log "firewall: $proto/$port accepted"
    fi
    if [[ -f $rules_file ]]; then
      line="-A INPUT ${args[*]}"
      if ! grep -qxF -- "$line" "$rules_file"; then
        awk -v add="$line" '!done && /^-A INPUT -j REJECT/ {print add; done = 1} {print} END {if (!done) exit 1}' \
          "$rules_file" >"$rules_file.new" || die "no INPUT REJECT line in $rules_file; add $proto/$port by hand"
        mv "$rules_file.new" "$rules_file"
      fi
    fi
  done
  [[ -f $rules_file ]] || log "warning: no $rules_file; the rules above last until reboot"
}

enable_unattended_upgrades() {
  cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
  systemctl enable --now unattended-upgrades.service >/dev/null
  log "unattended upgrades on"
}

harden_sshd() {
  # sshd keeps the first value it reads, and reads sshd_config.d/ in name
  # order, so this file goes first to beat a cloud-init "yes".
  cat >/etc/ssh/sshd_config.d/01-f1ai.conf <<'EOF'
# bootstrap.sh (F1 AI): keys only.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
  sshd -t || die "sshd rejected its configuration; see /etc/ssh/sshd_config.d/01-f1ai.conf"
  systemctl try-reload-or-restart ssh.service
  local effective
  effective=$(sshd -T)
  grep -qx "passwordauthentication no" <<<"$effective" || die "sshd still allows passwords"
  log "sshd: keys only"
}

install_deploy_key() {
  local key=${1:-} home ssh_dir keys tmp
  home=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
  ssh_dir="$home/.ssh"
  keys="$ssh_dir/authorized_keys"
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$ssh_dir"
  if [[ -z $key ]]; then
    if [[ -s $keys ]]; then
      log "deploy key: keeping the installed one"
    else
      log "warning: no deploy key given and none installed; GitHub Actions cannot deploy yet"
    fi
    return
  fi
  # A bare public key: no options of its own, one line.
  [[ $key =~ ^(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|ssh-rsa|sk-[a-z0-9@.-]+)\ [A-Za-z0-9+/=]+(\ [[:print:]]*)?$ ]] ||
    die "the argument is not a single SSH public key line"
  ssh-keygen -l -f /dev/stdin <<<"$key" >/dev/null || die "ssh-keygen could not read the deploy key"
  tmp=$(mktemp)
  # restrict: no forwarding of any kind, no pty, no ~/.ssh/rc; command=: the
  # only program this key can run, whatever the caller asks for.
  printf 'restrict,command="%s" %s\n' "$APP_DIR/deploy/oracle/deploy.sh" "$key" >"$tmp"
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$tmp" "$keys"
  rm -f "$tmp"
  log "deploy key: installed ($(ssh-keygen -l -f /dev/stdin <<<"$key" | cut -d' ' -f2))"
}

as_deploy() {
  # From /: git reads its working directory first, and root's is private.
  (cd / && runuser -u "$DEPLOY_USER" -- "$@")
}

# A sparse, shallow clone holding only deploy/oracle (and the repo's top-level
# files). Once deploy.sh has run, it owns the checked-out commit.
checkout_repo() {
  if [[ ! -d $APP_DIR/.git ]]; then
    log "repo: cloning deploy/oracle into $APP_DIR"
    as_deploy git clone --quiet --depth 1 --filter=blob:none --sparse --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
    as_deploy git -C "$APP_DIR" sparse-checkout set deploy/oracle
  elif [[ -s $ROOT/state/api_tag ]]; then
    log "repo: left at the deployed commit $(as_deploy git -C "$APP_DIR" rev-parse --short HEAD)"
  else
    log "repo: updating to $REPO_BRANCH"
    as_deploy git -C "$APP_DIR" fetch --quiet --depth 1 origin "$REPO_BRANCH"
    as_deploy git -C "$APP_DIR" checkout --quiet --detach FETCH_HEAD
  fi
}

install_env_template() {
  local env_file="$ROOT/.env"
  if [[ ! -e $env_file ]]; then
    install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR/deploy/oracle/env.example" "$env_file"
    log "env: created $env_file from env.example; fill it in before the first deploy"
  else
    chown "$DEPLOY_USER:$DEPLOY_USER" "$env_file"
    chmod 600 "$env_file"
    log "env: $env_file kept (mode 600, owner $DEPLOY_USER)"
  fi
}

install_units() {
  local unit
  for unit in "$APP_DIR"/deploy/oracle/systemd/*.service "$APP_DIR"/deploy/oracle/systemd/*.timer; do
    install -m 644 "$unit" /etc/systemd/system/
  done
  systemctl daemon-reload
  systemctl --quiet enable --now "${TIMERS[@]}"
  log "systemd: ${TIMERS[*]} enabled"
}

main() {
  check_host
  install_packages
  install_docker
  setup_swap
  setup_data_volume
  docker_waits_for_volume
  setup_deploy_user
  make_directories
  open_firewall
  enable_unattended_upgrades
  harden_sshd
  install_deploy_key "${1:-}"
  checkout_repo
  install_env_template
  install_units
  log "done. Next: fill in $ROOT/.env (docs/deploy/ORACLE.md, cutover), then deploy."
}

main "$@"; exit $?
