#!/usr/bin/env python3
"""Fail if any page would ship a broken or expiring image.

Three failure modes have actually bitten this site, and this guards all three:

1. Remote hotlinks. Stitch emits image URLs on lh3.googleusercontent.com; the
   /aida/ form is session-scoped and expires to 403. Pasting Stitch HTML
   verbatim silently plants images with a countdown on them.
2. Dangling local paths. An image moved or never committed is just as broken
   as an expired URL, and passes any check that only greps for http.
3. References that escape the deploy root. A path can resolve perfectly on
   disk and still 404 in production, because the browser cannot climb above
   the deployed directory - `../assets/x.jpg` from a top-level page becomes
   `/assets/x.jpg`, which only exists if it is inside DEPLOY_ROOT. This is
   not hypothetical: the whole site 404'd its images this way while a
   repo-only check reported everything fine.

DEPLOY_ROOT below must match Vercel's "Root Directory" setting. If that
setting ever changes, change this with it or the check goes blind again.

Only image references are inspected - <img src> and CSS url(...). Remote
stylesheets, fonts and scripts are none of this script's business.

    python tools/check_images.py

Exits non-zero and prints every offending file:line on failure.
"""

import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The directory Vercel actually deploys, relative to the repo - currently the
# project's Root Directory is "app". "" would mean the repo root. Anything a
# deployed page references must resolve inside here, or it 404s in production
# no matter how well it resolves on a developer's disk.
#
# Keep this in step with Vercel. If Root Directory is ever cleared, set this
# to "" (and app/ can then be deleted outright).
DEPLOY_ROOT_REL = "app"
DEPLOY_ROOT = os.path.normpath(os.path.join(REPO, DEPLOY_ROOT_REL))

# Archived raw Stitch exports, kept as a historical record of what was
# delivered. They are never served, and rewriting them would defeat the point.
EXEMPT_DIRS = {"redesign_html", "unpacked_stitch", "stitch_downloads"}

IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I | re.S)
CSS_URL_RE = re.compile(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", re.I)
REMOTE_RE = re.compile(r"^(https?:)?//", re.I)


def html_files():
    """Tracked HTML only - the guard polices what ships, not local scratch."""
    out = subprocess.run(
        ["git", "ls-files", "*.html"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for rel in out.splitlines():
        if not rel.strip():
            continue
        if rel.split("/")[0] in EXEMPT_DIRS:
            continue
        path = os.path.join(REPO, rel.replace("/", os.sep))
        if os.path.isfile(path):
            yield path


def refs(text):
    """Yield (line_number, reference) for every image reference."""
    for i, line in enumerate(text.splitlines(), 1):
        for m in IMG_SRC_RE.finditer(line):
            yield i, m.group(1)
        for m in CSS_URL_RE.finditer(line):
            yield i, m.group(1)


def main():
    remote, dangling, escaped = [], [], []

    for path in sorted(html_files()):
        rel = os.path.relpath(path, REPO).replace(os.sep, "/")
        text = open(path, encoding="utf-8", errors="replace").read()

        for line_no, ref in refs(text):
            if ref.startswith("data:"):
                continue

            if REMOTE_RE.match(ref):
                remote.append((rel, line_no, ref))
                continue

            # Pages outside the deploy root are not served, so the escape rule
            # cannot apply to them - but their paths must still resolve.
            deployed = os.path.commonpath([DEPLOY_ROOT, path]) == DEPLOY_ROOT
            root_for_abs = DEPLOY_ROOT if deployed else REPO

            base = root_for_abs if ref.startswith("/") else os.path.dirname(path)
            target = os.path.normpath(os.path.join(base, ref.lstrip("/").split("?")[0]))

            # A ../ that climbs past the deploy root resolves fine on disk but
            # is unreachable over HTTP - the browser clamps it at the root.
            if deployed and os.path.commonpath([DEPLOY_ROOT, target]) != DEPLOY_ROOT:
                escaped.append((rel, line_no, ref))
                continue

            if not os.path.isfile(target):
                dangling.append((rel, line_no, ref))

    if remote:
        print(f"FAIL: {len(remote)} remote image reference(s) - these can expire\n")
        for rel, line_no, ref in remote:
            print(f"  {rel}:{line_no}\n    {ref[:100]}")
        print(
            "\n  Run:  python tools/localize_images.py <file>"
            "\n  That downloads each image into assets/img/ and rewrites the path."
        )

    if escaped:
        if remote:
            print()
        print(
            f"FAIL: {len(escaped)} image reference(s) escape the deploy root\n"
            "      (these resolve on disk but 404 in production)\n"
        )
        for rel, line_no, ref in escaped:
            print(f"  {rel}:{line_no}\n    {ref}")
        print(
            f"\n  Deploy root is {DEPLOY_ROOT!r} - a browser cannot climb above it."
            "\n  Move the asset inside the deploy root, or fix the path."
        )

    if dangling:
        if remote or escaped:
            print()
        print(f"FAIL: {len(dangling)} image reference(s) point at a missing file\n")
        for rel, line_no, ref in dangling:
            print(f"  {rel}:{line_no}\n    {ref}")
        print("\n  The file was moved, renamed, or never committed.")

    if remote or dangling or escaped:
        return 1

    checked = sum(1 for _ in html_files())
    print(f"OK: all image references in {checked} HTML file(s) are local and resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
