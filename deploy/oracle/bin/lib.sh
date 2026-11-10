# shellcheck shell=bash
# Shared by the scripts in deploy/oracle/: paths, logging, the env-file reader
# and the one way to call Docker Compose. Sourced, never run.
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
# backup.sh records their row counts; restore-check.sh compares against them.
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

# count_rows DATABASE: one "table count" line per app table, sorted, with
# "absent" for a table that database does not have. The app creates each table
# on first use (only app_documents exists right after boot), so absence is a
# state, not an error.
count_rows() {
  local db=$1 present table sql=""
  present=$(psql_in "$db" -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
  for table in "${F1AI_APP_TABLES[@]}"; do
    sql+=${sql:+ UNION ALL }
    if grep -qxF "$table" <<<"$present"; then
      sql+="SELECT '$table', count(*)::text FROM public.$table"
    else
      sql+="SELECT '$table', 'absent'"
    fi
  done
  psql_in "$db" -F ' ' -c "SELECT name, n FROM ($sql) AS counts(name, n) ORDER BY name"
}
