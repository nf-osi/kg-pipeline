#!/usr/bin/env python3
"""Print entity annotation stats across all PubTator3 JSON files.

Scans pubtator3/*.json and reports:
- Total files and annotations
- Per-entity-type counts with examples
- Files with no annotations (if any)

See PUBTATOR_USAGE.md for context.
"""

import json
import os
from collections import Counter
from pathlib import Path

import tiktoken

# o200k_harmony covers gpt-4.1, o3, o4-mini
ENCODING = tiktoken.get_encoding("o200k_harmony")


def count_tokens(text: str) -> int:
    """Count tokens using the cl100k_base BPE tokenizer."""
    return len(ENCODING.encode(text))


def main():
    pub_dir = Path(__file__).resolve().parent.parent / "pubtator3"

    entity_types = Counter()
    entity_ids: dict[str, set[str]] = {}
    entity_examples: dict[str, list[str]] = {}
    total_annotations = 0
    total_files = 0
    files_with_no_annotations = []

    for fname in sorted(os.listdir(pub_dir)):
        if not fname.endswith(".json"):
            continue
        total_files += 1
        path = pub_dir / fname

        with open(path) as f:
            data = json.load(f)

        file_anns = 0
        for pub in data.get("PubTator3", []):
            for passage in pub.get("passages", []):
                for ann in passage.get("annotations", []):
                    total_annotations += 1
                    file_anns += 1
                    t = ann["infons"].get("type", "UNKNOWN")
                    entity_types[t] += 1

                    identifier = ann["infons"].get("identifier", "?")
                    entity_ids.setdefault(t, set()).add(identifier)

                    name = ann["infons"].get("name", ann.get("text", "?"))
                    db = ann["infons"].get("database", "?")
                    if t not in entity_examples:
                        entity_examples[t] = []
                    if len(entity_examples[t]) < 3:
                        entity_examples[t].append(f"{name} ({db}: {identifier})")

        if file_anns == 0:
            files_with_no_annotations.append(fname)

    print(f"Files:             {total_files}")
    print(f"Total annotations: {total_annotations:,}")
    print(f"No annotations:    {len(files_with_no_annotations)}")
    if files_with_no_annotations:
        for f in files_with_no_annotations:
            print(f"  - {f}")
    print()

    print("Entity types:")
    for t, count in entity_types.most_common():
        unique = len(entity_ids.get(t, set()))
        print(f"  {t}: {count:,} mentions, {unique:,} unique")
        for ex in entity_examples.get(t, []):
            print(f"    e.g. {ex}")
    print()

    # Token distribution across passages
    print("Token distribution across passages (tiktoken o200k_harmony):")
    all_lengths = []
    section_lengths: dict[str, list[int]] = {}

    for fname in sorted(os.listdir(pub_dir)):
        if not fname.endswith(".json"):
            continue
        path = pub_dir / fname
        with open(path) as f:
            data = json.load(f)
        for pub in data.get("PubTator3", []):
            for passage in pub.get("passages", []):
                st = passage["infons"].get(
                    "section_type", passage["infons"].get("type", "?")
                )
                n_tokens = count_tokens(passage.get("text", ""))
                all_lengths.append(n_tokens)
                section_lengths.setdefault(st, []).append(n_tokens)

    all_lengths.sort()
    n = len(all_lengths)
    print(f"  Total passages: {n:,}")
    print(
        f"  min={all_lengths[0]}  p25={all_lengths[n // 4]}  "
        f"median={all_lengths[n // 2]}  p75={all_lengths[3 * n // 4]}  "
        f"p95={all_lengths[int(n * 0.95)]}  max={all_lengths[-1]}  "
        f"mean={sum(all_lengths) / n:.1f}"
    )
    print()

    header = f"  {'section_type':<20} {'count':>6} {'min':>6} {'p25':>6} {'median':>6} {'p75':>6} {'max':>6} {'mean':>6}"
    print(header)
    print(f"  {'-' * 20} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6}")
    for st in sorted(section_lengths, key=lambda s: -len(section_lengths[s])):
        vals = sorted(section_lengths[st])
        m = len(vals)
        print(
            f"  {st:<20} {m:>6} {vals[0]:>6} {vals[m // 4]:>6} "
            f"{vals[m // 2]:>6} {vals[3 * m // 4]:>6} {vals[-1]:>6} "
            f"{sum(vals) / m:>6.0f}"
        )
    print()

    # Per-file summary
    print("Per-file breakdown:")
    print(f"  {'File':<25} {'Total':>7} {'Gene':>7} {'Disease':>7} {'Chemical':>7} {'Species':>7} {'CellLine':>8} {'Variant':>7}")
    print(f"  {'-'*25} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*7}")

    for fname in sorted(os.listdir(pub_dir)):
        if not fname.endswith(".json"):
            continue
        path = pub_dir / fname
        with open(path) as f:
            data = json.load(f)

        counts: dict[str, int] = Counter()
        for pub in data.get("PubTator3", []):
            for passage in pub.get("passages", []):
                for ann in passage.get("annotations", []):
                    counts[ann["infons"].get("type", "?")] += 1

        total = sum(counts.values())
        pmcid = fname.replace(".json", "")
        print(
            f"  {pmcid:<25} {total:>7} {counts.get('Gene',0):>7} "
            f"{counts.get('Disease',0):>7} {counts.get('Chemical',0):>7} "
            f"{counts.get('Species',0):>7} {counts.get('CellLine',0):>8} "
            f"{counts.get('Variant',0):>7}"
        )


if __name__ == "__main__":
    main()
