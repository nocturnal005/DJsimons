"""Restore the expired site images from the recovered Stitch artwork.

Stitch stores each generated image as its own screen, but nothing in the API
links a screen back to the URL it was embedded under - the image screens carry
no HTML. So slots are matched to artwork by pairing each slot's alt text (or
its role, for CSS backgrounds) against the prompt that generated the image.

Copies the chosen JPEGs into assets/img/ and repoints the markup at them.
"""

import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r"D:\djsimmons"
ASSETS = os.path.join(REPO, "assets", "img")
SRC = os.path.join(HERE, "stitch_assets")
CATALOG = json.load(open(os.path.join(HERE, "catalog.json"), encoding="utf-8"))

# (page, alt text) -> Stitch screen id prefix. "__bg__" marks the CSS
# background-image heroes, which carry no alt attribute.
MAPPING = {
    ("index.html", "Bespoke Mouldings"): "282d1c2d",
    ("index.html", "Archival Mountboards"): "cf220666",
    ("index.html", "Workshop Sundries"): "a1672171",

    ("mouldings.html", "Profile"): "b585ff36",
    ("mouldings.html", "Moulding Profile 1"): "7df68b9c",
    ("mouldings.html", "Moulding Profile 2"): "5c4c92f5",
    ("mouldings.html", "Moulding Profile 3"): "ff95d532",
    ("mouldings.html", "Detail 4"): "74129f5a",
    ("mouldings.html", "Detail 7"): "9a16417b",
    ("mouldings.html", "Detail 10"): "d8beb830",

    ("boards.html", "Premium Barrier"): "30d4daf8",
    ("boards.html", "Cold Press Mount"): "d0eafa04",
    ("boards.html", "Backing Samples"): "ea37b5d3",
    ("boards.html", "Specialty Samples"): "4a1d1b54",
    ("boards.html", "Mounting Stand"): "2bad3507",
    ("boards.html", "Details"): "1ec87dac",

    ("machinery.html", "Premium framing workshop equipment"): "25672e0c",
    ("machinery.html", "Precision Mitre Saw"): "762790db",
    ("machinery.html", "Industrial Underpinner"): "f9298586",
    ("machinery.html", "Wall-Mounted Cutter"): "3f3f81aa",
    ("machinery.html", "Precision Mount Cutter"): "399ce8ab",
    ("machinery.html", "Professional Underpinner"): "2e47e52d",
    ("machinery.html", "Double Mitre System"): "ad61af36",

    ("chop-service.html", "__bg__"): "5100a668",

    ("technical-data.html", "__bg__"): "fcb16ef5",
    ("technical-data.html", "Cotton Museum Board"): "7e0ee8b5",
    ("technical-data.html", "Conservation White Core"): "2525b82c",
    ("technical-data.html", "Standard White Core"): "a67cf23d",
    ("technical-data.html", "Standard Cream Core"): "a60f9f3a",
}

DEAD_RE = re.compile(r"https://lh3\.googleusercontent\.com/aida/[^\"')\s]+")
ALT_RE = re.compile(r'alt="([^"]*)"')


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:44] or "image"


def resolve(prefix):
    """Full asset path for a screen-id prefix."""
    for f in os.listdir(SRC):
        if f.startswith(prefix):
            return os.path.join(SRC, f)
    return None


def main():
    os.makedirs(ASSETS, exist_ok=True)
    total_repointed = 0
    unmatched = []

    for page in sorted({p for p, _ in MAPPING}):
        path = os.path.join(REPO, page)
        text = open(path, encoding="utf-8").read()
        original = text

        # Resolve each dead URL to the slot it occupies, via the alt on its line.
        slots = {}
        for line in text.splitlines():
            for url in DEAD_RE.findall(line):
                alt = ALT_RE.search(line)
                key = alt.group(1) if alt else "__bg__"
                slots.setdefault(url, key)

        print(f"\n{page}  ({len(slots)} expired)")
        for url, key in slots.items():
            prefix = MAPPING.get((page, key))
            if not prefix:
                unmatched.append((page, key))
                print(f"    UNMAPPED  {key}")
                continue

            src = resolve(prefix)
            if not src:
                unmatched.append((page, key))
                print(f"    NO ASSET  {key} -> {prefix}")
                continue

            name = f"{slugify(key if key != '__bg__' else page[:-5] + '-hero')}-{prefix}.jpg"
            dest = os.path.join(ASSETS, name)
            if not os.path.exists(dest):
                shutil.copy2(src, dest)

            rel = os.path.relpath(dest, os.path.dirname(path)).replace(os.sep, "/")
            n = text.count(url)
            text = text.replace(url, rel)
            total_repointed += n
            title = CATALOG.get(
                next(k for k in CATALOG if k.startswith(prefix)), {}
            ).get("title", "")
            print(f"    {key[:34]:<34} <- {title[:58]}")

        if text != original:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)

    print(f"\nrepointed {total_repointed} reference(s)")
    if unmatched:
        print(f"unmatched slots: {unmatched}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
