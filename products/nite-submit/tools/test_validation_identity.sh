#!/bin/zsh
set -euo pipefail
product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=$(tr -d '[:space:]' < "$product_dir/VERSION")
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
python3 - "$cli" "$product_dir" <<'PY'
import json
from pathlib import Path
import subprocess
import sys
import tempfile
with tempfile.TemporaryDirectory() as folder:
    manifest=Path(folder)/'manifest.json'
    report=Path(folder)/'report.json'
    identity='CONTROLLED_IDENTITY_REGRESSION'
    manifest.write_text(json.dumps({'corpus_id':identity,'cases':[{'id':'layout','pdf':str(Path(sys.argv[2])/'Sources/NiteSubmitTests/Fixtures/corpus/pdf/clear_000.pdf'),'truth':{},'evaluation_mode':'layout_only'}]}))
    subprocess.run([sys.argv[1],'validate','--manifest',str(manifest),'--out',str(report)],check=True,stdout=subprocess.DEVNULL)
    result=json.loads(report.read_text())
    assert result['corpus_id']==identity and result['processed']==1
    assert 'pdf' not in result and 'cases' not in result
print('Validation identity and aggregate privacy passed')
PY
