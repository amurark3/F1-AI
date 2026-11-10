#!/usr/bin/env bash
# The one command the deploy key may run. bootstrap.sh writes it into
# ~deploy/.ssh/authorized_keys as that key's command=, so whatever the caller
# asks for arrives in SSH_ORIGINAL_COMMAND and nothing else runs. It accepts
# exactly two requests:
#
#   deploy <40-hex commit sha>
#       Check out deploy/oracle at that commit, pull
#       ghcr.io/amurark3/f1-ai-api:<sha>, restart the stack on it and wait for
#       /api/ready (then /api/health/deep) from inside the API container. If it
#       is not ready in time, go back to the previous image and exit 1.
#   ingest-rulebook
#       Re-embed the FIA regulation PDFs into pgvector with the deployed image.
#
# Anything else exits 2. GitHub Actions calls it (deploy-oracle.yml); by hand
# on the VM it takes the same requests as arguments:
#
#   sudo -u deploy /srv/f1ai/app/deploy/oracle/deploy.sh deploy <sha>
#   sudo -u deploy /srv/f1ai/app/deploy/oracle/deploy.sh ingest-rulebook
#
# Rehearsal knobs (environment; sshd never passes a caller's environment to a
# forced command): F1AI_READY_TIMEOUT (seconds, default 180), F1AI_OFFLINE=1
# (skip the git fetch and the image pull; use what is already on this machine).
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=bin/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/bin/lib.sh"

READY_TIMEOUT=${F1AI_READY_TIMEOUT:-180}
OFFLINE=${F1AI_OFFLINE:-0}

usage() {
  echo "usage: deploy <40-hex commit sha> | ingest-rulebook" >&2
  exit 2
}

# Sets ACTION (and SHA) from the SSH request, or from the arguments when run
# by hand. The patterns are anchored and whole: no shell ever sees the request.
parse_request() {
  local request
  if [[ -n ${SSH_ORIGINAL_COMMAND+set} ]]; then
    request=$SSH_ORIGINAL_COMMAND
  else
    request="$*"
  fi
  if [[ $request =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    ACTION=deploy
    SHA=${BASH_REMATCH[1]}
  elif [[ $request == ingest-rulebook ]]; then
    ACTION=ingest-rulebook
  else
    request=${request//[^[:print:]]/?}
    log "rejected request: ${request:0:120}" >&2
    usage
  fi
}

is_commit_sha() {
  [[ $1 =~ ^[0-9a-f]{40}$ ]]
}

# One deploy or ingest at a time; a second caller waits up to 15 minutes.
take_lock() {
  mkdir -p "$F1AI_STATE_DIR"
  exec 9>"$F1AI_STATE_DIR/deploy.lock"
  flock -w 900 9 || die "another deploy is still running"
}

# Put deploy/oracle (compose.yaml, Caddyfile, these scripts) at the commit
# being deployed, so the stack definition always matches the image.
sync_files() {
  local sha=$1
  if [[ $OFFLINE == 1 ]]; then
    log "offline: deploy files left as they are"
    return 0
  fi
  git -C "$F1AI_DEPLOY_DIR" fetch --quiet --depth 1 origin "$sha"
  git -C "$F1AI_DEPLOY_DIR" checkout --quiet --detach "$sha"
  log "deploy files at $sha"
}

pull_image() {
  local ref="$F1AI_IMAGE_REPO:$1"
  if [[ $OFFLINE == 1 ]]; then
    if ! docker image inspect "$ref" >/dev/null 2>&1; then
      log "offline, and $ref is not on this machine"
      return 1
    fi
    log "offline: using the local $ref"
    return 0
  fi
  log "pulling $ref"
  if ! docker pull --quiet "$ref" >/dev/null; then
    log "could not pull $ref"
    return 1
  fi
}

start_stack() {
  local tag=$1
  log "starting the stack on $F1AI_IMAGE_REPO:$tag"
  API_TAG=$tag compose up --detach --remove-orphans --quiet-pull
}

# Keep the images of the live and previous deploys; remove the other tags of
# this repository (each holds a copy of the code layers on the boot disk).
prune_images() {
  local keep_live=$1 keep_previous=$2 ref
  while IFS= read -r ref; do
    case $ref in
      *:"<none>" | "$F1AI_IMAGE_REPO:$keep_live" | "$F1AI_IMAGE_REPO:$keep_previous") continue ;;
    esac
    if docker image rm "$ref" >/dev/null 2>&1; then
      log "removed old image $ref"
    else
      log "kept $ref (still in use)"
    fi
  done < <(docker image ls "$F1AI_IMAGE_REPO" --format '{{.Repository}}:{{.Tag}}')
}

rollback() {
  local previous=$1
  if [[ -z $previous ]]; then
    log "no previous image to go back to: the stack stays on $SHA, which is not ready"
    return 0
  fi
  log "rolling back to $previous"
  if is_commit_sha "$previous"; then
    sync_files "$previous"
  fi
  if start_stack "$previous" && wait_ready "$READY_TIMEOUT"; then
    log "rolled back: $previous is serving"
  else
    log "rolled back to $previous, but it is not ready either; check: bin/compose.sh logs api"
  fi
}

deploy() {
  local previous
  previous=$(deployed_tag)
  log "deploying $SHA (live: ${previous:-nothing yet})"
  sync_files "$SHA"
  # A failed pull or start goes back like a failed health check: the deploy
  # files have already moved to the new commit.
  if pull_image "$SHA" && start_stack "$SHA" && wait_ready "$READY_TIMEOUT"; then
    if [[ -n $previous && $previous != "$SHA" ]]; then
      write_state "$F1AI_PREVIOUS_TAG_FILE" "$previous"
    fi
    write_state "$F1AI_TAG_FILE" "$SHA"
    prune_images "$SHA" "${previous:-$SHA}"
    log "deployed $SHA"
    return 0
  fi
  rollback "$previous"
  log "deploy of $SHA failed; on the VM: bin/compose.sh logs --tail 200 api"
  return 1
}

ingest_rulebook() {
  [[ -n $(deployed_tag) ]] || die "nothing is deployed yet; deploy first"
  log "re-embedding the rulebook with $F1AI_IMAGE_REPO:$(deployed_tag)"
  compose --profile jobs run --rm -T jobs python -m app.rag.ingest --force
  log "rulebook ingest done"
}

main() {
  parse_request "$@"
  take_lock
  case $ACTION in
    deploy) deploy ;;
    ingest-rulebook) ingest_rulebook ;;
  esac
}

# On one line, so bash has read the whole call before running it: the deploy
# may check out a new copy of this file while it runs.
main "$@"; exit $?
