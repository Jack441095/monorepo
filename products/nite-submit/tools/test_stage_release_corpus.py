"""Release staging must use exact reviewed records, even with extra local PDFs."""

import tempfile
from pathlib import Path
import unittest

from stage_release_corpus import stage_cases, select_cases
from check_rebuilt_corpus import qualified_profiles
from restore_public_corpus import PRODUCT_DIR


class ReleaseScopeTests(unittest.TestCase):
    def test_real_qualification_excludes_intake_outputs_edges_and_unreviewed_files(self):
        profiles = qualified_profiles(PRODUCT_DIR / "real_validation_corpus")
        cases = select_cases(profiles, "all")
        self.assertEqual(len(cases), 47)
        self.assertEqual(len(select_cases(profiles, "submissions")), 9)
        self.assertEqual(len(select_cases(profiles, "guidance")), 26)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "stage"
            stage_cases(cases, destination)
            self.assertEqual(len(list(destination.iterdir())), 47)
            for item in destination.iterdir():
                self.assertNotIn(item.resolve().parent.name, {"beta_intake", "test_results", "rejected", "edge_cases"})

    def test_nonempty_destination_duplicate_names_and_empty_cases_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.pdf"
            source.write_bytes(b"source")
            case = {"pdf": str(source)}
            destination = Path(folder) / "stage"
            stage_cases([case], destination)
            for rows, output in [([case], destination), ([case, case], Path(folder)/"duplicate"), ([], Path(folder)/"empty")]:
                with self.assertRaises(ValueError):
                    stage_cases(rows, output)
            self.assertEqual(source.read_bytes(), b"source")


if __name__ == "__main__":
    unittest.main()
