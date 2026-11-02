# -*- coding: utf-8 -*-
"""Build normalized knowledge base JSON from huijiwiki raw dumps."""
import json, os, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "tools", "raw")
OUT = os.path.join(ROOT, "data")
os.makedirs(OUT, exist_ok=True)

def load(name):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)

buffs = load("SkillBuffs.json")["buff"]
tips = load("SkillTips.json")["tips"]
tips = {str(k): v for k, v in tips.items()}
attrs = {str(a["id"]): a for a in load("Attribute.json")["attributes"]}
index = load("CharacterIndex.json")["characters"]

BUFF_RE = re.compile(r"\[buff_([0-9_]+)\]")
TIP_RE = re.compile(r"\[tips_([0-9]+)\]")
SKILL_RE = re.compile(r"\[skill_([0-9_]+)\]")

def clean(t):
    if not isinstance(t, str):
        return ""
    t = t.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()

def resolve(text, refs):
    if not isinstance(text, str):
        return ""
    def rb(m):
        b = buffs.get(m.group(1))
        if b:
            refs["buffs"].append(b)
            return "「%s」" % b["name"]
        return ""
    text = BUFF_RE.sub(rb, text)
    def rt(m):
        t = tips.get(m.group(1))
        if t:
            refs["tips"].append(t)
            return t["skill_tips_name"]
        return ""
    text = TIP_RE.sub(rt, text)
    text = SKILL_RE.sub(lambda m: m.group(0), text)
    return clean(text)

def skill_type(sk, idx):
    if sk.get("passive") or sk.get("cost") == -1:
        return "被动"
    if idx == 0 and (sk.get("cost") or 0) == 0:
        return "普攻"
    if (sk.get("cost") or 0) == 0:
        return "普攻"
    return "技能"

def dedup(seq, key="name"):
    out, seen = [], set()
    for x in seq:
        k = x.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out

chars = []
for c in index:
    cid = str(c["id"])
    try:
        d = load("Character__%s.json" % cid)
    except Exception:
        continue
    name = d.get("name", {}).get("cn") or c["name"]
    skills = []
    for i, sk in enumerate(d.get("skills", [])):
        refs = {"buffs": [], "tips": []}
        desc = resolve(sk.get("description"), refs)
        ups = []
        for u in sk.get("upgrades", []) or []:
            ups.append({"level": u.get("level"), "effect": resolve(u.get("effect"), refs)})
        skills.append({
            "name": sk.get("name"),
            "type": skill_type(sk, i),
            "cost": sk.get("cost"),
            "brief": clean(sk.get("brief")),
            "desc": desc,
            "desc_before_awake": resolve(sk.get("description_before_awake"), refs),
            "upgrades": ups,
            "tags": [t.get("name") for t in (sk.get("tags") or [])],
            "buffs": dedup(refs["buffs"]),
            "tips": dedup(refs["tips"]),
        })
    a = attrs.get(cid, {})
    stats = {k: a.get(k) for k in ("atk", "hp", "def", "spd", "cri", "crid", "efh", "efr") if a.get(k) is not None}
    aliases = set()
    for n in [name, c.get("name"), c.get("pageTitle")]:
        if n:
            aliases.add(n)
    nicks = c.get("nickname") or []
    if isinstance(nicks, str):
        nicks = [nicks]
    for n in nicks:
        if isinstance(n, str) and n.strip():
            aliases.add(n.strip())
    if c.get("rarity"):
        aliases.add("%s%s" % (c["rarity"], name))
    chars.append({
        "id": c["id"],
        "name": name,
        "rarity": c.get("rarity") or d.get("grade"),
        "aliases": sorted(aliases, key=len, reverse=True),
        "tags": c.get("tags") or [],
        "extra": c.get("extraTags") or {},
        "year": c.get("year"),
        "date": d.get("date"),
        "cv": d.get("cv"),
        "intro": clean(d.get("introduction")),
        "stats": stats,
        "skills": skills,
    })

# 阴阳师 / 英杰
onmyoji = []
for cid in ["10", "11", "12", "13", "15", "16"]:
    d = load("Character__%s.json" % cid)
    skills = []
    for i, sk in enumerate(d.get("skills", [])):
        refs = {"buffs": [], "tips": []}
        skills.append({
            "name": sk.get("name"),
            "type": skill_type(sk, i),
            "cost": sk.get("cost"),
            "desc": resolve(sk.get("description"), refs),
            "upgrades": [{"level": u.get("level"), "effect": resolve(u.get("effect"), refs)} for u in (sk.get("upgrades") or [])],
            "tags": [t.get("name") for t in (sk.get("tags") or [])],
            "buffs": dedup(refs["buffs"]),
            "tips": dedup(refs["tips"]),
        })
    onmyoji.append({"id": int(cid), "name": d["name"]["cn"], "grade": d.get("grade"), "cv": d.get("cv"), "skills": dedup(skills)})

souls = []
for s in load("Soul.json")["soul"]:
    souls.append({
        "id": s["id"],
        "name": s["name"],
        "suit": s.get("suit"),
        "desc": clean(s.get("desc")),
        "type": "御魂" if s["type"] == 1 else "首领御魂",
        "way": clean(s.get("way")),
    })

with open(os.path.join(OUT, "characters.json"), "w", encoding="utf-8") as f:
    json.dump(chars, f, ensure_ascii=False, separators=(",", ":"))
with open(os.path.join(OUT, "souls.json"), "w", encoding="utf-8") as f:
    json.dump(souls, f, ensure_ascii=False, separators=(",", ":"))
with open(os.path.join(OUT, "onmyoji.json"), "w", encoding="utf-8") as f:
    json.dump(onmyoji, f, ensure_ascii=False, separators=(",", ":"))

print("chars", len(chars), "souls", len(souls), "onmyoji", len(onmyoji))
print("sample:", json.dumps(chars[0], ensure_ascii=False)[:600])
