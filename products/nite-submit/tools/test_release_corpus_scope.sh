#!/bin/zsh
set -euo pipefail
product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"
# Exercise the actual staging implementation and approved records.
python3 -m unittest discover -s tools -p 'test_stage_release_corpus.py'
