"""Minimal direct client for the Stitch MCP endpoint.

Claude Code's built-in MCP client cannot authenticate here: it sees the 401
challenge and attempts OAuth dynamic client registration, which
accounts.google.com does not support. So we speak JSON-RPC to the endpoint
directly instead.

The configured X-Goog-Api-Key identifies the app and is enough for
`initialize` / `tools/list`, but every real tool call needs a user OAuth 2
access token scoped to https://www.googleapis.com/auth/aida.

Put that token, by itself, in:

    C:\\Users\\frank\\.claude\\stitch_token.txt

It lives outside the git repo so it can never be committed.
"""

import json
import os
import sys
import urllib.error
import urllib.request

CFG = json.load(open(r"C:\Users\frank\.claude.json"))["mcpServers"]["stitch"]
URL = CFG["url"]
KEY = CFG["headers"]["X-Goog-Api-Key"]
TOKEN_FILE = r"C:\Users\frank\.claude\stitch_token.txt"

_id = [0]


def token():
    if not os.path.exists(TOKEN_FILE):
        return None
    tok = open(TOKEN_FILE, encoding="utf-8").read().strip()
    # Tolerate a pasted "Bearer xyz" or a stray trailing newline/quotes.
    tok = tok.removeprefix("Bearer ").strip().strip('"').strip("'")
    return tok or None


def rpc(method, params=None):
    _id[0] += 1
    body = json.dumps(
        {"jsonrpc": "2.0", "id": _id[0], "method": method, "params": params or {}}
    ).encode()
    headers = {
        "X-Goog-Api-Key": KEY,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    tok = token()
    if tok:
        headers["Authorization"] = "Bearer " + tok

    req = urllib.request.Request(URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read().decode("utf8", "replace")

    # The endpoint may reply as SSE; pull the JSON out of the data: frames.
    if raw.lstrip().startswith(("event:", "data:")):
        raw = "".join(
            line[5:].strip() for line in raw.splitlines() if line.startswith("data:")
        )
    msg = json.loads(raw)
    if "error" in msg:
        raise RuntimeError(msg["error"])
    return msg.get("result", {})


def call(tool, args=None):
    """Invoke an MCP tool and unwrap its content payload."""
    res = rpc("tools/call", {"name": tool, "arguments": args or {}})
    out = []
    for item in res.get("content", []):
        if item.get("type") == "text":
            try:
                out.append(json.loads(item["text"]))
            except json.JSONDecodeError:
                out.append(item["text"])
    if res.get("isError"):
        raise RuntimeError(out[0] if len(out) == 1 else out)
    return out[0] if len(out) == 1 else out


def check():
    """Report whether we can actually reach the user's Stitch data."""
    if not token():
        return False, f"No token found at {TOKEN_FILE}"
    try:
        res = call("list_projects", {})
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "401 - token rejected (expired, or missing the 'aida' scope)"
        return False, f"HTTP {e.code}"
    except RuntimeError as e:
        return False, f"server refused: {str(e)[:200]}"
    projects = res.get("projects", []) if isinstance(res, dict) else (res or [])
    return True, f"OK - {len(projects)} project(s) visible"


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "check"
    if what == "check":
        ok, msg = check()
        print(("READY  " if ok else "BLOCKED  ") + msg)
        sys.exit(0 if ok else 1)
    elif what == "tools":
        for t in rpc("tools/list").get("tools", []):
            print("  " + t["name"])
    else:
        args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(json.dumps(call(what, args), indent=1)[:6000])
