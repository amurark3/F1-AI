#!/usr/bin/env bash
# The FIA power-unit document ingest (backend/scripts/ingest_power_units.py) in
# the jobs container, with the deployed image. systemd runs it:
#   f1ai-pu-ingest.timer        hourly at :17, Thursday to Monday (race weekends)
#   f1ai-pu-ingest-daily.timer  daily at 05:47 UTC with --all-events, which
#                               re-reads every event page of the season
# Same schedule and flags as .github/workflows/ingest-power-units.yml, which
# this replaces at cutover.
#
#   bin/pu-ingest.sh [--all-events]
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [[ $# -gt 1 || ($# -eq 1 && $1 != --all-events) ]]; then
  echo "usage: pu-ingest.sh [--all-events]" >&2
  exit 2
fi
[[ -n $(deployed_tag) ]] || die "nothing is deployed yet (no $F1AI_TAG_FILE)"

# The job is the only writer of the power-unit documents. The hourly and the
# daily run take turns, as the workflow's concurrency group made them.
mkdir -p "$F1AI_STATE_DIR"
exec 9>"$F1AI_STATE_DIR/pu-ingest.lock"
flock 9

log "power-unit ingest ${1:-} with $F1AI_IMAGE_REPO:$(deployed_tag)"
compose --profile jobs run --rm -T jobs python -m scripts.ingest_power_units --require-database "$@"
log "power-unit ingest done"
