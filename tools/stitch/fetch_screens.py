"""Pull every screen's HTML out of the Stitch project and cache it locally.

The API is intermittently flaky ("Request contains an invalid argument" on
calls that succeed on retry), so each screen is retried and cached to disk;
re-running only fetches what is missing.
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stitch import call  # noqa: E402

PID = "17943241542421482918"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")
os.makedirs(CACHE, exist_ok=True)


def retry(fn, tries=4, delay=2.0):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(delay * (i + 1))


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf8", "replace")


def screen_html(sid):
    """Return cached HTML for a screen, downloading it if needed."""
    path = os.path.join(CACHE, sid + ".html")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()

    meta = retry(
        lambda: call(
            "get_screen",
            {"name": f"projects/{PID}/screens/{sid}", "projectId": PID, "screenId": sid},
        )
    )
    if isinstance(meta, list):
        meta = meta[0]
    code = (meta.get("htmlCode") or {}).get("downloadUrl")
    if not code:
        return None
    html = retry(lambda: fetch_url(code))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(CACHE, sid + ".title.txt"), "w", encoding="utf-8") as fh:
        fh.write(meta.get("title", ""))
    return html


def main():
    listing = retry(lambda: call("list_screens", {"projectId": PID}))
    screens = listing.get("screens", []) if isinstance(listing, dict) else listing

    # Full page designs carry the layouts we need; the rest are single generated
    # images whose HTML is just a bare wrapper.
    wanted = [s for s in screens if (s.get("title") or "").startswith("DJ Simons")]
    print(f"{len(screens)} screens total, {len(wanted)} page designs\n")

    for s in wanted:
        sid = s["name"].split("/")[-1]
        title = s.get("title", "")
        try:
            html = screen_html(sid)
            print(f"  ok    {len(html or ''):>7} bytes  {title[:62]}")
        except Exception as exc:
            print(f"  FAIL  {str(exc)[:40]:<40}  {title[:62]}")
        time.sleep(0.4)


if __name__ == "__main__":
    main()
