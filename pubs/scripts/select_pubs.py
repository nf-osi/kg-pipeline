#!/usr/bin/env python3
"""Select publications by license set.

Reads tools-portal-pmc-with-licenses.tsv and writes a filtered subset.

License sets:
  --permissive       CC-BY, CC-BY-4.0, Public Domain (124 papers)
  --derivatives-ok   Adds CC-BY-NC, CC-BY-NC-SA — allows derivatives,
                     restricts commercial use (139 papers)

Examples (from project root):
  python scripts/select_pubs.py --permissive
  python scripts/select_pubs.py --derivatives-ok
  python scripts/select_pubs.py --analyze
  python scripts/select_pubs.py --permissive -o subsets/my_subset.tsv
"""

import argparse
import csv
import sys
from collections import Counter

INPUT_FILE = "subsets/tools-portal-pmc-with-licenses.tsv"

PERMISSIVE = {"CC-BY", "CC-BY-4.0", "Public Domain"}
DERIVATIVES_OK = PERMISSIVE | {"CC-BY-NC", "CC-BY-NC-SA"}

SETS = {
    "permissive": PERMISSIVE,
    "derivatives-ok": DERIVATIVES_OK,
}


def analyze(all_records):
    """Show license distribution and set membership."""
    total = len(all_records)
    all_license_counts = Counter(r["license"] for r in all_records)

    print(f"Total publications: {total}")
    print()

    # Per-license breakdown with set membership
    print(f"  {'License':<40} {'Count':>5} {'%':>6}   Sets")
    print(f"  {'-'*40} {'-'*5} {'-'*6}   {'-'*25}")
    for lic, count in all_license_counts.most_common():
        pct = count * 100 / total
        member_of = [name for name, lics in SETS.items() if lic in lics]
        sets_str = ", ".join(member_of) if member_of else ""
        print(f"  {lic:<40} {count:>5} {pct:>5.1f}%   {sets_str}")
    print()

    # Set sizes
    print("Defined sets:")
    for name, lics in SETS.items():
        count = sum(1 for r in all_records if r.get("license") in lics)
        ft = sum(
            1 for r in all_records
            if r.get("license") in lics and r.get("has_fulltext") == "Yes"
        )
        print(f"  --{name:<20} {count:>4} papers ({ft} with full-text)")
        for lic in sorted(lics):
            lcount = all_license_counts.get(lic, 0)
            print(f"    {lic:<38} {lcount:>5}")


def select(args, license_set, set_name):
    """Filter and write selected publications."""
    output_file = args.output or f"subsets/tools-portal-pmc-{set_name}.tsv"

    # Read
    with open(args.input, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = reader.fieldnames
        all_records = list(reader)

    # Filter
    selected = [r for r in all_records if r.get("license") in license_set]

    # Write
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(selected)

    # Report
    print(f"Input:  {args.input} ({len(all_records)} publications)")
    print(f"Set:    --{set_name}")
    print(f"Output: {output_file} ({len(selected)} publications)")
    print()

    # All licenses in input
    all_license_counts = Counter(r["license"] for r in all_records)
    print("All licenses in input:")
    for lic, count in all_license_counts.most_common():
        tag = " <-- included" if lic in license_set else ""
        print(f"  {count:3d}  {lic}{tag}")
    print()

    # Selected breakdown
    selected_license_counts = Counter(r["license"] for r in selected)
    excluded_count = len(all_records) - len(selected)
    print(f"Selected: {len(selected)} ({len(selected) * 100 / len(all_records):.1f}%)")
    print(f"Excluded: {excluded_count} ({excluded_count * 100 / len(all_records):.1f}%)")
    print()

    print("Selected license breakdown:")
    for lic, count in selected_license_counts.most_common():
        print(f"  {count:3d}  {lic}")

    fulltext_count = sum(
        1 for r in selected if r.get("has_fulltext") == "Yes"
    )
    print()
    print(f"With full-text: {fulltext_count} ({fulltext_count * 100 / len(selected):.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Select publications by license set."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--permissive",
        action="store_true",
        help="CC-BY, CC-BY-4.0, Public Domain",
    )
    group.add_argument(
        "--derivatives-ok",
        action="store_true",
        help="Permissive + CC-BY-NC, CC-BY-NC-SA (allows derivatives)",
    )
    group.add_argument(
        "--analyze",
        action="store_true",
        help="Show license distributions and set sizes (no output file)",
    )
    parser.add_argument(
        "-i",
        "--input",
        default=INPUT_FILE,
        help=f"Input TSV (default: {INPUT_FILE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output TSV (default: tools-portal-pmc-<set>.tsv)",
    )
    args = parser.parse_args()

    if args.analyze:
        with open(args.input, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            all_records = list(reader)
        analyze(all_records)
    elif args.permissive:
        select(args, PERMISSIVE, "permissive")
    else:
        select(args, DERIVATIVES_OK, "derivatives-ok")


if __name__ == "__main__":
    main()
