#!/usr/bin/env python3
"""Mirror the site's web fonts into the public data directory.

Every browser then draws the same fonts no matter what the device has
installed, and visitors never depend on Google's servers being reachable.
Google Fonts already splits the CJK families into small unicode-range slices,
so a page only downloads the characters it shows.

Fonts (all SIL Open Font License 1.1):
  Geist                    interface sans
  Source Serif 4           statement serif; optical sizes cover body and headings
  Noto Sans SC / Serif SC  Chinese for the sans and serif stacks
  JetBrains Mono           code

The output directory is served by the frontend at /public/fonts/. It holds
content-addressed .woff2 files, fonts.css and manifest.json. A run builds a new
directory and swaps it in, so readers never see a half-written set.

Run it inside the backend-api container, which owns /data/public and has
outbound HTTPS (stdlib only, no installs):

  docker exec -i -u backend "$(docker compose -p xju-oj ps -q backend-api)" \\
      python3 - --output /data/public/fonts < deploy/ops/fetch-fonts.py
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request

CSS_API = "https://fonts.googleapis.com/css2"
FONT_HOST = "https://fonts.gstatic.com/"
# The CSS API only returns woff2 with unicode-range slices to modern browsers.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
FAMILIES = [
    ("Geist", "wght@400..700"),
    ("Source Serif 4", "ital,opsz,wght@0,8..60,400..700;1,8..60,400..700"),
    ("Noto Sans SC", "wght@400..700"),
    ("Noto Serif SC", "wght@400..700"),
    ("JetBrains Mono", "wght@400..700"),
]
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
UNICODE_RANGE = re.compile(r"^U\+[0-9A-F?]{1,6}(-[0-9A-F]{1,6})?(,\s*U\+[0-9A-F?]{1,6}(-[0-9A-F]{1,6})?)*$", re.I)
WEIGHT = re.compile(r"^\d{3}( \d{3})?$")


def fetch(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise SystemExit(f"refusing oversized response from {url}")
    return data


def css_url(family, axes):
    return f"{CSS_API}?family={family.replace(' ', '+')}:{axes}&display=swap"


def parse_faces(css, family):
    """Read Google's @font-face blocks, keeping only fields we re-emit after validation."""
    faces = []
    for block in re.findall(r"@font-face\s*{([^}]*)}", css):
        props = dict((key.strip().lower(), value.strip())
                     for key, value in re.findall(r"([a-zA-Z-]+)\s*:\s*([^;]+);", block))
        name = props.get("font-family", "").strip("'\"")
        style = props.get("font-style", "normal")
        weight = props.get("font-weight", "400")
        ranges = props.get("unicode-range", "")
        src = re.search(r"url\((https://[^)\s'\"]+)\)\s*format\(['\"]woff2['\"]\)", props.get("src", ""))
        if name != family or style not in ("normal", "italic") or not WEIGHT.match(weight) or not src:
            raise SystemExit(f"unexpected @font-face for {family}: {block.strip()[:200]}")
        if ranges and not UNICODE_RANGE.match(ranges):
            raise SystemExit(f"unexpected unicode-range for {family}: {ranges[:200]}")
        if not src.group(1).startswith(FONT_HOST):
            raise SystemExit(f"unexpected font host for {family}: {src.group(1)}")
        faces.append({"style": style, "weight": weight, "ranges": ranges, "url": src.group(1)})
    if not faces:
        raise SystemExit(f"no faces returned for {family}")
    return faces


def slug(family):
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def build(work_dir, url_prefix):
    rules, manifest, total, downloaded = [], [], 0, {}
    for family, axes in FAMILIES:
        faces = parse_faces(fetch(css_url(family, axes), 1024 * 1024).decode("utf-8"), family)
        for face in faces:
            name = downloaded.get(face["url"])
            if name is None:
                data = fetch(face["url"], MAX_FILE_BYTES)
                if data[:4] != b"wOF2":
                    raise SystemExit(f"not a woff2 file: {face['url']}")
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise SystemExit("font set exceeds the size budget")
                name = f"{slug(family)}-{hashlib.sha256(data).hexdigest()[:16]}.woff2"
                with open(os.path.join(work_dir, name), "wb") as handle:
                    handle.write(data)
                downloaded[face["url"]] = name
            rule = [
                "@font-face {",
                f"  font-family: '{family}';",
                f"  font-style: {face['style']};",
                f"  font-weight: {face['weight']};",
                "  font-display: swap;",
                f"  src: url('{url_prefix}{name}') format('woff2');",
            ]
            if face["ranges"]:
                rule.append(f"  unicode-range: {face['ranges']};")
            rule.append("}")
            rules.append("\n".join(rule))
        manifest.append({"family": family, "axes": axes, "faces": len(faces)})
        print(f"{family}: {len(faces)} faces", flush=True)
    header = "/* Generated by deploy/ops/fetch-fonts.py; fonts are SIL OFL 1.1. */\n"
    with open(os.path.join(work_dir, "fonts.css"), "w", encoding="utf-8") as handle:
        handle.write(header + "\n".join(rules) + "\n")
    with open(os.path.join(work_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "families": manifest, "files": len(downloaded), "bytes": total}, handle, indent=2)
    return len(downloaded), total


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", required=True, help="directory served at --url-prefix, e.g. /data/public/fonts")
    parser.add_argument("--url-prefix", default="/public/fonts/")
    args = parser.parse_args()
    output = os.path.abspath(args.output)
    parent = os.path.dirname(output)
    work_dir = tempfile.mkdtemp(prefix=".fonts-", dir=parent)
    try:
        count, total = build(work_dir, args.url_prefix)
        for name in os.listdir(work_dir):
            os.chmod(os.path.join(work_dir, name), 0o644)
        os.chmod(work_dir, 0o755)
        previous = None
        if os.path.exists(output):
            previous = f"{output}.old-{int(time.time())}"
            os.rename(output, previous)
        os.rename(work_dir, output)
        if previous:
            shutil.rmtree(previous, ignore_errors=True)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    print(f"wrote {count} font files ({total / 1024 / 1024:.1f} MiB) and fonts.css to {output}")


if __name__ == "__main__":
    sys.exit(main())
