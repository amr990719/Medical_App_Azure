"""`ready` must not be claimable from a partly filled record."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure" / "scripts"))

import acceptance_record as record  # noqa: E402

EARLY_PASS = "| AUTH-1 | before-admin | sign-in | PASS | run 12, 2026-11-05 |"
LATE_PENDING = "| CUT-1 | after-cutover | final host | PENDING | |"


class Record(unittest.TestCase):
    def open_items(self, *lines, stage="all"):
        return record.problems(record.read_rows("\n".join(lines)), stage)

    def test_all_pass_with_evidence_is_clean(self):
        self.assertEqual(self.open_items(EARLY_PASS, stage="before-admin"), [])

    def test_pending_is_open(self):
        self.assertEqual(self.open_items(EARLY_PASS, LATE_PENDING), ["CUT-1: PENDING"])

    def test_a_later_stage_does_not_block_an_earlier_one(self):
        self.assertEqual(self.open_items(EARLY_PASS, LATE_PENDING, stage="before-cutover"), [])

    def test_an_earlier_stage_blocks_a_later_one(self):
        items = self.open_items("| AUTH-1 | before-admin | x | PENDING | |", stage="after-cutover")
        self.assertEqual(items, ["AUTH-1: PENDING"])

    def test_a_failure_is_open(self):
        self.assertEqual(self.open_items("| PAY-1 | before-cutover | x | FAIL | bug 3 |")[0], "PAY-1: FAIL")

    def test_a_pass_without_evidence_is_open(self):
        for evidence in ("", "-"):
            line = f"| PAY-1 | before-cutover | x | PASS | {evidence} |"
            self.assertEqual(self.open_items(line), ["PAY-1: PASS without evidence"])

    def test_an_unreadable_record_is_never_clean(self):
        self.assertTrue(self.open_items("nothing here"))
        self.assertTrue(self.open_items("| AUTH-1 | someday | x | PASS | y |"))

    def test_a_repeated_id_is_open(self):
        self.assertIn("AUTH-1: listed twice", self.open_items(EARLY_PASS, EARLY_PASS))

    def test_the_committed_record_parses_and_is_not_claimed_ready(self):
        rows = record.read_rows((ROOT / "docs" / "production-acceptance.md").read_text("utf-8"))
        self.assertGreater(len(rows), 25)
        self.assertEqual({row.stage for row in rows} - set(record.STAGES), set())
        self.assertTrue(record.problems(rows, "all"), "nothing on Azure has been checked yet")


if __name__ == "__main__":
    unittest.main()
