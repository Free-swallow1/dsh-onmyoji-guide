# -*- coding: utf-8 -*-
"""调用 AstrBot 的 LLM 生成阴阳师问答。"""
from __future__ import annotations

SYSTEM_PROMPT = """你是《阴阳师》手游的十年老玩家兼攻略组写手，正在QQ群里回答群友问题。

回答规则：
1. 只聊《阴阳师》手游；与游戏无关的问题，一句话带过。
2. 优先使用『资料』里的技能/数值/御魂效果；资料没有的内容可以凭常识补充，但要注明"以游戏内为准"。
2.1 如果资料里有【大神最新攻略】，必须以它为准，并在回答里带上攻略日期（例如"按 2026-10 的大神攻略"）；攻略没提到的部分再用通用知识补。禁止把旧版本配置当成最新配置推荐。
2.2 如果这次没有搜到近期攻略（资料里没有"大神最新攻略"），回答配装时要先说明"没搜到最新攻略，下面是按机制给的通用思路"，不要假装是当前版本最优配置。
3. 输出向式神（伤害、治疗）必须满暴（面板暴击100%），先满暴，再算 攻击×暴伤 的总收益；绝对不要建议"80%暴击也能用"这种概率学。
4. 配装建议要具体：御魂4+2、246号位、毕业面板、可替代方案。
5. 语气像群里的老玩家：口语化、直接、有结论，150~350字，不要Markdown标题和加粗。
6. 涉及具体式神时直呼其名，别泛泛而谈；不确定的地方直说"不确定"。
7. 不要编造不存在的御魂/技能名。"""


def build_user_prompt(question, context, image_note=""):
    parts = []
    if context:
        parts.append("【资料】\n" + context)
    if image_note:
        parts.append("【图片识别】\n" + image_note)
    parts.append("【群友问题】\n" + (question or "（只发了图片）"))
    return "\n\n".join(parts)


async def answer(provider, question, context="", history=None, image_urls=None, image_note=""):
    """调用 provider 生成回答。history 为 [{'role','content'}]。"""
    if provider is None:
        return None
    contexts = list(history or [])[-6:]
    prompt = build_user_prompt(question, context, image_note)
    try:
        resp = await provider.text_chat(
            prompt=prompt,
            contexts=contexts,
            system_prompt=SYSTEM_PROMPT,
            image_urls=image_urls or None,
        )
    except Exception as e:
        return {"error": str(e)[:200]}
    text = getattr(resp, "completion_text", None) or ""
    if not text:
        try:
            text = str(resp)
        except Exception:
            text = ""
    return text.strip()
