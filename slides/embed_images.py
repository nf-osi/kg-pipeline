#!/usr/bin/env python3
"""Embed local images as base64 data URIs to produce a standalone HTML file."""

import argparse
import base64
import mimetypes
import os
import re
import sys


def embed_images(html_path: str, output_path: str | None = None) -> str:
    base_dir = os.path.dirname(os.path.abspath(html_path))

    with open(html_path) as f:
        html = f.read()

    def replace_src(match):
        src = match.group(1)
        if src.startswith("data:") or src.startswith("http://") or src.startswith("https://"):
            return match.group(0)
        img_path = os.path.join(base_dir, src)
        if not os.path.exists(img_path):
            print(f"  WARNING: {src} not found, skipping", file=sys.stderr)
            return match.group(0)
        mime, _ = mimetypes.guess_type(img_path)
        mime = mime or "image/png"
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        print(f"  Embedded: {src} ({len(b64) // 1024} KB)")
        return f'src="data:{mime};base64,{b64}"'

    result = re.sub(r'src="([^"]+)"', replace_src, html)

    if output_path is None:
        stem, ext = os.path.splitext(html_path)
        output_path = f"{stem}_standalone{ext}"

    with open(output_path, "w") as f:
        f.write(result)

    print(f"Output: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_file", help="HTML file to process")
    parser.add_argument("-o", "--output", help="Output path (default: <stem>_standalone.html)")
    args = parser.parse_args()

    embed_images(args.html_file, args.output)
