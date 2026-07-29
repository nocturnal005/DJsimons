#!/usr/bin/env python3
"""Download every remote Stitch image referenced by the site and rewrite the
HTML to point at local copies.

Stitch emits two kinds of image URL on lh3.googleusercontent.com:

  /aida-public/AB6AXu...   persistent published assets
  /aida/AP1WRL...          session-scoped preview URLs, which expire to 403

Hotlinking either is fragile; the second kind is a guaranteed future outage.
Run this against any freshly exported Stitch HTML *while the URLs are still
alive* to pull the images into assets/img/ and repoint the markup at them.

    python tools/localize_images.py                  # all root pages
    python tools/localize_images.py app/index.html   # specific files

Re-running is safe: already-downloaded images are left alone, and rewritten
references are ignored on later passes.
"""

import hashlib
import os
import re
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = os.path.join(REPO, "assets", "img")

DEFAULT_PAGES = [
    "index.html",
    "mouldings.html",
    "boards.html",
    "machinery.html",
    "chop-service.html",
    "technical-data.html",
    "sundries.html",
]

URL_RE = re.compile(r"https://lh3\.googleusercontent\.com/[^\"')\s]+")

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}

# Recover a human-readable name from the alt="" (or the nearest heading) that
# sits alongside the URL, so the asset folder stays browsable.
ALT_RE = re.compile(r'alt="([^"]*)"')


def slugify(text, fallback="image"):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or fallback


def label_for(url, sources):
    """Best-effort human label for a URL, from alt text on the same line."""
    for text in sources:
        for line in text.splitlines():
            if url in line:
                alt = ALT_RE.search(line)
                if alt and alt.group(1).strip():
                    return slugify(alt.group(1))
                if "background-image" in line:
                    return "background"
    return "image"


def download(url, dest_base):
    """Fetch url; return the filename written, or None on failure."""
    req = urllib.request.Request(
        url,
        headers={
            # Plain urllib gets refused by the CDN; mimic a browser fetch.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        data = resp.read()

    ext = EXT_BY_TYPE.get(ctype)
    if ext is None:
        if not ctype.startswith("image/"):
            raise ValueError(f"not an image (Content-Type: {ctype or 'unknown'})")
        ext = "." + ctype.split("/", 1)[1]

    name = dest_base + ext
    with open(os.path.join(ASSET_DIR, name), "wb") as fh:
        fh.write(data)
    return name


def main(argv):
    pages = argv[1:] or DEFAULT_PAGES
    paths = [os.path.join(REPO, p) for p in pages]

    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        sys.exit("no such file: " + ", ".join(missing))

    os.makedirs(ASSET_DIR, exist_ok=True)

    contents = {p: open(p, encoding="utf-8").read() for p in paths}

    urls = []
    for text in contents.values():
        for url in URL_RE.findall(text):
            if url not in urls:
                urls.append(url)

    if not urls:
        print("No remote Stitch images found - nothing to do.")
        return 0

    print(f"Found {len(urls)} unique remote image(s) across {len(paths)} page(s).\n")

    # url -> local filename, for the URLs we successfully pulled down.
    localized = {}
    failed = []

    for url in urls:
        digest = hashlib.sha1(url.encode()).hexdigest()[:8]
        base = f"{label_for(url, contents.values())}-{digest}"

        existing = next(
            (f for f in os.listdir(ASSET_DIR) if os.path.splitext(f)[0] == base), None
        )
        if existing:
            localized[url] = existing
            print(f"  cached  {existing}")
            continue

        try:
            name = download(url, base)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError) as exc:
            code = getattr(exc, "code", None)
            reason = f"HTTP {code}" if code else str(exc)
            # 403 here means an /aida/ preview URL has expired past recovery.
            failed.append((url, reason))
            print(f"  FAILED  {reason:<12} {base}")
            continue

        localized[url] = name
        print(f"  saved   {name}")

    # Rewrite references only for images we actually hold locally, so a failed
    # download leaves the original URL untouched rather than creating a 404.
    print()
    for path, text in contents.items():
        updated = text
        hits = 0
        for url, name in localized.items():
            rel = os.path.relpath(
                os.path.join(ASSET_DIR, name), os.path.dirname(path)
            ).replace(os.sep, "/")
            if url in updated:
                hits += updated.count(url)
                updated = updated.replace(url, rel)
        if updated != text:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(updated)
        print(f"  {os.path.relpath(path, REPO)}: {hits} reference(s) repointed")

    print(f"\nLocalized {len(localized)}/{len(urls)} image(s).")
    if failed:
        print(f"\n{len(failed)} image(s) could not be fetched and still point at Google:")
        for url, reason in failed:
            print(f"  {reason:<12} {url[:96]}...")
        print(
            "\nExpired /aida/ URLs are unrecoverable - re-export the project from "
            "Stitch and re-run this script while the new URLs are live."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
