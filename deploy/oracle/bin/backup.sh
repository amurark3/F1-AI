#!/usr/bin/env bash
# Nightly database backup (f1ai-backup.timer, 03:30 UTC):
#   1. pg_dump -Fc of the f1ai database to /srv/f1ai/backups/f1ai-<UTC>.dump,
#      with the app tables' row counts beside it (f1ai-<UTC>.counts), counted
#      just before and just after the dump; restore-check.sh compares against
#      them. If rows changed during the dump it tries again, twice; a dump
#      whose counts never settle is kept without a .counts file.
#   2. Keeps the newest 3 dumps on disk.
#   3. Uploads the dump and its counts to the Object Storage bucket
#      (OCI_BUCKET, default f1ai-backups) with the OCI CLI container and
#      instance-principal auth: OCI recognises the VM, so no key is on disk.
#      The bucket's lifecycle rule deletes objects after 14 days.
# Exits non-zero if any step fails.
#
#   bin/backup.sh              dump, prune, upload
#   bin/backup.sh --no-upload  dump and prune only (rehearsal, or no bucket yet)
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Oracle's OCI CLI image; tags are build dates. Bump by hand.
OCI_CLI_IMAGE="ghcr.io/oracle/oci-cli:20261021"
KEEP_LOCAL=3
DUMP_ATTEMPTS=3

upload=1
case ${1:-} in
  "") ;;
  --no-upload) upload=0 ;;
  *)
    echo "usage: backup.sh [--no-upload]" >&2
    exit 2
    ;;
esac

oci() {
  # Host network: the instance-principal token comes from the metadata
  # service at 169.254.169.254, which the image's firewall allows for any user.
  docker run --rm -i --network host "$OCI_CLI_IMAGE" --auth instance_principal "$@"
}

# dump NAME: writes NAME.dump, and NAME.counts if the counts held still.
dump() {
  local base="$F1AI_BACKUP_DIR/$1" attempt before after
  for ((attempt = 1; attempt <= DUMP_ATTEMPTS; attempt++)); do
    before=$(count_rows f1ai)
    compose exec -T postgres pg_dump -U f1ai -d f1ai -Fc >"$base.dump.partial"
    after=$(count_rows f1ai)
    mv -f "$base.dump.partial" "$base.dump"
    if [[ $before == "$after" ]]; then
      printf '%s\n' "$after" >"$base.counts"
      log "dumped $(du -h "$base.dump" | cut -f1) to $base.dump; rows: $(tr '\n' ' ' <<<"$after")"
      return 0
    fi
    log "rows changed during the dump (attempt $attempt of $DUMP_ATTEMPTS)"
    if ((attempt < DUMP_ATTEMPTS)); then
      sleep 30
    fi
  done
  log "warning: kept $base.dump without row counts; the restore check skips it"
}

# Newest KEEP_LOCAL dumps stay; their names sort by time.
prune_local() {
  local dumps=() i
  shopt -s nullglob
  dumps=("$F1AI_BACKUP_DIR"/f1ai-*.dump)
  shopt -u nullglob
  for ((i = 0; i < ${#dumps[@]} - KEEP_LOCAL; i++)); do
    rm -f -- "${dumps[i]}" "${dumps[i]%.dump}.counts"
    log "removed old local dump ${dumps[i]##*/}"
  done
}

upload() {
  local base=$1 bucket namespace file
  bucket=$(env_value OCI_BUCKET)
  bucket=${bucket:-f1ai-backups}
  namespace=$(env_value OCI_NAMESPACE)
  if [[ -z $namespace ]]; then
    namespace=$(oci os ns get --query data --raw-output)
  fi
  [[ $bucket =~ ^[A-Za-z0-9._-]+$ ]] || die "OCI_BUCKET is not a bucket name"
  [[ $namespace =~ ^[A-Za-z0-9._-]+$ ]] || die "OCI_NAMESPACE is not a namespace"
  for file in "$F1AI_BACKUP_DIR/$base.dump" "$F1AI_BACKUP_DIR/$base.counts"; do
    [[ -f $file ]] || continue
    oci os object put --namespace "$namespace" --bucket-name "$bucket" \
      --name "${file##*/}" --file - --force >/dev/null <"$file"
    log "uploaded ${file##*/} to $bucket"
  done
}

# Global, not local: the EXIT trap runs after main has returned.
PARTIAL=""

main() {
  local base
  base="f1ai-$(date -u +%Y%m%dT%H%M%SZ)"
  umask 077
  mkdir -p "$F1AI_BACKUP_DIR"
  PARTIAL="$F1AI_BACKUP_DIR/$base.dump.partial"
  trap 'rm -f -- "$PARTIAL"' EXIT
  dump "$base"
  prune_local
  if [[ $upload == 1 ]]; then
    upload "$base"
  else
    log "upload skipped (--no-upload)"
  fi
}

main "$@"; exit $?
