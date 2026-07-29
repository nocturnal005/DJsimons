"""Download every generated image asset from the Stitch project.

The image URLs embedded in Stitch's stored HTML have expired exactly as they
did on the live site. But each screen's `screenshot.downloadUrl` is minted
fresh on every get_screen call, so the original 1024x1024 artwork is still
fully recoverable through the API.

Writes JPEGs to ./stitch_assets/ plus a catalog.json mapping each file to the
prompt that generated it (which is what we match against the site's alt text).
"""

import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stitch import call  # noqa: E402
from fetch_screens import retry, PID  # noqa: E402

OUT = os.path.join(HERE, "stitch_assets")
CATALOG = os.path.join(HERE, "catalog.json")
os.makedirs(OUT, exist_ok=True)


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        ctype = r.headers.get("Content-Type", "")
        data = r.read()
    if not ctype.startswith("image/"):
        raise ValueError(f"not an image: {ctype}")
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


def main():
    listing = retry(lambda: call("list_screens", {"projectId": PID}))
    screens = listing.get("screens", []) if isinstance(listing, dict) else listing

    # Page designs are full-page renders, not reusable art; skip them.
    assets = [s for s in screens if not (s.get("title") or "").startswith("DJ Simons")]
    print(f"{len(assets)} image screens to pull\n")

    catalog = {}
    if os.path.exists(CATALOG):
        catalog = json.load(open(CATALOG, encoding="utf-8"))

    ok = skipped = failed = 0
    for i, s in enumerate(assets, 1):
        sid = s["name"].split("/")[-1]
        path = os.path.join(OUT, sid + ".jpg")

        if os.path.exists(path) and sid in catalog:
            skipped += 1
            continue

        try:
            meta = retry(
                lambda: call(
                    "get_screen",
                    {
                        "name": f"projects/{PID}/screens/{sid}",
                        "projectId": PID,
                        "screenId": sid,
                    },
                )
            )
            if isinstance(meta, list):
                meta = meta[0]
            url = (meta.get("screenshot") or {}).get("downloadUrl")
            if not url:
                raise ValueError("no screenshot url")
            size = retry(lambda: download(url, path))
            catalog[sid] = {
                "title": meta.get("title", ""),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "bytes": size,
            }
            ok += 1
            if i % 10 == 0 or ok <= 3:
                print(f"  [{i}/{len(assets)}] {size:>7}b  {meta.get('title','')[:64]}")
        except Exception as exc:
            failed += 1
            print(f"  [{i}] FAIL {str(exc)[:44]}  {(s.get('title') or '')[:50]}")

        # Checkpoint so a mid-run failure doesn't lose progress.
        if ok and ok % 15 == 0:
            json.dump(catalog, open(CATALOG, "w", encoding="utf-8"), indent=1)
        time.sleep(0.35)

    json.dump(catalog, open(CATALOG, "w", encoding="utf-8"), indent=1)
    print(f"\ndownloaded {ok}, cached {skipped}, failed {failed}")
    print(f"catalog: {len(catalog)} entries -> {CATALOG}")


if __name__ == "__main__":
    main()
