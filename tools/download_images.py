# -*- coding: utf-8 -*-
"""Download icons (shikigami heads, soul icons) from huiji CDN."""
import json, os, hashlib, urllib.request, concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "tools", "raw")
OUT = os.path.join(ROOT, "tools", "img")
os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"

def url(name):
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return "https://huiji-public.huijistatic.com/yys/uploads/%s/%s/%s" % (h[0], h[:2], urllib.parse.quote(name))

import urllib.parse

chars = json.load(open(os.path.join(RAW, "CharacterIndex.json"), encoding="utf-8"))["characters"]
skins = json.load(open(os.path.join(RAW, "Skin.json"), encoding="utf-8"))
souls = json.load(open(os.path.join(RAW, "Soul.json"), encoding="utf-8"))["soul"]

tasks = []  # (name, subdir)
for c in chars:
    cid = c["id"]
    tasks.append(("S_%s_01.png" % cid, "char"))
    tasks.append(("S_%s_02.png" % cid, "char"))
    d = skins.get(str(cid))
    if d and d.get("skins"):
        # all costume head icons
        for s in d["skins"][:8]:
            tasks.append(("S_%s_%s.png" % (cid, s["skin_id"]), "char"))
for s in souls:
    n = s["name"]
    tasks.append((n + ".png", "soul"))
    tasks.append((n + " s.png", "soul"))

# dedupe
seen = set()
uniq = []
for n, sub in tasks:
    if n in seen:
        continue
    seen.add(n)
    uniq.append((n, sub))
print("total", len(uniq))

def dl(item):
    name, sub = item
    d = os.path.join(OUT, sub)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 100:
        return "skip"
    try:
        req = urllib.request.Request(url(name), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 100:
            return "empty"
        open(dest, "wb").write(data)
        return "ok"
    except Exception as e:
        return "err:" + str(e)[:60]

stats = {"ok": 0, "skip": 0, "empty": 0, "err": 0}
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    for r in ex.map(dl, uniq):
        k = r.split(":")[0]
        stats[k] = stats.get(k, 0) + 1
print(stats)
