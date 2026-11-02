# -*- coding: utf-8 -*-
"""Build perceptual-hash index for shikigami/soul icons."""
import json, os, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import yys_vision

IMG = os.path.join(ROOT, "tools", "img")
DATA = os.path.join(ROOT, "data")

chars = json.load(open(os.path.join(DATA, "characters.json"), encoding="utf-8"))
souls = json.load(open(os.path.join(DATA, "souls.json"), encoding="utf-8"))

index = []
for c in chars:
    cid = c["id"]
    for fn in sorted(os.listdir(os.path.join(IMG, "char"))):
        if not fn.startswith("S_%s_" % cid):
            continue
        p = os.path.join(IMG, "char", fn)
        try:
            im = Image.open(p)
            im.load()
        except Exception:
            continue
        index.append({
            "type": "char",
            "name": c["name"],
            "rarity": c.get("rarity"),
            "dhash": yys_vision.dhash_hex(im),
            "feat": yys_vision.feat_b64(im),
            "file": fn,
        })

for s in souls:
    for fn in (s["name"] + ".png", s["name"] + " s.png"):
        p = os.path.join(IMG, "soul", fn)
        if not os.path.exists(p):
            continue
        try:
            im = Image.open(p)
            im.load()
        except Exception:
            continue
        index.append({
            "type": "soul",
            "name": s["name"],
            "dhash": yys_vision.dhash_hex(im),
            "feat": yys_vision.feat_b64(im),
            "file": fn,
        })

out = os.path.join(DATA, "image_index.json")
json.dump(index, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("index", len(index), "bytes", os.path.getsize(out))
print("chars", sum(1 for i in index if i["type"] == "char"), "souls", sum(1 for i in index if i["type"] == "soul"))
