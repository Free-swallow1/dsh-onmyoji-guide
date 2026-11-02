# -*- coding: utf-8 -*-
"""生成式神/御魂/阴阳师介绍图卡（PNG，调色板压缩）。

用法：
  python tools/build_cards.py --img-dir D:/path/to/img
  # img 目录需包含 skin/Skin_<id>_01.png、char/S_<id>_01.png、soul/<御魂名>.png
"""
import argparse
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "cards")

W = 560
PAD = 20
BG = (20, 17, 28)
PANEL = (34, 28, 46)
PANEL2 = (42, 35, 56)
GOLD = (214, 178, 110)
TEXT = (233, 229, 221)
SUB = (163, 156, 148)

FONT = os.environ.get("CARD_FONT", "C:/Windows/Fonts/msyh.ttc")
FONTB = os.environ.get("CARD_FONT_BOLD", "C:/Windows/Fonts/msyhbd.ttc")
# 建议使用 OFL 字体重新生成，例如 Noto Sans CJK SC：
#   CARD_FONT=NotoSansCJKsc-Regular.otf CARD_FONT_BOLD=NotoSansCJKsc-Bold.otf


def f(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size)


def wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=font) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def par(draw, xy, text, font, fill, maxw, lh, max_lines=None):
    x, y = xy
    lines = wrap(draw, text or "", font, maxw)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += lh
    return y


def pct(v):
    if v is None:
        return "-"
    return "%g%%" % round(v * 100, 1)


def stat_cell(draw, x, y, w, h, label, value):
    draw.rounded_rectangle([x, y, x + w, y + h], 10, fill=PANEL)
    draw.text((x + 10, y + 8), label, font=f(11), fill=SUB)
    draw.text((x + 10, y + 26), value, font=f(18, True), fill=TEXT)


def watermark(draw, y):
    draw.text((PAD, y), "阴阳师助手 · deepseek-v4.1flash-1017", font=f(10), fill=(108, 101, 94))
    return y + 18


def header(draw, y, name, badge, tags):
    draw.text((PAD, y), name, font=f(28, True), fill=TEXT)
    nw = draw.textlength(name, font=f(28, True))
    bw = draw.textlength(badge, font=f(13, True)) + 14
    draw.rounded_rectangle([PAD + nw + 12, y + 7, PAD + nw + 12 + bw, y + 31], 7, outline=GOLD, width=1)
    draw.text((PAD + nw + 19, y + 10), badge, font=f(13, True), fill=GOLD)
    draw.text((PAD, y + 40), " / ".join(tags or []), font=f(12), fill=GOLD)
    return y + 66


def load_art(path):
    if not path or not os.path.exists(path):
        return None
    try:
        im = Image.open(path)
        im.load()
        return im.convert("RGBA")
    except Exception:
        return None


def paste_art(canvas, d, path, x, y, w, h):
    im = load_art(path)
    if im is None:
        return
    im.thumbnail((w, h), Image.LANCZOS)
    canvas.paste(im, (x + (w - im.width) // 2, y + (h - im.height) // 2), im)
    d.rounded_rectangle([x - 3, y - 3, x + w + 3, y + h + 3], 9, outline=(68, 57, 82), width=1)


def render_char(c, rec, img_dir):
    canvas = Image.new("RGB", (W, 2400), BG)
    d = ImageDraw.Draw(canvas)
    y = header(d, 20, c["name"], c.get("rarity") or "", c.get("tags"))

    port_w, port_h = 200, 300
    px = W - PAD - port_w
    img = os.path.join(img_dir, "skin", "Skin_%s_01.png" % c["id"])
    if load_art(img) is None:
        img = os.path.join(img_dir, "char", "S_%s_01.png" % c["id"])
    paste_art(canvas, d, img, px, y, port_w, port_h)

    left_w = px - PAD - 14
    ly = y + 2
    cv = c.get("cv") or {}
    cv_txt = " / ".join([x for x in [cv.get("cn"), cv.get("jp")] if x])
    if cv_txt:
        d.text((PAD, ly), "CV：" + cv_txt, font=f(13), fill=SUB)
        ly += 22
    if c.get("date"):
        d.text((PAD, ly), "实装：" + str(c["date"]), font=f(13), fill=SUB)
        ly += 22
    ly = par(d, (PAD, ly + 4), (c.get("intro") or "").replace("\n", " "), f(13), SUB, left_w, 20, max_lines=5)
    if rec:
        box_y = ly + 6
        box_h = 78
        d.rounded_rectangle([PAD, box_y, PAD + left_w, box_y + box_h], 10, fill=PANEL2)
        d.text((PAD + 10, box_y + 8), "御魂参考", font=f(12, True), fill=GOLD)
        par(d, (PAD + 10, box_y + 28), rec.get("souls", ""), f(12), TEXT, left_w - 20, 18, max_lines=1)
        par(d, (PAD + 10, box_y + 46), "246：" + rec.get("pos", ""), f(11), SUB, left_w - 20, 16, max_lines=1)
        par(d, (PAD + 10, box_y + 62), rec.get("target", ""), f(11), SUB, left_w - 20, 14, max_lines=1)
    y += port_h + 14

    st = c.get("stats") or {}
    stats = [("攻击", st.get("atk")), ("生命", st.get("hp")), ("防御", st.get("def")), ("速度", st.get("spd")),
             ("暴击", pct(st.get("cri"))), ("暴伤", pct(st.get("crid"))),
             ("命中", pct(st.get("efh"))), ("抵抗", pct(st.get("efr")))]
    cw = (W - PAD * 2 - 10 * 3) // 4
    for i, (lab, val) in enumerate(stats):
        r, col = divmod(i, 4)
        stat_cell(d, PAD + col * (cw + 10), y + r * 66, cw, 56, lab, str(val) if val is not None else "-")
    y += 66 * 2 + 8

    d.text((PAD, y), "技能", font=f(18, True), fill=GOLD)
    y += 30
    for i, s in enumerate(c.get("skills") or [], 1):
        d.text((PAD, y), "%d. %s" % (i, s["name"]), font=f(16, True), fill=TEXT)
        cost = s.get("cost")
        ctype = "被动" if s.get("type") == "被动" or cost == -1 else ("%s火" % cost if cost else "0火")
        d.text((W - PAD - d.textlength(ctype, font=f(12)), y + 3), ctype, font=f(12), fill=GOLD)
        y += 26
        y = par(d, (PAD, y), (s.get("desc") or "").replace("\n", " "), f(13), TEXT, W - PAD * 2, 20)
        ups = " / ".join("Lv%s %s" % (u.get("level"), u.get("effect")) for u in (s.get("upgrades") or []))
        if ups:
            y = par(d, (PAD, y + 3), ups, f(11), SUB, W - PAD * 2, 17, max_lines=2)
        y += 10

    refs = []
    for s in c.get("skills") or []:
        for b in s.get("buffs") or []:
            if b.get("name") not in [r[0] for r in refs]:
                refs.append((b.get("name"), b.get("buffDesc") or ""))
        for t in s.get("tips") or []:
            if t.get("skill_tips_name") not in [r[0] for r in refs]:
                refs.append((t.get("skill_tips_name"), t.get("skill_tips_text") or ""))
    if refs:
        d.text((PAD, y), "词条", font=f(15, True), fill=GOLD)
        y += 26
        for name, desc in refs[:4]:
            y = par(d, (PAD, y), "%s：%s" % (name, (desc or "").replace("\n", " ")), f(11), SUB, W - PAD * 2, 17, max_lines=2)
            y += 2

    y = watermark(d, y + 8)
    return canvas.crop((0, 0, W, min(y + 8, canvas.height)))


def render_soul(s, img_dir):
    canvas = Image.new("RGB", (W, 1600), BG)
    d = ImageDraw.Draw(canvas)
    y = header(d, 20, s["name"], s.get("type") or "御魂", [])
    port_w, port_h = 190, 260
    px = W - PAD - port_w
    paste_art(canvas, d, os.path.join(img_dir, "soul", s["name"] + ".png"), px, y, port_w, port_h)

    left_w = px - PAD - 14
    ly = y + 2
    d.text((PAD, ly), "2件套", font=f(13, True), fill=GOLD)
    ly = par(d, (PAD, ly + 22), s.get("suit") or "-", f(14), TEXT, left_w, 20)
    ly += 12
    d.text((PAD, ly), "4件套", font=f(13, True), fill=GOLD)
    ly = par(d, (PAD, ly + 22), s.get("desc") or "-", f(13), TEXT, left_w, 20)
    y += port_h + 14

    d.text((PAD, y), "获取途径", font=f(15, True), fill=GOLD)
    y += 26
    y = par(d, (PAD, y), (s.get("way") or "未知").replace("\n", " / "), f(12), SUB, W - PAD * 2, 18)
    y = watermark(d, y + 10)
    return canvas.crop((0, 0, W, min(y + 6, canvas.height)))


def render_onmyoji(o, img_dir):
    canvas = Image.new("RGB", (W, 1600), BG)
    d = ImageDraw.Draw(canvas)
    y = header(d, 20, o["name"], o.get("grade") or "阴阳师", ["主角"])
    port_w, port_h = 180, 250
    px = W - PAD - port_w
    paste_art(canvas, d, os.path.join(img_dir, "skin", "Skin_%s_01.png" % o["id"]), px, y, port_w, port_h)
    y += port_h + 12

    d.text((PAD, y), "技能", font=f(18, True), fill=GOLD)
    y += 28
    for i, s in enumerate(o.get("skills") or [], 1):
        d.text((PAD, y), "%d. %s" % (i, s["name"]), font=f(15, True), fill=TEXT)
        y += 24
        y = par(d, (PAD, y), (s.get("desc") or "").replace("\n", " "), f(12), TEXT, W - PAD * 2, 18)
        y += 8
    if o.get("advice"):
        y = par(d, (PAD, y + 2), "建议：" + o["advice"], f(12), GOLD, W - PAD * 2, 18)
        y += 6
    y = watermark(d, y + 8)
    return canvas.crop((0, 0, W, min(y + 6, canvas.height)))


def save_card(im, path):
    q = im.convert("RGB").quantize(colors=96, method=Image.MEDIANCUT)
    q.save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-dir", default=os.path.join(ROOT, "tools", "img"))
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    chars = json.load(open(os.path.join(DATA, "characters.json"), encoding="utf-8"))
    souls = json.load(open(os.path.join(DATA, "souls.json"), encoding="utf-8"))
    onmyoji = json.load(open(os.path.join(DATA, "onmyoji.json"), encoding="utf-8"))
    recs = json.load(open(os.path.join(DATA, "recommend.json"), encoding="utf-8"))

    total = 0
    for c in chars:
        im = render_char(c, recs.get(c["name"]), args.img_dir)
        p = os.path.join(OUT, "char_%s.png" % c["id"])
        save_card(im, p)
        total += os.path.getsize(p)
    for s in souls:
        im = render_soul(s, args.img_dir)
        p = os.path.join(OUT, "soul_%s.png" % s["id"])
        save_card(im, p)
        total += os.path.getsize(p)
    for o in onmyoji:
        im = render_onmyoji(o, args.img_dir)
        p = os.path.join(OUT, "onmyoji_%s.png" % o["id"])
        save_card(im, p)
        total += os.path.getsize(p)
    print("cards:", len(os.listdir(OUT)), "total", round(total / 1024 / 1024, 1), "MB")


if __name__ == "__main__":
    main()
