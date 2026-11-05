#!/usr/bin/env python3
"""Reads the acceptance table of docs/production-acceptance.md and says what is still open.

    acceptance_record.py docs/production-acceptance.md --stage before-cutover
    acceptance_record.py docs/production-acceptance.md --stage all

A row is `| ID | stage | check | status | evidence |`, with the status PASS, FAIL or PENDING. Exit 0
only when every row of the requested stages is PASS and has evidence, so "ready" cannot be claimed
from a partly filled record. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Stages in the order they happen; a stage also requires the stages before it.
STAGES = ("before-admin", "before-cutover", "after-cutover", "before-live")
ROW = re.compile(
    r"^\|\s*(?P<id>[A-Z]+-\d+)\s*\|\s*(?P<stage>[a-z-]+)\s*\|(?P<check>.*?)\|"
    r"\s*(?P<status>[A-Z]+)\s*\|(?P<evidence>.*?)\|\s*$"
)


@dataclass(frozen=True)
class Row:
    id: str
    stage: str
    status: str
    evidence: str


def read_rows(text: str) -> list[Row]:
    rows = []
    for line in text.splitlines():
        match = ROW.match(line)
        if match:
            rows.append(
                Row(
                    match["id"],
                    match["stage"],
                    match["status"],
                    match["evidence"].strip(),
                )
            )
    return rows


def problems(rows: list[Row], stage: str) -> list[str]:
    found = []
    unknown = sorted({row.stage for row in rows} - set(STAGES))
    if unknown:
        found.append(f"unknown stage(s): {', '.join(unknown)}")
    wanted = STAGES if stage == "all" else STAGES[: STAGES.index(stage) + 1]
    seen = set()
    for row in rows:
        if row.id in seen:
            found.append(f"{row.id}: listed twice")
        seen.add(row.id)
        if row.stage not in wanted:
            continue
        if row.status != "PASS":
            found.append(f"{row.id}: {row.status}")
        elif not row.evidence or row.evidence == "-":
            found.append(f"{row.id}: PASS without evidence")
    if not any(row.stage in wanted for row in rows):
        found.append(f"no rows for {stage}: the record is unreadable or empty")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("record")
    parser.add_argument("--stage", default="all", choices=[*STAGES, "all"])
    args = parser.parse_args(argv)

    rows = read_rows(Path(args.record).read_text(encoding="utf-8"))
    open_items = problems(rows, args.stage)
    for item in open_items:
        print(f"OPEN {item}")
    print(f"acceptance record: {len(rows)} rows, {len(open_items)} open for stage '{args.stage}'")
    return 1 if open_items else 0


if __name__ == "__main__":
    sys.exit(main())
