#!/usr/bin/env bash
# docker compose for the f1ai stack, with the env file and the deployed image
# tag filled in (compose.yaml says why). Any compose arguments work:
#
#   bin/compose.sh ps
#   bin/compose.sh logs -f --since 1h api
#   bin/compose.sh restart api
#   bin/compose.sh --profile jobs run --rm jobs python -m scripts.backfill_predictions
#
# Run as the deploy user (or root). To change the image, use deploy.sh: it
# checks the new one and rolls back on failure; `up` here does not.
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

compose "$@"
