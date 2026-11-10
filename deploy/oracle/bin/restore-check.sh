#!/usr/bin/env bash
# Weekly proof that the backups restore (f1ai-restore-check.timer). Restores the
# newest local dump that has recorded row counts into a scratch database in the
# same Postgres, counts the app tables there, and compares with the counts
# backup.sh took from the live database around that dump. Any difference, or
# a restore error, exits non-zero. The scratch database is dropped either way.
#
# The comparison is with the live database at dump time, not now: the live
# tables keep changing after the dump (chat, caches), so today's counts would
# fail an intact backup.
#
#   bin/restore-check.sh
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SCRATCH_DB="f1ai_restore_check"

newest_counted_dump() {
  local dumps=() i
  shopt -s nullglob
  dumps=("$F1AI_BACKUP_DIR"/f1ai-*.dump)
  shopt -u nullglob
  for ((i = ${#dumps[@]} - 1; i >= 0; i--)); do
    if [[ -s ${dumps[i]%.dump}.counts ]]; then
      printf '%s' "${dumps[i]}"
      return 0
    fi
  done
  return 1
}

drop_scratch() {
  psql_in postgres -c "SET client_min_messages = warning" -c "DROP DATABASE IF EXISTS $SCRATCH_DB WITH (FORCE)" ||
    log "warning: could not drop $SCRATCH_DB; drop it by hand"
}

main() {
  local dump expected restored
  dump=$(newest_counted_dump) || die "no dump with recorded row counts in $F1AI_BACKUP_DIR"
  expected=$(<"${dump%.dump}.counts")
  log "restoring ${dump##*/} into $SCRATCH_DB"

  trap drop_scratch EXIT
  drop_scratch
  psql_in postgres -c "CREATE DATABASE $SCRATCH_DB"
  compose exec -T postgres pg_restore -U f1ai -d "$SCRATCH_DB" --no-owner --no-privileges --exit-on-error <"$dump"

  restored=$(count_rows "$SCRATCH_DB")
  if [[ $restored != "$expected" ]]; then
    log "MISMATCH: ${dump##*/} does not restore to the rows it was taken from"
    diff <(printf '%s\n' "$expected") <(printf '%s\n' "$restored") | sed 's/^/  /' || true
    exit 1
  fi
  log "ok: ${dump##*/} restores to the same rows: $(tr '\n' ' ' <<<"$restored")"
}

main "$@"; exit $?
