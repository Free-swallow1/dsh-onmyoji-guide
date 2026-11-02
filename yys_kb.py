# -*- coding: utf-8 -*-
"""阴阳师知识库：加载、检索、格式化。"""
from __future__ import annotations

import json
import os
import re
import difflib

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load_json(name, default):
    path = os.path.join(DATA_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _fmt_pct(v):
    if v is None:
        return "?"
    return ("%g%%" % round(v * 100, 1))


class KB:
    def __init__(self):
        self.chars = _load_json("characters.json", [])
        self.souls = _load_json("souls.json", [])
        self.onmyoji = _load_json("onmyoji.json", [])
        self.recommend = _load_json("recommend.json", {})
        self._mechanics = ""
        try:
            with open(os.path.join(DATA_DIR, "mechanics.md"), encoding="utf-8") as f:
                self._mechanics = f.read()
        except Exception:
            self._mechanics = ""

        self.by_name = {}
        self.by_alias = []
        for c in self.chars:
            self.by_name[c["name"]] = c
            for a in c.get("aliases", []):
                if a:
                    self.by_alias.append((a, c))
        self.onmyoji_by_name = {o["name"]: o for o in self.onmyoji}
        self.soul_by_name = {s["name"]: s for s in self.souls}

    # ---------- 检索 ----------
    def _norm(self, text):
        t = (text or "").strip().lower()
        t = re.sub(r"[\s,，。.!！?？:：;；\"'“”‘’()（）\[\]【】<>《》~～、|/\\]+", "", t)
        return t

    def find_char(self, text):
        """返回 (char, score)。优先精确别名，其次包含，最后模糊。"""
        if not text:
            return None, 0.0
        raw = text.strip()
        n = self._norm(raw)
        for c in self.chars:
            for a in c.get("aliases", []):
                if a and self._norm(a) == n:
                    return c, 1.0
        best, best_score = None, 0.0
        for a, c in self.by_alias:
            na = self._norm(a)
            if len(na) >= 2 and na in n:
                score = 0.8 + min(len(na), 8) * 0.01
                if score > best_score:
                    best, best_score = c, score
        if best:
            return best, best_score
        # 模糊
        names = list(self.by_name.keys())
        cand = difflib.get_close_matches(raw, names, n=1, cutoff=0.55)
        if cand:
            return self.by_name[cand[0]], 0.6
        return None, 0.0

    def find_soul(self, text):
        if not text:
            return None, 0.0
        n = self._norm(text)
        for s in self.souls:
            if self._norm(s["name"]) == n:
                return s, 1.0
        best, best_score = None, 0.0
        for s in self.souls:
            ns = self._norm(s["name"])
            if ns in n:
                score = 0.8 + len(ns) * 0.01
                if score > best_score:
                    best, best_score = s, score
        if best:
            return best, best_score
        cand = difflib.get_close_matches(text.strip(), [s["name"] for s in self.souls], n=1, cutoff=0.6)
        if cand:
            return self.soul_by_name[cand[0]], 0.6
        return None, 0.0

    def mentions(self, text):
        """找出文本中提到的式神和御魂（去重，按出现顺序）。"""
        chars, souls = [], []
        n = self._norm(text)
        if not n:
            return chars, souls
        hits = []
        for a, c in self.by_alias:
            na = self._norm(a)
            if len(na) >= 2 and na in n:
                hits.append((n.index(na), -len(na), c))
        hits.sort()
        seen = set()
        for _, _, c in hits:
            if c["id"] not in seen:
                seen.add(c["id"])
                chars.append(c)
        for s in self.souls:
            ns = self._norm(s["name"])
            if ns and ns in n:
                souls.append(s)
        return chars, souls

    # ---------- 格式化 ----------
    def stats_line(self, c):
        st = c.get("stats") or {}
        parts = []
        if st.get("atk") is not None:
            parts.append("攻击%d" % st["atk"])
        if st.get("hp") is not None:
            parts.append("生命%d" % st["hp"])
        if st.get("def") is not None:
            parts.append("防御%d" % st["def"])
        if st.get("spd") is not None:
            parts.append("速度%d" % st["spd"])
        if st.get("cri") is not None:
            parts.append("暴击%s" % _fmt_pct(st["cri"]))
        if st.get("crid") is not None:
            parts.append("暴伤%s" % _fmt_pct(st["crid"]))
        if st.get("efh"):
            parts.append("命中%s" % _fmt_pct(st["efh"]))
        if st.get("efr"):
            parts.append("抵抗%s" % _fmt_pct(st["efr"]))
        return "｜".join(parts)

    def role_line(self, c):
        tags = "/".join(c.get("tags") or []) or "综合"
        extra = c.get("extra") or {}
        bits = []
        if extra.get("dmgtype"):
            bits.append(extra["dmgtype"])
        if extra.get("feature"):
            bits.append(extra["feature"])
        return "定位：%s%s" % (tags, ("（%s）" % "，".join(bits)) if bits else "")

    def rec_for(self, c):
        name = c["name"]
        if name in self.recommend:
            return self.recommend[name], "专属"
        return self._rule_recommend(c), "通用"

    def _rule_recommend(self, c):
        tags = c.get("tags") or []
        extra = c.get("extra") or {}
        dmg = extra.get("dmgtype") or ""
        desc = " ".join((s.get("desc") or "") for s in c.get("skills") or [])

        def has(*kw):
            return any(k in tags for k in kw)

        if has("治疗", "恢复"):
            return {
                "souls": "树妖4 + 暴击2（或珍珠4）",
                "pos": "速/生/暴",
                "target": "满暴100%（治疗可暴击），生命尽量高",
                "note": "治疗量吃暴击，先满暴再堆生命。",
            }
        if has("拉条"):
            return {
                "souls": "招财猫4 / 火灵4 + 生命2",
                "pos": "速/生/生",
                "target": "速度230+（一速），生命达标",
                "note": "拉条式神速度优先，保证先手。",
            }
        if has("鬼火"):
            return {
                "souls": "招财猫4 / 火灵4 / 遗念火4 + 生命2",
                "pos": "速/抗/生",
                "target": "速度190+，抵抗/生命达标",
                "note": "打火式神堆速度与生存，卡在输出之前。",
            }
        if has("控制", "封印"):
            return {
                "souls": "魍魉之匣4 / 魅妖4 / 钟灵4 + 命中2",
                "pos": "速/命/生",
                "target": "效果命中150%+，速度200+",
                "note": "控制命中优先，AOE 控制更吃速度。",
            }
        if has("护盾", "守护", "减伤"):
            return {
                "souls": "地藏像4 / 薙魂4 / 蚌精4 + 生命2",
                "pos": "速/生/生（或速/抗/生）",
                "target": "生命尽量高，速度190+",
                "note": "辅助/保核，生命与速度优先。",
            }
        if has("伤害"):
            multi = ("多段" in desc) or ("次" in dmg)
            if "生命上限" in desc:
                return {
                    "souls": "树妖4 / 生命2 混搭（生命加成）",
                    "pos": "生/生/生或速/生/生",
                    "target": "生命最大化，保证满暴若技能吃暴击",
                    "note": "技能吃生命上限，优先生命。",
                }
            if multi:
                return {
                    "souls": "针女4 + 暴击2（多段）；破势4 视目标",
                    "pos": "攻/攻/暴击（针女）或攻/攻/暴伤",
                    "target": "满暴100%，攻击优先",
                    "note": "多段输出针女吃攻击上限，满暴后堆攻击。",
                }
            return {
                "souls": "破势4 + 暴击2（通用）；心眼/狂骨/网切按场景",
                "pos": "攻/攻/暴伤",
                "target": "满暴100%，暴伤250%+，攻击9000+",
                "note": "输出必须先满暴，再比较攻击×暴伤收益。",
            }
        return {
            "souls": "招财猫4 / 涂佛4 + 生命2（按技能机制调整）",
            "pos": "速/抗/生",
            "target": "速度/抵抗达标，保证存活",
            "note": "通用辅助思路，具体看技能机制。",
        }

    def card_path(self, kind, ident):
        p = os.path.join(DATA_DIR, "cards", "%s_%s.png" % (kind, ident))
        return p if os.path.exists(p) else ""

    def char_card(self, c, with_rec=True):
        lines = ["【%s %s】%s" % (c.get("rarity") or "", c["name"], self.stats_line(c))]
        lines.append(self.role_line(c))
        if c.get("cv"):
            cn = (c["cv"] or {}).get("cn") or ""
            jp = (c["cv"] or {}).get("jp") or ""
            if cn or jp:
                lines.append("CV：%s" % " / ".join([x for x in (cn, jp) if x]))
        sk = []
        for s in c.get("skills") or []:
            cost = s.get("cost")
            if s.get("type") == "被动" or cost == -1:
                cs = "被动"
            elif cost and cost > 0:
                cs = "%d火" % cost
            else:
                cs = "0火"
            sk.append("%s（%s）" % (s["name"], cs))
        if sk:
            lines.append("技能：" + "、".join(sk))
        if with_rec:
            rec, src = self.rec_for(c)
            lines.append("御魂参考（%s）：%s" % (src, rec["souls"]))
            lines.append("246：%s｜目标：%s" % (rec["pos"], rec["target"]))
            if rec.get("note"):
                lines.append("说明：" + rec["note"])
        return "\n".join(lines)

    def skill_text(self, c):
        lines = ["【%s 技能】" % c["name"]]
        for i, s in enumerate(c.get("skills") or [], 1):
            cost = s.get("cost")
            if s.get("type") == "被动" or cost == -1:
                cs = "被动"
            elif cost and cost > 0:
                cs = "%d鬼火" % cost
            else:
                cs = "0鬼火"
            head = "%d. %s（%s）" % (i, s["name"], cs)
            lines.append(head)
            if s.get("brief"):
                lines.append("　“%s”" % s["brief"])
            if s.get("desc"):
                lines.append("　" + s["desc"].replace("\n", " "))
            for u in s.get("upgrades") or []:
                lines.append("　Lv.%s %s" % (u.get("level"), u.get("effect")))
            for b in s.get("buffs") or []:
                lines.append("　〔%s〕%s" % (b.get("name"), (b.get("buffDesc") or "").replace("\n", " ")))
            for t in s.get("tips") or []:
                lines.append("　〔%s〕%s" % (t.get("skill_tips_name"), (t.get("skill_tips_text") or "").replace("\n", " ")))
        return "\n".join(lines)

    def soul_text(self, s):
        return "【%s】（%s）\n2件套：%s\n4件套：%s\n获取：%s" % (
            s["name"], s.get("type") or "御魂", s.get("suit") or "-", s.get("desc") or "-", (s.get("way") or "-").split("\n")[0]
        )

    def onmyoji_text(self, name):
        o = self.onmyoji_by_name.get(name)
        if not o:
            return None
        lines = ["【%s（%s）】" % (o["name"], o.get("grade") or "阴阳师")]
        for s in o.get("skills") or []:
            lines.append("· %s：%s" % (s["name"], (s.get("desc") or "").replace("\n", " ")))
        lines.append("提示：主角上场只能带 3 个技能，按副本/PVP 切换；主角增伤属于独立乘区。")
        return "\n".join(lines)

    # ---------- 机制检索 ----------
    def mechanics_for(self, question, limit=2600):
        if not self._mechanics:
            return ""
        sections = re.split(r"(?m)^## ", self._mechanics)
        if len(sections) <= 1:
            return self._mechanics[:limit]
        q = question or ""
        keywords = []
        if re.search(r"伤害|公式|计算|系数|破防|防御|减伤", q):
            keywords += ["伤害计算", "面板属性"]
        if re.search(r"满暴|暴击|暴伤|暴击伤害|反堆|面板", q):
            keywords += ["暴击与", "伤害计算"]
        if re.search(r"御魂|套装|246|位置|主属性|副属性|强化|首领", q):
            keywords += ["御魂系统"]
        if re.search(r"速度|行动条|拉条|一速|推条", q):
            keywords += ["速度与行动条"]
        if re.search(r"命中|抵抗|控制|解控|驱散", q):
            keywords += ["效果命中", "控制、驱散"]
        if re.search(r"克制|怕|针对|反制|怎么打|阵容", q):
            keywords += ["克制与反克制", "PVP"]
        if re.search(r"晴明|神乐|八百|源博雅|阴阳师|主角|加成", q):
            keywords += ["阴阳师（主角）"]
        if re.search(r"PVE|副本|逢魔|御魂副本|觉醒|业原火|契灵", q, re.I):
            keywords += ["PVE"]
        if re.search(r"斗技|PVP|上分|ban", q, re.I):
            keywords += ["PVP"]
        picked = []
        for sec in sections[1:]:
            title = sec.split("\n", 1)[0]
            for kw in keywords:
                if kw in title:
                    picked.append("## " + sec.strip())
                    break
        if not picked:
            # 没有命中就给总览（前四节）
            picked = ["## " + s.strip() for s in sections[1:5]]
        text = "\n\n".join(picked)
        return text[:limit]

    def search_context(self, question, max_chars=3000):
        """给 LLM 的检索上下文。"""
        chunks = []
        chars, souls = self.mentions(question)
        # 直接问某式神名但 mentions 没命中时，用 find_char 兜底
        if not chars:
            c, score = self.find_char(question)
            if c and score >= 0.8:
                chars = [c]
        if not souls:
            s, score = self.find_soul(question)
            if s and score >= 0.8:
                souls = [s]
        for c in chars[:2]:
            chunks.append(self.char_card(c))
            chunks.append(self.skill_text(c))
        for s in souls[:2]:
            chunks.append(self.soul_text(s))
        mech = self.mechanics_for(question)
        if mech:
            chunks.append(mech)
        return "\n\n".join(chunks)[:max_chars]


# ---------------- 玩法/副本场景 ----------------
SCENARIOS = [
    {"key": "魂十", "aliases": ["魂十", "魂10", "八岐大蛇十层", "大蛇十层"],
     "search": "魂十 阵容 配置 御魂", "desc": "八岐大蛇十层，吃御魂加成"},
    {"key": "魂土", "aliases": ["魂土", "魂十一", "魂11", "悲鸣"],
     "search": "魂土 阵容 配置 御魂", "desc": "八岐大蛇十一层（悲鸣），吃御魂加成"},
    {"key": "魂王", "aliases": ["魂王", "魂十二", "魂12", "神罚"],
     "search": "魂王 阵容 配置 御魂", "desc": "八岐大蛇十二层（神罚），吃御魂加成"},
    {"key": "魂B", "aliases": ["魂B", "魂玉", "魂十三", "魂13", "虚无"],
     "search": "魂B 魂玉 阵容 配置 御魂", "desc": "八岐大蛇十三层（虚无），吃御魂加成"},
    {"key": "真蛇", "aliases": ["真蛇", "真八岐大蛇", "真·八岐大蛇"],
     "search": "真蛇 阵容 配置 御魂", "desc": "真·八岐大蛇，每周 2 次，不吃御魂加成"},
    {"key": "地域鬼王", "aliases": ["地域鬼王", "地鬼"],
     "search": "地域鬼王 阵容 配置", "desc": "地域鬼王，每日/每周冲榜"},
    {"key": "斗技", "aliases": ["斗技", "pvp", "PVP"],
     "search": "斗技 阵容 配置 御魂", "desc": "斗技 PVP，阵容/翻牌/配速"},
    {"key": "道馆", "aliases": ["道馆", "道馆突破", "道馆防守"],
     "search": "道馆 阵容 配置", "desc": "道馆突破/防守"},
    {"key": "逢魔", "aliases": ["逢魔", "封魔", "逢魔之时", "封魔之时"],
     "search": "逢魔之时 阵容 配置", "desc": "逢魔之时（封魔），首领冲榜"},
    {"key": "业原火", "aliases": ["业原火"], "search": "业原火 阵容 配置", "desc": "业原火副本"},
    {"key": "六道之门", "aliases": ["六道", "六道之门"], "search": "六道之门 阵容 配置", "desc": "六道之门"},
    {"key": "秘闻", "aliases": ["秘闻", "秘闻副本"], "search": "秘闻 阵容 配置", "desc": "秘闻副本"},
    {"key": "结界突破", "aliases": ["结界突破", "突破"], "search": "结界突破 阵容 配置", "desc": "结界突破"},
    {"key": "永生之海", "aliases": ["永生之海", "下海"], "search": "永生之海 阵容 配置", "desc": "永生之海四层"},
    {"key": "协同斗技", "aliases": ["协同斗技"], "search": "协同斗技 阵容 配置", "desc": "协同斗技"},
    {"key": "百鬼弈", "aliases": ["百鬼弈"], "search": "百鬼弈 阵容 配置", "desc": "百鬼弈"},
    {"key": "探索", "aliases": ["困28", "困二十八", "探索副本"], "search": "困28 阵容 配置", "desc": "探索副本（困28 刷狗粮）"},
]


def find_scenario(kb, text):
    """在文本里匹配玩法/副本名，返回 scenario dict 或 None。"""
    if not text:
        return None
    n = kb._norm(text)
    best, best_len = None, 0
    for sc in SCENARIOS:
        for a in sc["aliases"]:
            na = kb._norm(a)
            if na and na in n and len(na) > best_len:
                best, best_len = sc, len(na)
    return best
