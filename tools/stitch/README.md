# Stitch image recovery

Tooling used to recover the site's expired images from the Google Stitch
project, and to keep them from expiring again.

## What went wrong

Stitch emits two kinds of image URL on `lh3.googleusercontent.com`:

| Form | Lifetime |
| --- | --- |
| `/aida-public/AB6AXu…` | persistent |
| `/aida/AP1WRL…` | session-scoped — **expires to 403** |

The pages were built by pasting Stitch HTML verbatim, so half the images were
hotlinked through the second kind and eventually died. Stitch's *own* stored
HTML rots the same way — 20 of the 24 `/aida/` URLs inside the project were
already dead when we looked.

What does survive is the artwork itself. Every generated image is its own
screen in the project, and `get_screen` mints a **fresh signed URL** for
`screenshot.downloadUrl` on each call. That is how the originals were
recovered after the embedded links had expired.

## Scripts

| File | Purpose |
| --- | --- |
| `stitch.py` | JSON-RPC client for `stitch.googleapis.com/mcp`. Reads the API key from `~/.claude.json`. Run it directly for `check` / `tools`. |
| `fetch_screens.py` | Downloads and caches the HTML of every page-design screen. |
| `pull_assets.py` | Downloads all 1024×1024 generated images to `stitch_assets/` and writes `catalog.json` (file → generating prompt). |
| `restore.py` | Maps recovered artwork onto the site's empty slots and repoints the markup. Its `MAPPING` records which image landed where. |

Note Claude Code's built-in MCP client cannot talk to this server: it responds
to the 401 challenge by attempting OAuth dynamic client registration, which
`accounts.google.com` does not support. `stitch.py` sidesteps that by sending
the API key directly. If calls start returning 401, the key has expired —
re-add the server with a fresh one:

```bash
claude mcp remove stitch -s user
claude mcp add stitch --transport http --header "X-Goog-Api-Key: <new-key>" -s user https://stitch.googleapis.com/mcp
```

The API is intermittently flaky and returns `Request contains an invalid
argument` on calls that succeed on retry, so every request is retried and
cached.

## Rule going forward

**Never ship a `lh3.googleusercontent.com` URL.** Any freshly exported Stitch
HTML must be run through `tools/localize_images.py` immediately, while its
URLs are still alive:

```bash
python tools/localize_images.py path/to/exported.html
```

That downloads every image into `assets/img/` and rewrites the references to
relative paths.

## Enforcement

The rule above is not left to memory — `tools/check_images.py` enforces it at
two points, and fails on either thing that has actually broken this site:

- a remote image reference (it can expire)
- a local reference pointing at a missing file (equally broken, and invisible
  to any check that only greps for `http`)

Only tracked HTML is inspected, so local scratch files are ignored.
`redesign_html/` and the other raw export folders are exempt: they are archived
records of what Stitch delivered, and rewriting them would destroy their value.

**Locally**, via a pre-commit hook. Enable it once per clone:

```bash
git config core.hooksPath tools/hooks
```

**On GitHub**, via `.github/workflows/images.yml`, which runs on every push to
`main` and every pull request. This is the part that matters: a hook only
protects the clone that enabled it, and a commit reintroducing expiring URLs
has already reached this repository once from elsewhere.

To see it work, reintroduce a pre-fix page and run the checker:

```bash
git show a8c2552:boards.html > boards.html && python tools/check_images.py
```

It reports all 18 offending lines. Restore with `git checkout -- boards.html`.
