"""Add a real log + metadata to the curated corpus (with QA gating).

Run:  PYTHONPATH=src python3 scripts/add_log_to_corpus.py <log.csv> <metadata.yaml> [--force]
"""

from __future__ import annotations

import argparse
import json
import sys

from dynamis.data.corpus import CorpusMeta, add_log


def main() -> int:
    ap = argparse.ArgumentParser(description="Add a log to the curated corpus.")
    ap.add_argument("csv", help="path to the raw log CSV")
    ap.add_argument("metadata", help="path to the metadata YAML (see configs/metadata_template.yaml)")
    ap.add_argument("--corpus-dir", default="data/corpus")
    ap.add_argument("--force", action="store_true", help="add even if QA finds problems")
    args = ap.parse_args()

    meta = CorpusMeta.from_yaml(args.metadata)
    res = add_log(args.csv, meta, corpus_dir=args.corpus_dir, force=args.force)

    print(f"entry_id: {res.entry_id}")
    print("\nQA report:")
    print(json.dumps(res.qa, indent=2, default=str))
    if res.warnings:
        print("\nmetadata warnings:")
        for w in res.warnings:
            print(f"  - {w}")
    if res.problems:
        print("\nQA problems:")
        for p in res.problems:
            print(f"  - {p}")

    if res.ok:
        print(f"\nADDED -> {res.path}")
        return 0
    print("\nNOT ADDED (QA failed). Re-run with --force to override.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
