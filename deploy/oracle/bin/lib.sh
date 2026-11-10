# shellcheck shell=bash
# Shared by the scripts in deploy/oracle/: paths, logging and the one way to
# call Docker Compose. Sourced, never run.
#
# Paths default to the VM's layout. F1AI_ROOT and F1AI_ENV_FILE exist so the
# local rehearsal can point everything at a scratch directory; on the VM nothing
# sets them (sshd passes a forced command no environment of the caller's).

# Exported: they are the environment of every script here and its children.
F1AI_DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export F1AI_DEPLOY_DIR

export F1AI_ROOT="${F1AI_ROOT:-/srv/f1ai}"
export F1AI_ENV_FILE="${F1AI_ENV_FILE:-$F1AI_ROOT/.env}"

export F1AI_STATE_DIR="$F1AI_ROOT/state"
# The image tag deploy.sh last deployed successfully.
export F1AI_TAG_FILE="$F1AI_STATE_DIR/api_tag"

log() {
  printf '%s %s: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${0##*/}" "$*"
}

die() {
  log "error: $*" >&2
  exit 1
}

# The tag deploy.sh last recorded as healthy; empty before the first deploy.
deployed_tag() {
  if [[ -s $F1AI_TAG_FILE ]]; then
    tr -d '[:space:]' <"$F1AI_TAG_FILE"
  fi
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
