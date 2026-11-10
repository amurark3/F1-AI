# shellcheck shell=bash
# Shared by the scripts in deploy/oracle/: paths, logging, the env-file reader,
# the one way to call Docker Compose, row counts and the API readiness wait.
# Sourced, never run.
#
# Paths default to the VM's layout. F1AI_ROOT and F1AI_ENV_FILE exist so the
# local rehearsal can point everything at a scratch directory; on the VM nothing
# sets them (sshd passes a forced command no environment of the caller's).

# Exported: they are the environment of every script here and its children.
export F1AI_IMAGE_REPO="ghcr.io/amurark3/f1-ai-api"
F1AI_DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export F1AI_DEPLOY_DIR

export F1AI_ROOT="${F1AI_ROOT:-/srv/f1ai}"
export F1AI_ENV_FILE="${F1AI_ENV_FILE:-$F1AI_ROOT/.env}"

export F1AI_STATE_DIR="$F1AI_ROOT/state"
export F1AI_BACKUP_DIR="$F1AI_ROOT/backups"
# The image tag deploy.sh last deployed successfully, and the one before it.
export F1AI_TAG_FILE="$F1AI_STATE_DIR/api_tag"
export F1AI_PREVIOUS_TAG_FILE="$F1AI_STATE_DIR/api_tag.previous"

# The five tables the app creates for itself (CREATE TABLE IF NOT EXISTS).
# backup.sh records their row counts; restore-check.sh compares against them;
# migrate-from-supabase.sh copies them from Supabase.
F1AI_APP_TABLES=(app_documents analysis_cache chat_message user_profile rulebook_chunk)

log() {
  printf '%s %s: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${0##*/}" "$*"
}

die() {
  log "error: $*" >&2
  exit 1
}

# env_value KEY: the value of KEY in the env file (the last assignment wins, as
# in Compose), with one pair of surrounding quotes removed. Empty when unset.
# Read line by line, never sourced: the file is data, not a script.
env_value() {
  local key=$1 line value=""
  [[ -r $F1AI_ENV_FILE ]] || die "cannot read the env file $F1AI_ENV_FILE"
  while IFS= read -r line || [[ -n $line ]]; do
    if [[ $line == "$key="* ]]; then
      value=${line#*=}
    fi
  done <"$F1AI_ENV_FILE"
  value=${value%$'\r'}
  if [[ $value =~ ^\'(.*)\'$ || $value =~ ^\"(.*)\"$ ]]; then
    value=${BASH_REMATCH[1]}
  fi
  printf '%s' "$value"
}

# The tag deploy.sh last recorded as healthy; empty before the first deploy.
deployed_tag() {
  if [[ -s $F1AI_TAG_FILE ]]; then
    tr -d '[:space:]' <"$F1AI_TAG_FILE"
  fi
}

# write_state FILE VALUE: replace a state file whole (write, then rename).
write_state() {
  local file=$1 value=$2
  mkdir -p "$(dirname "$file")"
  printf '%s\n' "$value" >"$file.tmp"
  mv -f "$file.tmp" "$file"
}

# compose ARGS...: docker compose for this stack. API_TAG defaults to the
# deployed tag, so jobs and hand-run commands use the image that is live.
compose() {
  [[ -r $F1AI_ENV_FILE ]] || die "cannot read the env file $F1AI_ENV_FILE"
  API_TAG="${API_TAG:-$(deployed_tag)}" docker compose \
    --project-directory "$F1AI_DEPLOY_DIR" \
    --file "$F1AI_DEPLOY_DIR/compose.yaml" \
    --env-file "$F1AI_ENV_FILE" \
    "$@"
}

# psql DATABASE ARGS...: psql as f1ai inside the postgres container, unaligned,
# no psqlrc, stopping at the first error.
psql_in() {
  local db=$1
  shift
  compose exec -T postgres psql -U f1ai -d "$db" -XAtq -v ON_ERROR_STOP=1 "$@"
}

# The tables a database has in its public schema, one per line.
PUBLIC_TABLES_SQL="SELECT tablename FROM pg_tables WHERE schemaname = 'public'"

# app_counts_sql PRESENT: one query giving a "table count" row per app table,
# sorted, with "absent" for a table not in PRESENT (the database's tables, one
# per line, from PUBLIC_TABLES_SQL).
app_counts_sql() {
  local present=$1 table sql=""
  for table in "${F1AI_APP_TABLES[@]}"; do
    sql+=${sql:+ UNION ALL }
    if grep -qxF "$table" <<<"$present"; then
      sql+="SELECT '$table', count(*)::text FROM public.$table"
    else
      sql+="SELECT '$table', 'absent'"
    fi
  done
  printf '%s' "SELECT name, n FROM ($sql) AS counts(name, n) ORDER BY name"
}

# count_rows DATABASE: one "table count" line per app table, sorted, with
# "absent" for a table that database does not have. The app creates each table
# on first use (only app_documents exists right after boot), so absence is a
# state, not an error.
count_rows() {
  local db=$1 present
  present=$(psql_in "$db" -c "$PUBLIC_TABLES_SQL")
  psql_in "$db" -F ' ' -c "$(app_counts_sql "$present")"
}

# Run inside the API container: exit 0 once warm-up is complete and the
# database answers, 1 otherwise, printing why on one line. Warm-up that
# finished with an error still counts as up (the error is printed): it means
# an outside source failed, such as GitHub's release downloads, which the
# previous image would hit just the same.
READY_PROBE='
import json, sys, urllib.error, urllib.request
base = "http://127.0.0.1:8000/api"
try:
    state = json.load(urllib.request.urlopen(base + "/ready", timeout=5))
except Exception as exc:
    sys.exit(f"not answering: {exc}")
stage, error = state.get("stage"), state.get("error")
if not state.get("ready"):
    sys.exit(f"warming up: {stage}")
try:
    urllib.request.urlopen(base + "/health/deep", timeout=15)
except urllib.error.HTTPError as exc:
    sys.exit(f"warmed up, but /api/health/deep answered {exc.code}")
except Exception as exc:
    sys.exit(f"warmed up, but /api/health/deep failed: {exc}")
print("ready" + (f" (warm-up finished with an error: {error})" if error else ""))
'
READY_POLL_SECONDS=5

# wait_ready SECONDS: poll the API until it is ready, or fail once SECONDS
# pass. Prints each new status once, not every poll.
wait_ready() {
  local timeout=$1 deadline status last=""
  deadline=$((SECONDS + timeout))
  while ((SECONDS < deadline)); do
    if status=$(compose exec -T api python -c "$READY_PROBE" 2>&1); then
      log "api: $status"
      return 0
    fi
    status=${status##*$'\n'}
    if [[ $status != "$last" ]]; then
      log "api: ${status:0:200}"
      last=$status
    fi
    sleep "$READY_POLL_SECONDS"
  done
  log "api: not ready after ${timeout}s"
  return 1
}
