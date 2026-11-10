#!/usr/bin/env bash
# Copies the app's data from Supabase into this VM's Postgres, once, at cutover
# (docs/deploy/ORACLE.md, cutover; plan P0c.6). Run it as deploy after the first
# deploy (it runs the deployed image) and after writes to Supabase have stopped
# (Render suspended, the ingest Actions disabled). The source URL comes from the
# environment, never the command line:
#
#   sudo -iu deploy
#   read -rsp 'Supabase session pooler URL: ' SOURCE_DATABASE_URL; echo
#   export SOURCE_DATABASE_URL
#   /srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --dry-run
#   /srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --replace
#   unset SOURCE_DATABASE_URL
#
# Steps:
#   1. libpq splits SOURCE_DATABASE_URL into PGHOST, PGPASSWORD … (the API
#      image's scripts.libpq_env, run with no network), and pg_dump and psql
#      get those by name, so the URL never reaches a command line, where ps
#      shows it. It is never printed.
#   2. The app's five tables are created in the target by the app's own code
#      (scripts.ensure_schema in the jobs container): only app_documents exists
#      once the API has booted; the others are created on first use.
#   3. Checks: the source answers, runs a PostgreSQL that pg_dump 17 can read,
#      and its vector columns have the width the app embeds with.
#   4. pg_dump --data-only of the five tables (those the source has) to a file
#      on the volume, deleted on exit. COPY names its columns, so a column the
#      source lacks (app_documents.version, added in P0c.4) takes the target's
#      default.
#   5. With the API stopped, restores it in one transaction: refuses if any of
#      the five tables holds rows, unless --replace, which empties them in that
#      same transaction; moves each id sequence past the largest id. Any error
#      rolls the whole restore back.
#   6. Verifies each table's row count in the source, counted again now,
#      against the target, and the vector widths. A difference exits 1 with a
#      table that tells a source still being written apart from a bad restore.
#   7. Starts the API again and waits for /api/ready.
#
#   --dry-run  steps 1-6 into a scratch database on the same server, dropped
#              afterwards; the live tables and the API are left alone.
#   --replace  overwrite the five tables although they hold rows. The API
#              writes documents of its own soon after it boots, so the run at
#              cutover is likely to need it; the dry run says so if it does.
#
# Never writes to the source: pg_dump reads in a read-only transaction, and
# every psql session there runs with default_transaction_read_only.
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# pg_dump and psql for the source: the image compose.yaml runs Postgres from,
# so the client, its dump format and the target server are one version.
PG_CLIENT_IMAGE="pgvector/pgvector:pg17"
PG_CLIENT_MAJOR=17
LIVE_DB="f1ai"
SCRATCH_DB="f1ai_migrate_check"
READY_TIMEOUT=${F1AI_READY_TIMEOUT:-180}

DRY_RUN=0
REPLACE=0
# The source's libpq settings, "PGNAME=value" each. Never exported in this
# shell: source_client exports them in a subshell, for one docker run.
SOURCE_ENV=()
SOURCE_TABLES=""
EMBEDDING_DIM=""
# Globals, not locals: the EXIT trap runs after main has returned.
DUMP_FILE=""
SCRATCH_CREATED=0
API_STOPPED=0

indent() {
  sed 's/^/  /'
}

# Lines joined into one: "a, b, c".
listing() {
  paste -sd ',' - | sed 's/,/, /g'
}

usage() {
  echo "usage: migrate-from-supabase.sh [--dry-run] [--replace]" >&2
  echo "       (the source URL is read from SOURCE_DATABASE_URL, never from an argument)" >&2
  exit 2
}

parse_args() {
  local arg
  for arg in "$@"; do
    case $arg in
      --dry-run) DRY_RUN=1 ;;
      --replace) REPLACE=1 ;;
      *) usage ;;
    esac
  done
}

# "public.app_documents, public.analysis_cache, …": the five tables, for SQL.
qualified_tables() {
  local table list=""
  for table in "${F1AI_APP_TABLES[@]}"; do
    list+="${list:+, }public.$table"
  done
  printf '%s' "$list"
}

# The app tables' vector columns, "table.column width" (pgvector keeps the
# width in the type modifier; -1 means none was declared).
vector_widths_sql() {
  local names
  names=$(printf "'%s'," "${F1AI_APP_TABLES[@]}")
  printf '%s' "SELECT c.relname || '.' || a.attname, a.atttypmod
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE n.nspname = 'public' AND c.relname IN (${names%,}) AND t.typname = 'vector'
      AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY 1"
}

# The widths the stored vectors actually have, per vector column: "none" when
# no row has one.
ROW_WIDTHS_SQL="SELECT 'chat_message.embedding', coalesce(string_agg(DISTINCT vector_dims(embedding)::text, ','), 'none') FROM public.chat_message
  UNION ALL
  SELECT 'rulebook_chunk.embedding', coalesce(string_agg(DISTINCT vector_dims(embedding)::text, ','), 'none') FROM public.rulebook_chunk"

# --- The source ---------------------------------------------------------------

# source_setting NAME: the value of one libpq setting, empty when unset.
source_setting() {
  local entry
  for entry in "${SOURCE_ENV[@]}"; do
    if [[ $entry == "$1="* ]]; then
      printf '%s' "${entry#*=}"
      return 0
    fi
  done
}

# host:port/database, for logs. No user, no password.
source_label() {
  local port
  port=$(source_setting PGPORT)
  printf '%s:%s/%s' "$(source_setting PGHOST)" "${port:-5432}" "$(source_setting PGDATABASE)"
}

# source_client CMD ARGS...: CMD in the Postgres client image, connected to the
# source through libpq's variables, which docker run is given by name only.
source_client() {
  (
    local entry names=()
    for entry in "${SOURCE_ENV[@]}"; do
      export "${entry?}"
      names+=(-e "${entry%%=*}")
    done
    exec docker run --rm "${names[@]}" "$PG_CLIENT_IMAGE" "$@"
  )
}

# source_psql ARGS...: psql on the source, unaligned, read-only for the session.
source_psql() {
  source_client psql -XAtq -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only = on" "$@"
}

api_image() {
  local tag=${API_TAG:-$(deployed_tag)}
  [[ -n $tag ]] || die "nothing is deployed yet: deploy first (the migration runs the deployed image)"
  printf '%s:%s' "$F1AI_IMAGE_REPO" "$tag"
}

load_source() {
  local image settings line
  [[ -n ${SOURCE_DATABASE_URL:-} ]] ||
    die "SOURCE_DATABASE_URL is not set: export the Supabase session pooler URL first (never pass it as an argument)"
  image=$(api_image)
  settings=$(docker run --rm --network none -e SOURCE_DATABASE_URL "$image" \
    python -m scripts.libpq_env SOURCE_DATABASE_URL) ||
    die "SOURCE_DATABASE_URL was refused (why is above)"
  unset SOURCE_DATABASE_URL
  while IFS= read -r line; do
    [[ $line =~ ^PG[A-Z_]+= ]] || die "unexpected output from scripts.libpq_env"
    SOURCE_ENV+=("$line")
  done <<<"$settings"
  if [[ $(source_setting PGPORT) == 6543 && $(source_setting PGHOST) == *.pooler.supabase.com ]]; then
    die "that is Supabase's transaction pooler (port 6543), which pg_dump cannot use: take the session pooler URL (port 5432)"
  fi
  log "source: $(source_label) (read-only; the credentials stay hidden)"
}

check_source() {
  local version major tables
  version=$(source_psql -c "SHOW server_version_num") || die "cannot query the source $(source_label) (libpq's message is above)"
  [[ $version =~ ^[0-9]+$ ]] || die "the source reported no server version"
  major=$((version / 10000))
  ((major <= PG_CLIENT_MAJOR)) ||
    die "the source runs PostgreSQL $major; pg_dump $PG_CLIENT_MAJOR reads $PG_CLIENT_MAJOR and older only"
  tables=$(source_psql -c "$PUBLIC_TABLES_SQL")
  SOURCE_TABLES=$(grep -xF -f <(printf '%s\n' "${F1AI_APP_TABLES[@]}") <<<"$tables" | sort || true)
  [[ -n $SOURCE_TABLES ]] || die "the source has none of the app's tables: is SOURCE_DATABASE_URL the app's database?"
  log "source: PostgreSQL $major; app tables: $(listing <<<"$SOURCE_TABLES")"
}

# source_counts: "table count" per app table in the source, now; a table the
# source does not have counts 0 (the target has it, empty).
source_counts() {
  local tables
  tables=$(source_psql -c "$PUBLIC_TABLES_SQL")
  source_psql -F ' ' -c "$(app_counts_sql "$tables")" | sed 's/ absent$/ 0/' | LC_ALL=C sort
}

# --- The target ---------------------------------------------------------------

# rows_held COUNTS: the "table count" lines of tables that hold rows.
rows_held() {
  awk '$2 != "0" && $2 != "absent"' <<<"$1"
}

# ensure_target_schema DATABASE: the app's tables, by the app's own code. Sets
# EMBEDDING_DIM from what it reports.
ensure_target_schema() {
  local db=$1 out
  log "creating the app's tables in $db (scripts.ensure_schema, jobs container)"
  if ! out=$(compose --profile jobs run --rm -T jobs python -m scripts.ensure_schema --dbname "$db"); then
    printf '%s\n' "$out" >&2
    die "could not create the app's tables in $db"
  fi
  indent <<<"$out"
  [[ $out =~ embedding\ dimension\ ([0-9]+) ]] || die "scripts.ensure_schema reported no embedding dimension"
  EMBEDDING_DIM=${BASH_REMATCH[1]}
}

# check_widths WHERE WIDTHS: every "table.column width" line has the app's
# width (EMBEDDING_DIM).
check_widths() {
  local where=$1 widths=$2 column width bad=0
  while read -r column width; do
    [[ -n $column ]] || continue
    if [[ $width != "$EMBEDDING_DIM" ]]; then
      log "$where: $column has width $width; the app embeds with $EMBEDDING_DIM"
      bad=1
    fi
  done <<<"$widths"
  return "$bad"
}

check_vector_columns() {
  local db=$1 sql source_widths target_widths
  sql=$(vector_widths_sql)
  source_widths=$(source_psql -F ' ' -c "$sql")
  target_widths=$(psql_in "$db" -F ' ' -c "$sql")
  check_widths source "$source_widths" || die "the source's vectors do not fit the app's; nothing was copied"
  check_widths "$db" "$target_widths" || die "$db's vector columns are not the app's; nothing was copied"
  [[ $(wc -l <<<"$target_widths") == 2 ]] || die "$db is missing a vector column: $(listing <<<"$target_widths")"
  log "vector columns: vector($EMBEDDING_DIM) in $db; in the source: $(listing <<<"${source_widths:-none}")"
}

create_scratch() {
  drop_scratch
  psql_in postgres -c "CREATE DATABASE $SCRATCH_DB"
  SCRATCH_CREATED=1
}

drop_scratch() {
  psql_in postgres -c "SET client_min_messages = warning" -c "DROP DATABASE IF EXISTS $SCRATCH_DB WITH (FORCE)" ||
    log "warning: could not drop $SCRATCH_DB; drop it by hand"
}

# One deploy, ingest or migration at a time: deploy.sh and pu-ingest.sh take
# these locks too, so neither restarts the API or writes a document mid-restore.
take_locks() {
  mkdir -p "$F1AI_STATE_DIR"
  exec 8>"$F1AI_STATE_DIR/deploy.lock"
  flock -w 900 8 || die "a deploy is still running; try again once it is done"
  exec 7>"$F1AI_STATE_DIR/pu-ingest.lock"
  flock -w 900 7 || die "the power-unit ingest is still running; try again once it is done"
}

stop_api() {
  if [[ -n $(compose ps --quiet --status running api) ]]; then
    log "stopping the API for the restore"
    compose stop api
    API_STOPPED=1
  fi
}

restart_api() {
  API_STOPPED=0
  log "starting the API"
  compose start api && wait_ready "$READY_TIMEOUT"
}

# --- Dump, restore, verify ----------------------------------------------------

dump_source() {
  local table args=() started=$SECONDS
  for table in "${F1AI_APP_TABLES[@]}"; do
    if grep -qxF "$table" <<<"$SOURCE_TABLES"; then
      args+=("--table=public.$table")
    fi
  done
  mkdir -p "$F1AI_ROOT/migration"
  DUMP_FILE="$F1AI_ROOT/migration/supabase-$(date -u +%Y%m%dT%H%M%SZ).sql"
  log "dumping from the source: $(listing <<<"$SOURCE_TABLES")"
  source_client pg_dump --data-only --strict-names --encoding=UTF8 "${args[@]}" >"$DUMP_FILE" ||
    die "pg_dump failed (its message is above)"
  log "dumped $(du -h "$DUMP_FILE" | cut -f1) in $((SECONDS - started))s"
}

# dump_counts: "table count" per app table, from the COPY blocks in the dump.
dump_counts() {
  local table counts
  counts=$(awk '
    /^COPY public\./ { table = substr($2, 8); rows = 0; inside = 1; next }
    inside && $0 == "\\." { print table, rows; inside = 0; next }
    inside { rows++ }' "$DUMP_FILE")
  for table in "${F1AI_APP_TABLES[@]}"; do
    awk -v t="$table" '$1 == t { n = $2 } END { print t, n + 0 }' <<<"$counts"
  done | LC_ALL=C sort
}

# The statements before the dump: lock the five tables against other writers,
# then empty them (--replace) or make sure they are empty.
restore_head() {
  local tables table checks=""
  tables=$(qualified_tables)
  printf 'LOCK TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n' "$tables"
  if ((REPLACE)); then
    printf 'TRUNCATE %s;\n' "$tables"
    return 0
  fi
  for table in "${F1AI_APP_TABLES[@]}"; do
    checks+="${checks:+ OR }EXISTS (SELECT 1 FROM public.$table)"
  done
  printf '%s\n' "DO \$guard\$ BEGIN
  IF $checks THEN
    RAISE EXCEPTION 'the target tables hold rows, so nothing was restored; re-run with --replace to overwrite them';
  END IF;
END \$guard\$;"
}

# The statement after the dump: every serial or identity column's sequence
# continues after the largest id. The dump sets the search path to nothing, so
# every name here is qualified.
restore_tail() {
  local relations
  relations=$(printf "'public.%s'::regclass," "${F1AI_APP_TABLES[@]}")
  printf '%s\n' "DO \$sequences\$
DECLARE
  col record;
BEGIN
  FOR col IN
    SELECT a.attrelid::regclass AS tbl, a.attname AS name,
           pg_catalog.pg_get_serial_sequence(a.attrelid::regclass::text, a.attname) AS seq
    FROM pg_catalog.pg_attribute a
    WHERE a.attrelid IN (${relations%,}) AND a.attnum > 0 AND NOT a.attisdropped
  LOOP
    CONTINUE WHEN col.seq IS NULL;
    EXECUTE pg_catalog.format(
      'SELECT pg_catalog.setval(%L, coalesce((SELECT max(%I) FROM %s), 0) + 1, false)',
      col.seq, col.name, col.tbl);
  END LOOP;
END \$sequences\$;"
}

restore() {
  local db=$1 started=$SECONDS
  log "restoring into $db in one transaction"
  { restore_head && cat "$DUMP_FILE" && restore_tail; } |
    psql_in "$db" --single-transaction -f - >/dev/null ||
    die "the restore failed and was rolled back, so $db is as it was (the error is above)"
  log "restored in $((SECONDS - started))s"
}

# verify DATABASE: row counts and vector widths against the source. On a
# mismatch, prints source (now), dump and target counts side by side. Sorted
# here, not by each server: the two may collate differently.
verify() {
  local db=$1 source target dumped widths
  source=$(source_counts)
  target=$(count_rows "$db" | LC_ALL=C sort)
  if [[ $source != "$target" ]]; then
    dumped=$(dump_counts)
    log "MISMATCH: the row counts in $db differ from the source's"
    LC_ALL=C join <(printf '%s\n' "$source") <(printf '%s\n' "$dumped") |
      LC_ALL=C join - <(printf '%s\n' "$target") |
      awk 'BEGIN { printf "  %-16s %12s %12s %12s\n", "table", "source now", "dump", "target" }
           { printf "  %-16s %12s %12s %12s%s\n", $1, $2, $3, $4, ($2 == $4 ? "" : "   <-") }'
    if [[ $dumped == "$target" ]]; then
      log "the restore matches the dump, so the source changed after it: stop every writer to Supabase, then re-run with --replace"
    else
      log "the restore does not match the dump"
    fi
    return 1
  fi
  widths=$(psql_in "$db" -F ' ' -c "$ROW_WIDTHS_SQL")
  if grep -qvE " (none|$EMBEDDING_DIM)\$" <<<"$widths"; then
    log "MISMATCH: stored vectors in $db with another width: $(listing <<<"$widths")"
    return 1
  fi
  log "verified: row counts equal the source's; stored vectors: $(listing <<<"$widths")"
}

summary() {
  local db=$1
  count_rows "$db" | awk '{ printf "  %-16s %10s rows\n", $1, $2 }'
  log "took ${SECONDS}s"
}

# Remove the dump and the scratch database, and start the API if this run
# stopped it. Idempotent: main calls it on success, the EXIT trap on any exit.
cleanup() {
  if [[ -n $DUMP_FILE ]]; then
    rm -f -- "$DUMP_FILE"
    DUMP_FILE=""
  fi
  if ((SCRATCH_CREATED)); then
    SCRATCH_CREATED=0
    drop_scratch
  fi
  if ((API_STOPPED)) && ! restart_api; then
    log "warning: the API is not ready; check: bin/compose.sh logs --tail 200 api"
    return 1
  fi
}

main() {
  local live held target
  parse_args "$@"
  umask 077
  trap cleanup EXIT
  load_source
  check_source

  live=$(count_rows "$LIVE_DB")
  held=$(rows_held "$live")
  if ((DRY_RUN)); then
    target=$SCRATCH_DB
    create_scratch
  else
    target=$LIVE_DB
    if [[ -n $held ]] && ((!REPLACE)); then
      log "the live tables already hold rows:"
      indent <<<"$held"
      die "nothing was changed; re-run with --replace to overwrite them with the source's"
    fi
  fi

  ensure_target_schema "$target"
  check_vector_columns "$target"
  dump_source
  if ((!DRY_RUN)); then
    take_locks
    stop_api
  fi
  restore "$target"
  if ! verify "$target"; then
    if ((!DRY_RUN)); then
      log "the restore into $LIVE_DB is committed; fix the cause and re-run with --replace"
    fi
    exit 1
  fi

  if ((DRY_RUN)); then
    log "dry run passed; would copy:"
    summary "$target"
    if [[ -n $held ]]; then
      log "the live tables hold rows ($(listing <<<"$held")), so the real run needs --replace"
    fi
  else
    log "migrated:"
    summary "$target"
  fi
  cleanup || die "the data is migrated, but the API did not come back"
}

main "$@"; exit $?
