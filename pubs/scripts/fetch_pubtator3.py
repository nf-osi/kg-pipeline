#!/usr/bin/env python3
"""Fetch PubTator 3.0 full-text entity annotations.

Reads a TSV with pmcid/pmid columns, calls the PubTator3 API for each
unique PMCID/PMID pair, and saves BioC JSON to pubtator3/<PMCID>.json.
Skips papers that are already cached with valid responses.

Usage (from project root):
  python scripts/fetch_pubtator3.py
  python scripts/fetch_pubtator3.py subsets/tools-portal-pmc-derivatives-ok.tsv

See PUBTATOR_USAGE.md for API details.
"""

import argparse
import csv
import json
import os
import time
import urllib.request
from pathlib import Path

DEFAULT_INPUT = "subsets/tools-portal-pmc-permissive.tsv"


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PubTator 3.0 annotations for papers in a TSV."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=DEFAULT_INPUT,
        help=f"Input TSV with pmcid/pmid columns (default: {DEFAULT_INPUT})",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    tsv_path = base_dir / args.input
    out_dir = base_dir / "pubtator3"
    out_dir.mkdir(exist_ok=True)

    api_base = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
    delay = 0.5  # seconds between requests (well under 20 req/s limit)

    # Collect unique PMCID/PMID pairs
    seen = set()
    pairs = []
    with open(tsv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            pmcid = row["pmcid"].strip()
            pmid = row["pmid"].strip().replace("PMID:", "")
            if pmcid not in seen:
                seen.add(pmcid)
                pairs.append((pmcid, pmid))

    print(f"Found {len(pairs)} unique papers in {tsv_path.name}")

    ok, skip, err = 0, 0, 0
    for i, (pmcid, pmid) in enumerate(pairs):
        out_path = out_dir / f"{pmcid}.json"

        # Skip if already cached with a valid PubTator3 response
        if out_path.exists() and out_path.stat().st_size > 100:
            try:
                with open(out_path) as f:
                    data = json.load(f)
                if "PubTator3" in data:
                    skip += 1
                    continue
            except (json.JSONDecodeError, KeyError):
                pass  # re-fetch

        url = f"{api_base}/publications/export/biocjson?pmids={pmid}&full=true"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()

            parsed = json.loads(raw)
            if "PubTator3" not in parsed:
                print(f"  ERR  {pmcid} (PMID {pmid}) — unexpected response: {list(parsed.keys())}")
                err += 1
                continue

            with open(out_path, "wb") as f:
                f.write(raw)

            ok += 1
            size_kb = len(raw) / 1024
            print(f"  OK   {pmcid} (PMID {pmid}) — {size_kb:.1f} KB [{i+1}/{len(pairs)}]")

        except Exception as e:
            print(f"  ERR  {pmcid} (PMID {pmid}) — {e}")
            err += 1

        time.sleep(delay)

    print(f"\nDone: {ok} fetched, {skip} cached, {err} errors — {ok+skip+err}/{len(pairs)} total")


if __name__ == "__main__":
    main()
