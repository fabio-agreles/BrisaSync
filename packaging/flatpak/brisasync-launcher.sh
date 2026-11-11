#!/usr/bin/env sh
set -e

export PYTHONPATH="/app/lib/brisasync/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="/app/lib/brisasync/bin:/app/bin:${PATH}"

exec python3 -m brisasync.main "$@"

