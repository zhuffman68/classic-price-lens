#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$task_root"
export QT_MEDIA_BACKEND=ffmpeg
export RAYON_NUM_THREADS=2
if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python -m price_lens "$@"
fi
exec python -m price_lens "$@"
