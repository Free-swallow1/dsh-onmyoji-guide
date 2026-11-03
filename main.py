# -*- coding: utf-8 -*-
"""AstrBot 阴阳师助手插件。

功能：
- 式神/御魂/阴阳师/机制 查询
- 满暴、面板、伤害、御魂评分计算
- 群内自然语言问答（LLM + 本地知识库）
- 图片识别式神/御魂并给建议
- 群白名单（WebUI 配置或 /yys 加群）
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import time

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from astrbot.api.event import filter, AstrMessageEvent  # noqa: E402
from astrbot.api.star import Context, Star, StarTools  # noqa: E402
from astrbot.api import logger  # noqa: E402
import astrbot.api.message_components as Comp  # noqa: E402

# 插件热重载时清掉旧模块，避免用到上一版代码
for _m in ("yys_kb", "yys_calc", "yys_vision", "yys_llm", "yys_ds"):
    sys.modules.pop(_m, None)

import yys_kb  # noqa: E402
import yys_calc  # noqa: E402
import yys_vision  # noqa: E402
import yys_llm  # noqa: E402
import yys_ds  # noqa: E402

DEFAULT_GROUPS = []
DEFAULT_KEYWORDS = [
    "阴阳师", "痒痒鼠", "御魂", "式神", "满暴", "满爆", "暴击", "暴伤", "配装",
    "毕业", "面板", "阵容", "克制", "斗技", "逢魔", "魂十", "魂十一", "魂十二",
    "觉醒", "业原火", "契灵", "值得练", "怎么养", "6号位", "魂土", "魂王", "真蛇",
    "地鬼", "道馆", "封魔", "魂B", "魂玉", "六道", "秘闻", "下海", "困28",
    "四号位", "二号位", "针女", "破势", "狂骨", "招财", "火灵", "蚌精", "地藏",
    "树妖", "薙魂", "魅妖", "日女", "返魂香", "网切", "伤魂鸟", "心眼", "狰",
    "鸣屋", "阴摩罗", "被服", "珍珠", "雪幽魂", "钟灵", "反枕", "木魅",
]

# 这些词太泛，旧配置里即使有也一律不触发被动回复（避免“改配置”被当成游戏提问）
BAD_KEYWORDS = {"配置", "设置", "速度", "命中", "抵抗", "攻略", "大神", "版本", "更新", "插件"}

# 管理/配置类意图：命中任意一个就不做被动回复，把消息留给主机器人/其他插件
META_WORDS = (
    "配置", "设置", "插件", "管理员", "机器人", "模型", "提示词", "人格", "记忆",
    "重启", "安装", "卸载", "权限", "白名单", "黑名单", "禁言", "撤回", "群主",
    "群管", "本群", "群号", "部署", "日志", "报错", "接口", "密钥",
    "token", "api", "key", "prompt", "系统提示", "换模型", "改一下", "帮我改",
    "调一下", "改配置", "发消息", "指令", "命令",
)

# 明确的提问/求建议语气；没有这些词时，被动回复一律不触发
INTENT_WORDS = (
    "?", "？", "怎么", "多少", "为什么", "吗", "如何", "值不值", "哪个", "比较",
    "带什么", "怎么带", "配装", "搭配", "毕业", "面板", "满暴", "满爆", "攻略",
    "阵容", "克制", "值得", "练吗", "养吗", "打不过", "过不去", "推荐", "强不强",
    "好用", "要不要", "有没有", "怎么样", "求配", "求阵容", "问一下", "请问",
)

HELP_TEXT = (
    "阴阳师助手用法：\n"
    "/yys 天照 —— 式神面板+技能+御魂推荐\n"
    "/yys 技能 天照 —— 完整技能描述\n"
    "/yys 御魂 破势 —— 御魂效果\n"
    "/yys 阴阳师 晴明 —— 主角技能\n"
    "/yys 满暴 天照 —— 满暴凑法\n"
    "/yys 算 攻击8000 暴击95 暴伤260 —— 面板收益\n"
    "/yys 评分 暴击8 暴伤12 攻击加成5 —— 御魂评分\n"
    "/yys 克制 —— 克制关系\n"
    "/yys 加群 123456 —— 管理员加群\n"
    "也可以直接@我提问，或发式神/御魂截图，我会识别并给建议。"
)


class YYSPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.kb = yys_kb.KB()
        self.index = yys_vision.load_index()
        self.history = {}
        self._last_passive = {}
        try:
            self.data_dir = str(StarTools.get_data_dir("astrbot_plugin_yys"))
        except Exception:
            self.data_dir = os.path.join(_PLUGIN_DIR, "data")
        self.ds = yys_ds.DSClient(self.data_dir, cookie=self._cfg("ds_cookie", ""))
        try:
            _cp = os.path.join(self.data_dir, "ds_cookie.txt")
            if not self.ds.cookie and os.path.exists(_cp):
                self.ds.cookie = open(_cp, encoding="utf-8").read().strip()
        except Exception:
            pass
        logger.info(
            "阴阳师插件已加载：式神 %d、御魂 %d、图片索引 %d",
            len(self.kb.chars), len(self.kb.souls), len(self.index),
        )

    # ---------------- 配置与工具 ----------------
    def _cfg(self, key, default=None):
        try:
            v = self.config.get(key, default)
            return default if v is None else v
        except Exception:
            return default

    def _whitelist(self):
        wl = self._cfg("group_whitelist", DEFAULT_GROUPS)
        if isinstance(wl, str):
            wl = [wl]
        return [str(x).strip() for x in (wl or []) if str(x).strip()]

    def _allowed(self, event: AstrMessageEvent):
        gid = str(event.get_group_id() or "")
        if not gid:
            return bool(self._cfg("allow_private", True))
        wl = self._whitelist()
        if not wl:
            # 白名单为空 = 不启用任何群，需要管理员先添加自己的群号
            return False
        return gid in wl

    def _ref_url(self, name):
        for item in self.index:
            if item.get("type") == "char" and item.get("name") == name:
                return yys_vision.ref_url(item.get("file"))
        return ""

    def _provider(self, event):
        try:
            return self.context.get_using_provider(umo=event.unified_msg_origin)
        except Exception:
            try:
                return self.context.get_using_provider()
            except Exception:
                return None

    def _remember(self, gid, q, a):
        h = self.history.setdefault(gid, [])
        h.append({"role": "user", "content": q[:400]})
        h.append({"role": "assistant", "content": a[:600]})
        del h[:-6]

    def _truncate(self, text):
        limit = int(self._cfg("max_reply_chars", 900))
        text = (text or "").strip()
        if len(text) > limit:
            text = text[: limit - 12] + "\n……（截断）"
        return text

    async def _llm_answer(self, event, question, context=None, image_urls=None, image_note="",
                          fresh_guide=""):
        provider = self._provider(event)
        if provider is None:
            return None
        ctx = context if context is not None else self.kb.search_context(question)
        if fresh_guide:
            ctx = (ctx or "") + "\n\n【大神最新攻略（优先采用，别用旧配置）】\n" + fresh_guide
        gid = str(event.get_group_id() or event.get_sender_id() or "")
        hist = self.history.get(gid, [])
        ans = await yys_llm.answer(provider, question, ctx, hist, image_urls, image_note)
        if isinstance(ans, dict) and ans.get("error"):
            logger.warning("LLM 调用失败：%s", ans["error"])
            return None
        return ans

    # ---------------- 图片 ----------------
    async def _image_bytes(self, comp):
        try:
            ref = getattr(comp, "url", None) or getattr(comp, "file", None) or getattr(comp, "path", None) or ""
            ref = str(ref)
            if ref.startswith("base64://"):
                return base64.b64decode(ref[9:])
            if ref.startswith("http://") or ref.startswith("https://"):
                import aiohttp

                timeout = aiohttp.ClientTimeout(total=20)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(ref, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status != 200:
                            return None
                        data = await resp.read()
                        return data if len(data) > 100 else None
            if os.path.exists(ref):
                with open(ref, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.warning("下载图片失败：%s", e)
        return None

    async def _identify(self, event, img_bytes, hint=""):
        """OCR 截图文字 → 本地图标匹配 → 视觉模型。返回 (type, name, item, source, extra)。"""
        ocr = yys_vision.ocr_text(img_bytes)
        if ocr:
            chars, souls = self.kb.mentions(ocr)
            if chars:
                c = chars[0]
                return "式神", c["name"], c, "截图文字", ocr
            if souls:
                s = souls[0]
                return "御魂", s["name"], s, "截图文字", ocr

        item, score, margin = yys_vision.local_match(img_bytes, self.index)
        if item:
            name = item.get("name")
            if item.get("type") == "char" and name in self.kb.by_name:
                return "式神", name, self.kb.by_name[name], "本地图标匹配", ocr
            if item.get("type") == "soul" and name in self.kb.soul_by_name:
                return "御魂", name, self.kb.soul_by_name[name], "本地图标匹配", ocr

        provider = self._provider(event)
        if provider is not None and self._cfg("enable_vision", True):
            res = await yys_vision.vlm_identify_async(provider, img_bytes, self.kb, hint or ocr)
            if isinstance(res, dict) and not res.get("error"):
                typ = str(res.get("type") or "")
                name = str(res.get("name") or "").strip()
                conf = res.get("confidence")
                # 如果模型读到了图里的文字，优先按文字里的名字匹配（截图场景最可靠）
                seen_text = str(res.get("text") or "")
                if seen_text:
                    tc, ts = self.kb.mentions(seen_text)
                    if tc:
                        return "式神", tc[0]["name"], tc[0], "截图文字", (conf, seen_text)
                    if ts:
                        return "御魂", ts[0]["name"], ts[0], "截图文字", (conf, seen_text)
                c, score = self.kb.find_char(name) if name else (None, 0)
                if c and score >= 0.8:
                    # 没有截图文字可依据时，用官方立绘二次确认，避免自信认错
                    if not seen_text:
                        ref = self._ref_url(c["name"])
                        ok = await yys_vision.vlm_confirm(provider, img_bytes, ref, c["name"])
                        if ok is False:
                            return "式神", c["name"], c, "视觉模型", (0.3, ocr)
                    return "式神", c["name"], c, "视觉模型", (conf, ocr)
                s, score = self.kb.find_soul(name) if name else (None, 0)
                if s and score >= 0.8:
                    return "御魂", s["name"], s, "视觉模型", (conf, ocr)
                return typ or "未知", name, None, "视觉模型", (conf, ocr)
        return "未知", "", None, "", ocr

    async def _handle_image_message(self, event, img_comp, text):
        img_bytes = await self._image_bytes(img_comp)
        if not img_bytes:
            return "图片下载失败了，可能是链接过期，重发一张试试？", []
        typ, name, item, source, extra = await self._identify(event, img_bytes, text)
        ocr = extra if isinstance(extra, str) else (extra[1] if isinstance(extra, tuple) else "")
        conf = None
        if isinstance(extra, tuple) and extra and isinstance(extra[0], (int, float)):
            conf = float(extra[0])
        if typ == "式神" and item is not None:
            head = "【识别】%s（%s，%s）" % (item["name"], item.get("rarity") or "", source)
            if conf is not None and conf < 0.65:
                head = "【看图】看着像%s（%s，置信度约%.0f%%）" % (item["name"], source, conf * 100)
            reply = head + "\n" + self.kb.char_card(item)
            reply += "\n需要完整技能或更细的配装，直接问我。"
            return self._truncate(reply)
        if typ == "御魂" and item is not None:
            head = "【识别】%s（%s）" % (item["name"], source)
            if conf is not None and conf < 0.65:
                head = "【看图】看着像%s（%s，置信度约%.0f%%）" % (item["name"], source, conf * 100)
            return self._truncate(head + "\n" + self.kb.soul_text(item))
        # 未识别：交给 LLM 看图回答
        note = "识别结果：%s（%s）" % (name, typ) if name else "未能确定具体式神/御魂。"
        if ocr:
            note += "｜截图文字：" + ocr[:150]
        ans = await self._llm_answer(
            event,
            "这张图里的式神/物品是什么？结合阴阳师知识说说它是什么、有什么用、怎么培养或搭配。",
            context=self.kb.search_context((name or "") + " " + (text or "")),
            image_note=note,
            image_urls=[yys_vision.to_data_uri(img_bytes)],
        )
        if ans:
            return self._truncate("【看图】" + note + "\n" + ans)
        return "这张图我没认出来。可以发清楚一点的式神录/御魂截图，或者直接打名字问我。"

    # ---------------- 文本回复 ----------------
    def _match_reply(self, text):
        chars, souls = self.kb.mentions(text)
        is_question = any(w in text for w in ("?", "？", "怎么", "多少", "为什么", "吗", "如何", "值不值", "哪个", "比较"))
        if chars and len(text) <= 10 and not is_question:
            return self.kb.char_card(chars[0])
        if souls and len(text) <= 10 and not is_question:
            return self.kb.soul_text(souls[0])
        return None

    def _should_passive(self, event, text, has_image):
        """被动回复的准入条件：只接“明确在问阴阳师”的消息。

        原则：默认不插话；管理/配置/闲聊一律放行给主机器人，
        避免“帮我改配置”这类消息被当成游戏提问。
        """
        if has_image:
            return True
        if self._cfg("passive_mode", "keyword") == "off":
            return False
        if not text:
            return False
        if len(text) > 120:
            return False
        if str(event.get_sender_id()) == str(event.get_self_id()):
            return False

        low = text.lower()
        # 0) 去掉 @ 前缀后再判断
        text = re.sub(r"^(@\S+\s*)+", "", text).strip()
        if not text:
            return False
        # 1) 管理/配置类意图，直接让路
        if any(w in low for w in META_WORDS):
            return False

        chars, souls = self.kb.mentions(text)
        scenario = yys_kb.find_scenario(self.kb, text)
        kws = self._cfg("passive_keywords", DEFAULT_KEYWORDS) or []
        hit_kw = any(k and k not in BAD_KEYWORDS and k in text for k in kws)

        # 2) 只发一个式神/御魂名：当作查询，回图卡
        if len(text) <= 8 and not any(x in text for x in ("?", "？", "怎么", "吗")):
            c, sc = self.kb.find_char(text)
            if c and sc >= 0.9 and len(text) <= len(c["name"]) + 1:
                return True
            s2, sc2 = self.kb.find_soul(text)
            if s2 and sc2 >= 0.9 and len(text) <= len(s2["name"]) + 1:
                return True

        # 3) 必须像提问/求建议
        if not any(w in text for w in INTENT_WORDS):
            return False

        # 4) 必须有明确的游戏对象或术语；@ 也不例外
        return bool(chars or souls or scenario or hit_kw
                    or "阴阳师" in text or "痒痒鼠" in text or "yys" in low)

    def _parse_guide_subject(self, text):
        """解析 '/yys 攻略 xxx' 的查询对象：式神 + 玩法/副本名。"""
        t = re.sub(r"(阵容配置|阵容码|阵容|配置|攻略|搭配|作业|怎么打|怎么配|怎么带)+$", "", (text or "").strip()).strip()
        scenario = yys_kb.find_scenario(self.kb, t)
        hero = None
        rest = t
        if scenario:
            for a in scenario["aliases"]:
                rest = rest.replace(a, " ")
        c, sc = self.kb.find_char(rest.strip() or t)
        if c and sc >= 0.9:
            hero = c
        return hero, scenario

    def _need_fresh_guide(self, text):
        if not self._cfg("enable_ds", True):
            return None
        scenario = yys_kb.find_scenario(self.kb, text)
        chars, _ = self.kb.mentions(text)
        if not chars:
            c, sc = self.kb.find_char(text)
            if c and sc >= 0.85:
                chars = [c]
        if not scenario and not chars:
            return None
        words = ("攻略", "配置", "配装", "御魂", "搭配", "阵容", "毕业", "面板", "满暴",
                 "怎么带", "带什么", "怎么打", "最新", "作业", "配速")
        if not scenario and not any(w in text for w in words):
            return None
        return {"hero": chars[0] if chars else None, "scenario": scenario}

    def _make_qr_images(self, codes):
        out = []
        if not codes:
            return out
        d = os.path.join(self.data_dir, "ds_img")
        os.makedirs(d, exist_ok=True)
        for c in codes[: int(self._cfg("ds_max_qr", 2))]:
            name = "qr_%s.png" % re.sub(r"[^0-9A-Za-z]", "", c)[:32]
            p = os.path.join(d, name)
            r = yys_ds.make_qr_image(c, p)
            if r:
                out.append(r)
        return out

    async def _fetch_guide(self, subject):
        """subject: {"hero": char|None, "scenario": dict|None}。返回 (guide_context, image_paths)。"""
        hero = (subject or {}).get("hero")
        scenario = (subject or {}).get("scenario")
        hero_name = hero["name"] if hero else None
        target = (scenario or {}).get("key") or hero_name or "目标"
        try:
            if not self.ds._load_recent():
                try:
                    await asyncio.wait_for(self.ds.refresh_recent(), timeout=25)
                except Exception:
                    pass
            else:
                try:
                    import asyncio as _a
                    _a.create_task(self.ds.refresh_recent())
                except Exception:
                    pass
            guides = await self.ds.search_guides(hero=hero_name, scenario=scenario, limit=1)
        except Exception as e:
            logger.warning("大神攻略检索失败：%s", e)
            return "", []
        if not guides:
            return "", []
        g = guides[0]
        kind = "合集导航" if getattr(g, "is_index", False) else ("单篇" if getattr(g, "title_hit", False) else "相关单篇")
        ctx = "标题：%s\n作者：%s\n日期：%s\n对应：%s\n类型：%s\n正文：%s\n原文：%s" % (
            g.title, g.nick or "未知", g.date_str(), target, kind, g.brief(1200), g.url)
        codes = list(getattr(g, "codes", []) or [])
        if codes:
            ctx += "\n阵容码：" + "；".join(codes[:3])
        imgs = []
        if codes:
            imgs = self._make_qr_images(codes)
        elif int(self._cfg("ds_max_images", 2)) > 0:
            try:
                imgs = await self.ds.download_images(guides, limit=int(self._cfg("ds_max_images", 2)))
            except Exception:
                imgs = []
        return ctx, imgs

    async def _passive_reply(self, event, text, has_image):
        gid = str(event.get_group_id() or "")
        now = time.time()
        if not has_image:
            gap = float(self._cfg("passive_cooldown", 6))
            if now - self._last_passive.get(gid, 0) < gap:
                return None
            self._last_passive[gid] = now

        img_comp = None
        for comp in event.message_obj.message:
            if isinstance(comp, Comp.Image):
                img_comp = comp
                break
        imgs = []
        if img_comp is not None and self._cfg("enable_image", True):
            reply, imgs = await self._handle_image_message(event, img_comp, text)
        else:
            quick = self._match_reply(text)
            if quick and self._cfg("quick_card", True):
                reply = quick
                chars, souls = self.kb.mentions(text)
                if chars:
                    card = self.kb.card_path("char", chars[0]["id"])
                    if card:
                        reply, imgs = "", [card]
                elif souls:
                    card = self.kb.card_path("soul", souls[0]["id"])
                    if card:
                        reply, imgs = "", [card]
            else:
                if not text:
                    return None
                fresh_guide = ""
                subject = self._need_fresh_guide(text)
                if subject is not None:
                    fresh_guide, imgs = await self._fetch_guide(subject)
                reply = await self._llm_answer(event, text, fresh_guide=fresh_guide)
                if not reply:
                    chars, souls = self.kb.mentions(text)
                    if chars:
                        reply = self.kb.char_card(chars[0])
                    elif souls:
                        reply = self.kb.soul_text(souls[0])
                    else:
                        reply = "让我查一下……这个我暂时没把握，换个说法或直接发式神名给我？"
        if reply or imgs:
            if reply:
                self._remember(gid, text, reply)
            return self._truncate(reply or ""), imgs
        return None

    # ---------------- 指令 ----------------
    def _command_args(self, event, names):
        raw = (event.message_str or "").strip()
        for n in names:
            if raw.lower().startswith(n.lower()):
                return raw[len(n):].strip()
        return raw

    @filter.command("yys", alias={"痒痒鼠"})
    async def yys_cmd(self, event: AstrMessageEvent):
        """阴阳师查询：式神/御魂/满暴/算面板/克制"""
        if not self._allowed(event):
            return
        msg = self._command_args(event, ["yys", "痒痒鼠"])
        if not msg:
            yield event.plain_result(HELP_TEXT)
            return

        if msg.startswith(("大神登录", "扫码登录")):
            rest = msg.split(" ", 1)[1].strip() if " " in msg else ""
            async for r in self._ds_login(event, rest):
                yield r
            return
        if msg.startswith("大神状态"):
            yield event.plain_result(await self._ds_status())
            return

        if msg.startswith(("攻略", "配置", "大神")):
            rest = msg[2:].strip() if msg.startswith("攻略") else msg[2:].strip()
            async for r in self._guide_reply(event, rest):
                yield r
            return

        for prefix, handler in (
            ("技能", self._cmd_skills),
            ("御魂", self._cmd_soul),
            ("阴阳师", self._cmd_onmyoji),
            ("满暴", self._cmd_manbao),
            ("算", self._cmd_calc),
            ("面板", self._cmd_calc),
            ("评分", self._cmd_score),
            ("克制", self._cmd_counter),
            ("出处", self._cmd_where),
        ):
            if msg.startswith(prefix):
                rest = msg[len(prefix):].strip()
                card = ""
                if prefix == "技能":
                    c0, _ = self.kb.find_char(rest)
                    card = self.kb.card_path("char", c0["id"]) if c0 else ""
                elif prefix == "御魂":
                    s0, _ = self.kb.find_soul(rest)
                    card = self.kb.card_path("soul", s0["id"]) if s0 else ""
                elif prefix == "阴阳师":
                    for nm, oid in (("晴明",10),("神乐",11),("八百比丘尼",12),("源博雅",13),("源赖光",15),("藤原道长",16)):
                        if nm in rest:
                            card = self.kb.card_path("onmyoji", oid)
                            break
                if card:
                    yield event.image_result(card)
                    return
                out = await handler(event, rest)
                if out:
                    if prefix == "技能":
                        out = out[:2600]
                    yield event.plain_result(out)
                return

        if msg.startswith("加群"):
            yield event.plain_result(await self._cmd_add_group(event, msg[2:].strip()))
            return
        if msg.startswith("群列表"):
            yield event.plain_result("当前启用群：\n" + "\n".join(self._whitelist()))
            return
        if msg.startswith("帮助") or msg in ("help", "？", "?"):
            yield event.plain_result(HELP_TEXT)
            return

        # 默认：短词=卡片，长句=LLM
        c, score = self.kb.find_char(msg)
        if c and len(msg) <= len(c["name"]) + 3:
            card = self.kb.card_path("char", c["id"])
            if card:
                yield event.image_result(card)
            else:
                yield event.plain_result(self._truncate(self.kb.char_card(c)))
            return
        if len(msg) <= 6:
            s, _ = self.kb.find_soul(msg)
            if s:
                card = self.kb.card_path("soul", s["id"])
                if card:
                    yield event.image_result(card)
                else:
                    yield event.plain_result(self._truncate(self.kb.soul_text(s)))
                return
        ans = await self._llm_answer(event, msg)
        if ans:
            yield event.plain_result(self._truncate(ans))
        else:
            yield event.plain_result("没查到。试试 /yys 天照，或 /yys 帮助 看用法。")

    async def _ds_status(self):
        if not self.ds.cookie:
            try:
                p = os.path.join(self.data_dir, "ds_cookie.txt")
                if os.path.exists(p):
                    self.ds.cookie = open(p, encoding="utf-8").read().strip()
            except Exception:
                pass
        if not self.ds.cookie:
            return "大神：当前是游客模式（大多数公开攻略能看）。如果提示要登录，发 /yys 大神登录 扫码。"
        try:
            import aiohttp

            async with aiohttp.ClientSession() as s:
                async with s.get("https://inf.ds.163.com/v1/web/base/mine/userInfo",
                                 headers=self.ds._headers(), timeout=10) as r:
                    data = await r.json()
            if str(data.get("code")) == "200":
                return "大神：已登录（Cookie 有效）。"
            return "大神：Cookie 可能失效了，重新 /yys 大神登录 扫码。"
        except Exception as e:
            return "大神：登录状态检查失败（%s）" % str(e)[:60]

    async def _ds_login(self, event, rest=""):
        if not event.is_admin():
            yield event.plain_result("只有管理员能发起扫码登录。")
            return
        if rest.startswith(("cookie", "Cookie", "COOKIE")):
            cookie = rest.split(" ", 1)[1].strip() if " " in rest else rest[6:].strip()
            cookie = cookie.lstrip("=:").strip()
            if len(cookie) < 20:
                yield event.plain_result("格式：/yys 大神登录 cookie NTES_SESS=...; S_INFO=...")
                return
            try:
                with open(os.path.join(self.data_dir, "ds_cookie.txt"), "w", encoding="utf-8") as f:
                    f.write(cookie)
                self.ds.cookie = cookie
            except Exception as e:
                yield event.plain_result("保存失败：%s" % str(e)[:60])
                return
            yield event.plain_result("Cookie 已保存。%s" % await self._ds_status())
            return
        import aiohttp

        yield event.plain_result("正在获取大神登录二维码……")
        state, payload = "timeout", ""
        try:
            jar = aiohttp.CookieJar(unsafe=True)
            async with aiohttp.ClientSession(cookie_jar=jar, timeout=aiohttp.ClientTimeout(total=30)) as s:
                uuid, img = await yys_ds.qr_login_start(s)
                if not uuid or not img:
                    yield event.plain_result("二维码获取失败，稍后再试。")
                    return
                p = os.path.join(self.data_dir, "ds_qr.png")
                with open(p, "wb") as f:
                    f.write(img)
                yield event.image_result(p)
                yield event.plain_result("请用网易大神 App 扫码并在手机上确认（180 秒内有效）。扫完我会提示。")

                def on_status(code, raw):
                    logger.info("大神扫码状态：%s %s", code, raw[:800])

                state, payload = await yys_ds.qr_login_poll(s, uuid, timeout=180, on_status=on_status)
        except Exception as e:
            logger.warning("大神扫码登录失败：%s", e)
            yield event.plain_result("登录流程出错：%s" % str(e)[:80])
            return

        if state == "ok":
            try:
                with open(os.path.join(self.data_dir, "ds_cookie.txt"), "w", encoding="utf-8") as f:
                    f.write(payload)
                self.ds.cookie = payload
            except Exception:
                pass
            ok = await self._ds_status()
            yield event.plain_result("扫码成功，Cookie 已保存。%s" % ok)
            return
        if state == "expired":
            yield event.plain_result("二维码已过期，重新发 /yys 大神登录 生成新码。")
            return
        if state == "nocookie":
            logger.warning("扫码成功但未取得 Cookie：%s", str(payload)[:300])
            yield event.plain_result(
                "扫到了，但没换到登录态。可以先用游客模式；或把浏览器登录后的 Cookie 填到插件配置 ds_cookie。")
            return
        yield event.plain_result("没等到确认（%s）。确认手机点过“确认登录”后，再发一次 /yys 大神登录。" % (payload or "超时"))

    async def _guide_reply(self, event, rest):
        """最新攻略：/yys 攻略 天照  /yys 攻略 魂土配置"""
        L = chr(10)
        hero, scenario = self._parse_guide_subject(rest)
        if not hero and not scenario:
            yield event.plain_result(
                "用法：/yys 攻略 <式神或玩法>" + L +
                "例：/yys 攻略 魂土配置、/yys 攻略 魂王、/yys 攻略 真蛇、/yys 攻略 地域鬼王、" + L +
                "/yys 攻略 斗技阵容、/yys 攻略 道馆、/yys 攻略 逢魔、/yys 攻略 天照魂土配置")
            return
        label = "-".join([x for x in [(scenario or {}).get("key"), (hero or {}).get("name")] if x])
        yield event.plain_result("正在网易大神搜「%s」的最新阵容/配置……" % label)
        try:
            if not self.ds._load_recent():
                await asyncio.wait_for(self.ds.refresh_recent(), timeout=30)
        except Exception:
            pass
        guides = await self.ds.search_guides(
            hero=hero["name"] if hero else None, scenario=scenario, limit=2)
        if not guides:
            msg = ""
            if scenario:
                msg += "（%s：%s）%s" % (scenario["key"], scenario.get("desc", ""), L)
            if hero:
                msg += self.kb.char_card(hero)
            else:
                msg += ("大神上没搜到「%s」近期的阵容攻略。可以先按「拉条/打火 + 主C + 收尾」的通用框架配，"
                        "具体式神的面板和御魂发名字问我。" % label)
            yield event.plain_result(self._truncate(msg))
            return
        g = guides[0]
        age_days = (time.time() * 1000 - g.time) / 86400000 if g.time else 9999
        warn = ""
        if age_days > 365:
            warn = "（注意：这条攻略是 %s 的，可能已过时，配置仅作参考）%s" % (g.date_str(), L)
        if getattr(g, "is_index", False):
            tag = "（合集导航，里面有%s的分篇，点原文找）" % label
        elif getattr(g, "title_hit", False):
            tag = ""
        else:
            tag = "（相关攻略，标题没直接写%s）" % label
        head = "【大神攻略·%s】" % (scenario["key"] if scenario else "式神")
        text = "%s%s%s%s%s作者：%s｜%s%s" % (
            warn, head, g.title, tag, L, g.nick or "未知", g.date_str(), L)
        if scenario and scenario.get("desc"):
            text += "（%s：%s）%s" % (scenario["key"], scenario["desc"], L)
        codes = list(getattr(g, "codes", []) or [])
        text += g.brief(300 if getattr(g, "is_index", False) else 500)
        if codes:
            text += "%s阵容码：%s" % (L, "；".join(codes[:3]))
        if g.url:
            text += "%s原文：%s" % (L, g.url)
        text += "%s（%s）" % (L, "优先用阵容码导入；配速以攻略和图为准" if codes else "配速以攻略和图为准")
        yield event.plain_result(self._truncate(text))
        if codes:
            imgs = self._make_qr_images(codes)
        else:
            imgs = await self.ds.download_images(guides, limit=int(self._cfg("ds_max_images", 2)))
        for p in imgs:
            try:
                yield event.image_result(p)
            except Exception as e:
                logger.warning("发送攻略图片失败：%s", e)

    async def _cmd_skills(self, event, rest):
        c, _ = self.kb.find_char(rest)
        if not c:
            return "没找到这个式神，确认下名字？"
        return self.kb.skill_text(c)

    async def _cmd_soul(self, event, rest):
        s, _ = self.kb.find_soul(rest)
        if not s:
            return "没找到这个御魂，确认下名字？"
        return self.kb.soul_text(s)

    async def _cmd_onmyoji(self, event, rest):
        names = ["晴明", "神乐", "八百比丘尼", "源博雅", "源赖光", "藤原道长"]
        for n in names:
            if n in rest:
                return self.kb.onmyoji_text(n) or "暂无数据"
        return "主角：" + "、".join(names) + "\n例：/yys 阴阳师 晴明"

    async def _cmd_manbao(self, event, rest):
        c, _ = self.kb.find_char(rest)
        if not c:
            return "格式：/yys 满暴 天照"
        return yys_calc.manbao_report(c)

    async def _cmd_calc(self, event, rest):
        panel = yys_calc.parse_panel(rest)
        c, _ = self.kb.find_char(rest)
        if not panel and c:
            return yys_calc.manbao_report(c)
        if not panel:
            return "格式：/yys 算 攻击8000 暴击95 暴伤260"
        return yys_calc.panel_report(panel.get("atk"), panel.get("crit"), panel.get("critdmg"), c)

    async def _cmd_score(self, event, rest):
        p = yys_calc.parse_panel(rest)
        crit = p.get("crit", 0)
        critdmg = p.get("critdmg", 0)
        atk = p.get("atk", 0)
        spd = p.get("spd", 0)
        return yys_calc.soul_score(crit, critdmg, atk, spd) + "\n（若把'攻击'当攻击加成%，就是攻击加成分）"

    async def _cmd_counter(self, event, rest):
        text = self.kb.mechanics_for("克制与反克制 " + rest, limit=2200)
        if not text:
            return "机制库未加载。"
        return text

    async def _cmd_where(self, event, rest):
        s, _ = self.kb.find_soul(rest)
        if not s:
            return "格式：/yys 出处 破势"
        return "【%s】获取途径：\n%s" % (s["name"], s.get("way") or "未知")

    async def _cmd_add_group(self, event, gid_text):
        if not event.is_admin():
            return "只有管理员能加群。"
        gid = "".join(ch for ch in gid_text if ch.isdigit())
        if not gid:
            return "格式：/yys 加群 123456789"
        wl = self._whitelist()
        if gid in wl:
            return "群 %s 已经在列表里了。" % gid
        wl.append(gid)
        try:
            self.config["group_whitelist"] = wl
            if hasattr(self.config, "save_config"):
                self.config.save_config()
        except Exception as e:
            logger.warning("保存群列表失败：%s", e)
        return "已添加群 %s。当前：%s" % (gid, "、".join(wl))

    # 便捷指令
    @filter.command("式神")
    async def shishen_cmd(self, event: AstrMessageEvent):
        """查询式神面板与御魂推荐"""
        if not self._allowed(event):
            return
        c, _ = self.kb.find_char(self._command_args(event, ["式神"]))
        if not c:
            yield event.plain_result("格式：/式神 天照")
            return
        card = self.kb.card_path("char", c["id"])
        if card:
            yield event.image_result(card)
        else:
            yield event.plain_result(self._truncate(self.kb.char_card(c)))

    @filter.command("御魂")
    async def yuhun_cmd(self, event: AstrMessageEvent):
        """查询御魂效果"""
        if not self._allowed(event):
            return
        s, _ = self.kb.find_soul(self._command_args(event, ["御魂"]))
        if not s:
            yield event.plain_result("格式：/御魂 破势")
            return
        card = self.kb.card_path("soul", s["id"])
        if card:
            yield event.image_result(card)
        else:
            yield event.plain_result(self._truncate(self.kb.soul_text(s)))

    @filter.command("满暴")
    async def manbao_cmd(self, event: AstrMessageEvent):
        """查看式神满暴凑法"""
        if not self._allowed(event):
            return
        c, _ = self.kb.find_char(self._command_args(event, ["满暴"]))
        if not c:
            yield event.plain_result("格式：/满暴 天照")
            return
        yield event.plain_result(self._truncate(yys_calc.manbao_report(c)))

    # 群消息监听
    @filter.event_message_type(filter.EventMessageType.ALL, priority=50)
    async def on_all_message(self, event: AstrMessageEvent):
        """群内自然语言问答与图片识别"""
        text = (event.message_str or "").strip()
        # 去掉开头的 @机器人 前缀，避免 “@bot 天照” 被当成普通句子
        text = re.sub(r"^(@\S+\s*)+", "", text).strip()
        if text.startswith(("/", "／")):
            return
        # 已被指令解析的消息交给指令 handler，避免重复回复
        try:
            if event.get_extra("parsed_params") is not None:
                return
        except Exception:
            pass
        if text.split(" ")[0] in ("yys", "式神", "御魂", "满暴", "痒痒鼠"):
            return
        if not self._allowed(event):
            return
        has_image = any(isinstance(c, Comp.Image) for c in event.message_obj.message)
        if not has_image and not text:
            return
        if not self._should_passive(event, text, has_image):
            return
        try:
            out = await self._passive_reply(event, text, has_image)
        except Exception as e:
            logger.error("阴阳师问答出错：%s", e, exc_info=True)
            return
        if out:
            reply, imgs = out if isinstance(out, tuple) else (out, [])
            if reply:
                yield event.plain_result(reply)
            for p in imgs or []:
                try:
                    yield event.image_result(p)
                except Exception as e:
                    logger.warning("发送攻略图片失败：%s", e)
            # 不 stop_event，避免抢掉主机器人/其他插件的指令

    async def terminate(self):
        logger.info("阴阳师插件已卸载")
