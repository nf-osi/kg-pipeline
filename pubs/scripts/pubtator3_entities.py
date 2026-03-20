#!/usr/bin/env python3
"""Export unique entities from PubTator3 annotations to a TSV file.

Scans pubtator3/*.json and writes one row per unique entity with:
- type, identifier, name, database, mention_count, paper_count, pmcids

Output: subsets/pubtator3_entities.tsv

See PUBTATOR_USAGE.md for context.
"""

import csv
import json
import os
from collections import defaultdict
from pathlib import Path


def main():
    pub_dir = Path(__file__).resolve().parent.parent / "pubtator3"
    out_path = Path(__file__).resolve().parent.parent / "subsets" / "pubtator3_entities.tsv"

    # Keyed by (type, identifier)
    entities: dict[tuple[str, str], dict] = {}

    for fname in sorted(os.listdir(pub_dir)):
        if not fname.endswith(".json"):
            continue
        pmcid = fname.replace(".json", "")
        path = pub_dir / fname

        with open(path) as f:
            data = json.load(f)

        for pub in data.get("PubTator3", []):
            for passage in pub.get("passages", []):
                for ann in passage.get("annotations", []):
                    t = ann["infons"].get("type", "UNKNOWN")
                    identifier = ann["infons"].get("identifier", "")
                    name = ann["infons"].get("name", ann.get("text", ""))
                    database = ann["infons"].get("database", "")

                    key = (t, identifier)
                    if key not in entities:
                        entities[key] = {
                            "type": t,
                            "identifier": identifier,
                            "name": name,
                            "database": database,
                            "mention_count": 0,
                            "pmcids": set(),
                        }
                    entities[key]["mention_count"] += 1
                    entities[key]["pmcids"].add(pmcid)
                    # Prefer non-empty name
                    if not entities[key]["name"] and name:
                        entities[key]["name"] = name

    # Sort by type then descending mention count
    rows = sorted(
        entities.values(),
        key=lambda r: (r["type"], -r["mention_count"]),
    )

    fieldnames = [
        "type",
        "identifier",
        "name",
        "database",
        "mention_count",
        "paper_count",
        "pmcids",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "type": row["type"],
                    "identifier": row["identifier"],
                    "name": row["name"],
                    "database": row["database"],
                    "mention_count": row["mention_count"],
                    "paper_count": len(row["pmcids"]),
                    "pmcids": ",".join(sorted(row["pmcids"])),
                }
            )

    type_counts = defaultdict(int)
    for r in rows:
        type_counts[r["type"]] += 1

    print(f"Wrote {len(rows):,} unique entities to {out_path.name}")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count:,}")


if __name__ == "__main__":
    main()
