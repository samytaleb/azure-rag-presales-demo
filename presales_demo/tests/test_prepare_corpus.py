"""Verify the documented Markdown-to-TXT staging workflow."""
import tempfile
import unittest
from pathlib import Path

from presales_demo.prepare_corpus import stage


class StagingTests(unittest.TestCase):
    def test_stage_is_idempotent_and_safe(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "docs"
            first = stage(dest)
            self.assertEqual(len(first), 4)
            self.assertTrue(all(state == "staged" for _, state in first))
            self.assertTrue((dest / "01-product.txt").read_text().startswith("# MeridianOps"))
            again = stage(dest)
            self.assertEqual(len(again), 4)
            self.assertTrue(all(state == "unchanged" for _, state in again))

            changed = dest / "01-product.txt"
            changed.write_text("tampered example", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                stage(dest)
            stage(dest, overwrite=True)
            self.assertTrue(changed.read_text().startswith("# MeridianOps"))

    def test_reject_non_regular_destination(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            (dest / "01-product.txt").mkdir()
            with self.assertRaises(ValueError):
                stage(dest)


if __name__ == "__main__":
    unittest.main()
