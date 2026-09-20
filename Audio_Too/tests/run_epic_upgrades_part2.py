import sys
from pathlib import Path

# Add directories to path
BUSINESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUSINESS_ROOT / "server" / "app"))
sys.path.insert(0, str(BUSINESS_ROOT / "studio" / "audio_analysis"))

import tests.test_epic_upgrades_part2 as t

class MockMonkeypatch:
    def setattr(self, obj, name, value):
        setattr(obj, name, value)

mp = MockMonkeypatch()
t.test_generate_correction_rack(mp)
t.test_analyze_stems_masking_calculation()
t.test_handle_stems_upload_endpoint()
print("All epic upgrades part 2 unit tests passed successfully!")
