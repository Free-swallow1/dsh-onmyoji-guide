# -*- coding: utf-8 -*-
"""阴阳师面板/暴击/伤害计算。"""
from __future__ import annotations

import re


def _num(x):
    try:
        return float(str(x).replace("%", "").strip())
    except Exception:
        return None


def parse_panel(text):
    """从文本里解析 攻击/暴击/暴伤。支持 '攻击8000 暴击95 暴伤260'。"""
    out = {}
    patterns = {
        "atk": r"(?:攻击|面板攻击|攻击力)\s*[:：=]?\s*(\d+(?:\.\d+)?)",
        "crit": r"(?:暴击率|暴击)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*%?",
        "critdmg": r"(?:暴击伤害|暴伤)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*%?",
        "hp": r"(?:生命|血量)\s*[:：=]?\s*(\d+(?:\.\d+)?)",
        "spd": r"(?:速度)\s*[:：=]?\s*(\d+(?:\.\d+)?)",
    }
    for k, p in patterns.items():
        m = re.search(p, text)
        if m:
            out[k] = float(m.group(1))
    return out


def panel_report(atk=None, crit=None, critdmg=None, char=None):
    """计算满暴判定、期望系数、攻击×暴伤。crit/critdmg 为百分数。"""
    lines = []
    base = ""
    if char:
        st = char.get("stats") or {}
        base = "【%s】基础：攻击%s 暴击%s 暴伤%s\n" % (
            char["name"],
            st.get("atk", "?"),
            ("%g%%" % round((st.get("cri") or 0) * 100, 1)),
            ("%g%%" % round((st.get("crid") or 0) * 100, 1)),
        )
        if atk is None and st.get("atk"):
            atk = float(st["atk"])
        if crit is None and st.get("cri") is not None:
            crit = float(st["cri"]) * 100
        if critdmg is None and st.get("crid") is not None:
            critdmg = float(st["crid"]) * 100
    if crit is None:
        crit = 0.0
    if critdmg is None:
        critdmg = 150.0
    crit = max(0.0, min(100.0, crit))
    cd = max(0.0, critdmg) / 100.0
    full = 1.0 + cd
    expected = crit / 100.0 * full + (1 - crit / 100.0) * 1.0

    lines.append(base + "面板：攻击 %s｜暴击 %g%%｜暴伤 %g%%" % (
        int(atk) if atk else "?", crit, critdmg))
    if crit >= 100:
        lines.append("✅ 满暴达成（暴击 100%），溢出无收益。")
    else:
        lines.append("⚠️ 未满暴：还差 %g%% 暴击。输出必须满暴，否则每段伤害都在赌。" % (100 - crit))
    lines.append("满暴系数（攻击×暴伤）：×%.3f" % full)
    lines.append("当前期望系数：×%.3f（暴击率 %.0f%%）" % (expected, crit))
    if crit < 100:
        gain = (full - expected) / expected * 100
        lines.append("补满暴后期望提升：+%.1f%%（这是稳定收益，不是概率）" % gain)
    if atk:
        lines.append("满暴后 攻击×暴伤 = %d × %.2f = %d" % (atk, full, int(atk * full)))

    # 攻击 vs 暴伤 边际收益
    if atk and crit >= 100:
        atk_gain = 1.0 / atk * 100  # 每 1 点攻击
        cd_gain = (0.01 / full) * 100  # 每 1% 暴伤
        lines.append("边际：+1%% 攻击 → 总系数 +1.0%%；+1%% 暴伤 → 总系数 +%.2f%%（当前暴伤下）" % (cd_gain))
        ratio = (1.0 / 100.0) / (0.01 / full)
        lines.append("即 1%% 暴伤 ≈ %.2f%% 攻击，暴伤越高攻击越值钱。" % ratio)
    return "\n".join(lines)


def manbao_report(char, six_slot="crit", set_crit=30.0, sub_crit=None):
    """满暴凑法。six_slot: crit(6号位暴击55%) / cd(6号位暴伤89%)。"""
    st = char.get("stats") or {}
    base = (st.get("cri") or 0) * 100
    need_total = 100.0
    main = 55.0 if six_slot == "crit" else 0.0
    have = base + main + set_crit
    lines = ["【%s 满暴方案】" % char["name"]]
    lines.append("基础暴击 %g%% + 6号位%s + 两个暴击2件套 %g%% = %g%%" % (
        base, ("暴击55%" if six_slot == "crit" else "暴伤（0暴击）"), set_crit, have))
    if have >= need_total:
        lines.append("已满暴，副属性可以全堆暴伤/攻击。")
    else:
        gap = need_total - have
        lines.append("还差 %g%% 暴击，需要副属性凑（6 个位置平均 %.1f%%/个）。" % (gap, gap / 6))
    other = "暴伤（89%）" if six_slot == "crit" else "暴击（55%）"
    alt_have = base + (0 if six_slot == "crit" else 55.0) + set_crit
    lines.append("若 6 号位改带%s：暴击 = %g%%，缺口 %g%%。" % (
        other, alt_have, max(0, 100 - alt_have)))
    lines.append("结论：6号位暴击=68%暴伤换55%暴击，容易满暴、上限低；6号位暴伤=上限高但要反堆暴击。")
    return "\n".join(lines)


def soul_score(crit=0.0, critdmg=0.0, atk_pct=0.0, speed=0.0):
    """输出御魂双暴评分（社区常用口径）。"""
    score = crit * 2 + critdmg + atk_pct * 0.5 + speed * 0.5
    if score >= 40:
        verdict = "极品，直接锁"
    elif score >= 30:
        verdict = "很好，可以留"
    elif score >= 20:
        verdict = "过渡可用"
    else:
        verdict = "建议当狗粮/奉纳"
    return "双暴评分：%.1f（暴击×2 + 暴伤 + 攻击加成×0.5 + 速度×0.5）\n评价：%s" % (score, verdict)
