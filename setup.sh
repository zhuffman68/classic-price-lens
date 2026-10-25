#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$task_root"
if [[ ! -d vendor/minerva/.git ]]; then
    git clone https://github.com/itechify/minerva.git vendor/minerva
    git -C vendor/minerva checkout --detach 7e1aa7d418fb255bd66eb4dce848fc9eb305cd81
fi
if [[ $(git -C vendor/minerva rev-parse HEAD) != 7e1aa7d418fb255bd66eb4dce848fc9eb305cd81 ]]; then
    printf '%s\n' 'Unexpected Minerva revision. Keep the pinned core before building.' >&2
    exit 1
fi
cargo build --locked --manifest-path reader/Cargo.toml -j 2
python -c 'import PySide6.QtMultimedia' || printf '%s\n' 'Install PySide6 (pip install -r requirements.txt, or python-pyside6 from your package manager).'
