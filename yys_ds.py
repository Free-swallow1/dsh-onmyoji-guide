# -*- coding: utf-8 -*-
"""网易大神（ds.163.com）攻略检索：百度站内搜索 → 大神 feed 详情 → 图文。"""
from __future__ import annotations

import asyncio
import html as htmlmod
import json
import os
import re
import time
import urllib.parse

API = "https://inf.ds.163.com"
SEARCH = "https://m.so.com/s?q="
BING = "https://cn.bing.com/search?format=rss&q="
BAIDU = "https://www.baidu.com/s"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")

_TAG_RE = re.compile(r"<[^>]+>")
CODE_RE = re.compile(r"\|\s*TA[C]?\s*\|\s*[0-9a-fA-F]{16,64}")


def extract_codes(*texts):
    """从正文里提取阴阳师阵容码（|TA|xxx / |TAC|xxx），去重保序。"""
    out = []
    for t in texts:
        if not t:
            continue
        for m in CODE_RE.findall(t):
            code = re.sub(r"\s+", "", m)
            if code not in out:
                out.append(code)
    return out


def make_qr_image(data, path):
    """生成阵容码二维码；没装 qrcode 库时返回 None。"""
    try:
        import qrcode

        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path)
        return path
    except Exception:
        return None


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = htmlmod.unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_img_urls(long_text):
    if not long_text:
        return []
    urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', long_text, re.I)
    return [u for u in urls if u.startswith("http")]


class Guide:
    def __init__(self, data):
        self.__dict__.update(data)
        if not getattr(self, "codes", None):
            self.codes = extract_codes(self.text, self.long_text)

    def brief(self, limit=700):
        body = self.long_text or self.text
        body = re.sub(r"#([^#]{1,20})#", "", body)
        # 去掉推广/求赞类噪音行
        lines = []
        for line in body.split("\n"):
            t = line.strip()
            if not t:
                continue
            if re.search(r"氪金|充值|首充|折扣|优惠|福利|抽奖|点赞|转发|关注|传送门|加群|交流群|接单|业务|私信", t) and len(t) < 140:
                continue
            lines.append(t)
        body = " ".join(lines)
        body = re.sub(r"https?://\S+", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        return body[:limit]

    def date_str(self):
        try:
            return time.strftime("%Y-%m-%d", time.localtime(self.time / 1000))
        except Exception:
            return ""


class DSClient:
    def __init__(self, data_dir, cookie=""):
        self.data_dir = data_dir
        self.cookie = (cookie or "").strip()
        self.cache = {}
        self.cache_ttl = 6 * 3600
        self.img_dir = os.path.join(data_dir, "ds_img")
        os.makedirs(self.img_dir, exist_ok=True)
        self.recent_path = os.path.join(data_dir, "ds_recent.json")
        self._recent = None
        self._recent_ts = 0
        self._id_cache = {}
        self._backend_block = {}

    # ---------- 基础请求 ----------
    def _headers(self, mobile=False):
        h = {"User-Agent": MOBILE_UA if mobile else UA,
             "Referer": "https://ds.163.com/",
             "Accept-Language": "zh-CN,zh;q=0.9"}
        if self.cookie and not mobile:
            h["Cookie"] = self.cookie
        return h

    async def _get(self, session, url, timeout=12, binary=False, mobile=False):
        async with session.get(url, headers=self._headers(mobile), timeout=timeout) as r:
            if r.status != 200:
                return None
            return await r.read() if binary else await r.text()

    # ---------- 搜索 ----------
    async def _search_360(self, session, wd, limit):
        try:
            text = await self._get(session, SEARCH + urllib.parse.quote(wd), timeout=15, mobile=True) or ""
        except Exception:
            return []
        if not text or "验证" in text or "qcaptcha" in text:
            return []
        return self._ids_from_html(text, limit)

    async def _search_bing(self, session, wd, limit):
        try:
            text = await self._get(session, BING + urllib.parse.quote(wd), timeout=15) or ""
        except Exception:
            return []
        if not text or "<rss" not in text:
            return []
        links = re.findall(r"<link>(https://ds\.163\.com/(?:feed|article)/[0-9a-f]+)/?<", text)
        out, seen = [], set()
        for u in links:
            fid = u.rstrip("/").rsplit("/", 1)[-1]
            if fid not in seen:
                seen.add(fid)
                out.append(fid)
            if len(out) >= limit:
                break
        return out

    async def _search_baidu(self, session, wd, limit):
        try:
            text = await self._get(session, BAIDU + "?wd=" + urllib.parse.quote(wd), timeout=15) or ""
        except Exception:
            return []
        if not text or "百度安全验证" in text or "wappass" in text:
            return []
        return self._ids_from_html(text, limit)

    def _ids_from_html(self, text, limit):
        ids = re.findall(r"ds\.163\.com/(?:feed|article)/([0-9a-f]{20,32})", text)
        out, seen = [], set()
        for i in ids:
            if i not in seen:
                seen.add(i)
                out.append(i)
            if len(out) >= limit:
                break
        return out

    async def search_ids(self, session, query, limit=12):
        """多搜索源兜底：360 移动 → Bing RSS → 百度。带冷却与缓存。"""
        wd = "site:ds.163.com " + query
        cache_key = "ids:" + wd
        now = time.time()
        hit = self._id_cache.get(cache_key)
        if hit and now - hit[0] < 86400:
            return hit[1]
        backends = [("360", self._search_360), ("bing", self._search_bing), ("baidu", self._search_baidu)]
        for name, fn in backends:
            if now < self._backend_block.get(name, 0):
                continue
            try:
                ids = await fn(session, wd, limit)
            except Exception:
                ids = []
            if ids:
                self._id_cache[cache_key] = (now, ids)
                return ids
            # 失败后冷却，避免把搜索源打到验证码
            self._backend_block[name] = now + (1800 if name != "bing" else 600)
        self._id_cache[cache_key] = (now, [])
        return []

    # ---------- 详情 ----------    # ---------- 详情 ----------
    async def fetch_feed(self, session, fid):
        url = API + "/v1/web/feed/basic/facade?feedId=" + fid
        try:
            raw = await self._get(session, url, timeout=12)
            j = json.loads(raw)
        except Exception:
            return None
        feed = (j.get("result") or {}).get("feed")
        if not feed:
            return None
        try:
            content = json.loads(feed.get("content") or "{}")
        except Exception:
            content = {}
        body = content.get("body") or {}
        text = (body.get("text") or "").strip()
        title = (body.get("title") or "").strip()
        long_text = strip_html(body.get("longText") or "")
        images = []
        for m in body.get("media") or []:
            mt = (m.get("mimeType") or "").lower()
            if mt.startswith("image/") and m.get("url"):
                images.append(m["url"])
            elif mt.startswith("video/") and m.get("cover"):
                images.append(m["cover"])
        for u in extract_img_urls(body.get("longText") or ""):
            if u not in images:
                images.append(u)
        if not (text or title or long_text):
            return None
        nick = ""
        try:
            nick = json.loads(feed.get("appRole") or "{}").get("nick") or ""
        except Exception:
            pass
        topics = [t.get("topicName") for t in (feed.get("topicInfoList") or []) if t.get("topicName")]
        rec = feed.get("record") or {}
        codes = extract_codes(text, long_text)
        return Guide({
            "id": fid,
            "codes": codes,
            "type": int(feed.get("type") or 0),
            "time": int(feed.get("createTime") or 0),
            "nick": nick,
            "title": title or (text.split("\n")[0][:40] if text else ""),
            "text": text,
            "long_text": long_text,
            "images": images,
            "topics": topics,
            "likes": rec.get("likeCount") or 0,
            "url": "https://ds.163.com/%s/%s/" % ("article" if int(feed.get("type") or 0) == 6 else "feed", fid),
        })

    # ---------- 最近动态缓存 ----------
    def _load_recent(self):
        if self._recent is not None:
            return self._recent
        try:
            with open(self.recent_path, encoding="utf-8") as f:
                data = json.load(f)
            self._recent = [Guide(d) for d in data if isinstance(d, dict)]
        except Exception:
            self._recent = []
        return self._recent

    def _save_recent(self):
        try:
            data = [g.__dict__ for g in (self._recent or [])][:600]
            with open(self.recent_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass

    async def feed_ids(self, session, page, count=60, query=None):
        if query is None:
            query = {
                "sortType": "time", "inRecommend": 1, "recommendDays": 0,
                "categoryId": "-1", "title": "推荐",
                "tags": ["5af7dbbbd54568048c609f3b"], "feedTypes": [3],
            }
        url = (API + "/v1/web/recommend/square/feed/custom/with-fixed-feedIds"
               "?count=%d&page=%d&squareId=5bed6281d545682b8bb8a761&query=%s&feedIdList="
               % (count, page, urllib.parse.quote(json.dumps(query, separators=(",", ":")))))
        try:
            raw = await self._get(session, url, timeout=15)
            return ((json.loads(raw).get("result") or {}).get("feedIdList")) or []
        except Exception:
            return []

    async def refresh_recent(self, pages=2):
        """拉取圈子里最新动态 + 长文攻略，补充搜索源搜不到的新攻略。"""
        queries = [
            ({"sortType": "time", "inRecommend": 1, "recommendDays": 0, "categoryId": "-1",
              "title": "推荐", "tags": ["5af7dbbbd54568048c609f3b"], "feedTypes": [3]}, pages),
            ({"sortType": "consume", "inRecommend": 1, "recommendDays": 90, "categoryId": "-1",
              "title": "推荐长文", "tags": ["5af7dbbbd54568048c609f3b"], "feedTypes": [6]}, 2),
            ({"sortType": "time", "inRecommend": 1, "recommendDays": 30, "categoryId": "-1",
              "title": "推荐", "tags": ["5af7dbbbd54568048c609f3b"], "feedTypes": [2]}, 1),
        ]
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                ids = []
                for q, npages in queries:
                    for pg in range(npages):
                        got = await self.feed_ids(session, pg, query=q)
                        for i in got:
                            if i not in ids:
                                ids.append(i)
                if not ids:
                    return 0
                known = {g.id for g in self._load_recent()}
                todo = [i for i in ids if i not in known][:150]
                if not todo:
                    return 0
                feeds = await asyncio.gather(*[self.fetch_feed(session, i) for i in todo])
        except Exception:
            return 0
        cur = self._load_recent()
        cur.extend([f for f in feeds if f])
        dedup = {}
        for g in cur:
            dedup[g.id] = g
        cur = sorted(dedup.values(), key=lambda g: -g.time)[:800]
        self._recent = cur
        self._save_recent()
        self._recent_ts = time.time()
        return len(feeds)

    def recent_matches(self, hero):
        out = []
        for g in self._load_recent():
            body = g.title + " " + g.text + " " + (g.long_text or "")[:800]
            if hero and hero in body:
                out.append(g)
        return out

    # ---------- 组合检索 ----------
    async def search_guides(self, hero=None, scenario=None, keywords=None, limit=2, max_days=400):
        """搜式神攻略或玩法/副本（魂土/真蛇/斗技等）阵容。"""
        subject = (scenario or {}).get("key") or hero or ""
        aliases = list((scenario or {}).get("aliases") or ([hero] if hero else []))
        key = "%s|%s" % (subject, ",".join(keywords or []))
        now = time.time()
        hit = self.cache.get(key)
        if hit and now - hit[0] < (self.cache_ttl if hit[1] else 300):
            return hit[1]
        queries = []
        if scenario:
            queries.append(scenario.get("search") or ("%s 阵容 配置" % scenario["key"]))
            queries.append("%s 攻略 阵容 御魂" % scenario["key"])
            if hero:
                queries.append("%s %s 配置" % (hero, scenario["key"]))
        elif hero:
            queries.append("%s 御魂 配置" % hero)
            queries.append("%s 攻略 阵容" % hero)
        else:
            queries.append(" ".join(keywords or ["阴阳师", "攻略"]))
        guides = []
        try:
            guides.extend(self.recent_matches_any(aliases))
        except Exception:
            pass
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                ids = []
                for q in queries:
                    got = await self.search_ids(session, q, limit=10)
                    for i in got:
                        if i not in ids:
                            ids.append(i)
                if ids:
                    guides.extend(await asyncio.gather(*[self.fetch_feed(session, i) for i in ids[:14]]))
        except Exception:
            pass
        if not guides:
            self.cache[key] = (now, [])
            return []
        now_ms = time.time() * 1000
        results = []
        for g in guides:
            if not g:
                continue
            body = (g.title + " " + g.text + " " + g.long_text[:1500])
            score = 0.0
            build_hits = sum(1 for kw in ("御魂", "配置", "配装", "阵容", "阵容码", "满暴", "面板", "配速", "御魂搭配", "速度")
                             if kw in body)
            cnt = sum(body.count(a) for a in aliases) if aliases else 0
            title_hit = bool(aliases) and any(a in g.title for a in aliases)
            near = bool(aliases) and any(
                re.search(re.escape(a) + r".{0,60}(御魂|配置|配装|阵容|阵容码|面板|满暴|配速)", body, re.S)
                or re.search(r"(御魂|配置|配装|阵容|阵容码|面板|满暴|配速).{0,60}" + re.escape(a), body, re.S)
                for a in aliases
            )
            if title_hit:
                score += 4
            if cnt:
                score += min(cnt, 6) * 0.5
            if aliases and not (title_hit or cnt >= 2 or near):
                score -= 3
            score += min(build_hits, 4) * 0.6
            age_days = (now_ms - g.time) / 86400000 if g.time else 9999
            if age_days <= 180:
                score += 2
            elif age_days <= 365:
                score += 0.8
            if "攻略" in body or "推荐" in body:
                score += 0.5
            if len(g.long_text) > 500 or len(g.text) > 120:
                score += 0.5
            if age_days > max_days:
                score -= 2
            if getattr(g, "codes", None):
                score += 2.5
            g.score = score
            g.age_days = age_days
            g.build_hits = build_hits
            g.title_hit = title_hit
            g.is_index = bool(re.search("导航|合集|目录", g.title))
            if g.is_index and not title_hit:
                score -= 0.8
                g.score = score
            results.append(g)
        # 有阵容码的优先，其次按得分/新鲜度
        results.sort(key=lambda x: (0 if getattr(x, "codes", None) else 1, -x.score, x.age_days))
        results = [r for r in results
                   if r.score >= 2.0 and (getattr(r, "build_hits", 0) >= 1 or "阵容" in r.title)][:limit]
        self.cache[key] = (now, results)
        return results

    def recent_matches_any(self, aliases):
        out = []
        for g in self._load_recent():
            body = g.title + " " + g.text + " " + (g.long_text or "")[:800]
            if any(a and a in body for a in aliases):
                out.append(g)
        return out

    # ---------- 图片 ----------
    async def download_images(self, guides, limit=2, max_bytes=6 * 1024 * 1024):
        out = []
        if not guides or limit <= 0:
            return out
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for g in guides:
                    for u in g.images:
                        if len(out) >= limit:
                            break
                        try:
                            data = await self._get(session, u, timeout=15, binary=True)
                            if not data or len(data) > max_bytes or len(data) < 1000:
                                continue
                            ext = ".jpg"
                            if u.lower().endswith(".png") or data[:8] == b"\x89PNG\r\n\x1a\n":
                                ext = ".png"
                            name = "guide_%s_%d%s" % (g.id[:8], len(out), ext)
                            path = os.path.join(self.img_dir, name)
                            with open(path, "wb") as f:
                                f.write(data)
                            out.append(path)
                        except Exception:
                            continue
                        if len(out) >= limit:
                            break
        except Exception:
            return out
        return out


# ---------- 扫码登录（游客被拒时用） ----------
QR_ID = "https://q.reg.163.com/qrcode/getqrcodeid/?product=godlike_web&callback=cb"
QR_IMG = ("https://q.reg.163.com/qrcode/getGeneralUrlQrcode?uuid=%s&size=220"
          "&url=https://ds.163.com&url2=https://ds.163.com&product=godlike_web")
QR_STATUS = "https://q.reg.163.com/qrcode/qrcodeauthstatus?product=godlike_web&uuid=%s&callback=cb"


def _jsonp(text):
    if not text:
        return {}
    m = re.search(r"\((.*)\)\s*$", text.strip(), re.S)
    raw = m.group(1) if m else text
    try:
        return json.loads(raw)
    except Exception:
        return {}


async def qr_login_start(session):
    """返回 (uuid, 二维码图片字节)。"""
    async with session.get(QR_ID, headers={"User-Agent": UA, "Referer": "https://ds.163.com/"}) as r:
        data = _jsonp(await r.text())
    try:
        content = json.loads(data.get("content") or "{}")
        uuid = (content.get("l") or {}).get("i") or ""
    except Exception:
        uuid = ""
    if not uuid:
        return "", None
    async with session.get(QR_IMG % uuid, headers={"User-Agent": UA, "Referer": "https://ds.163.com/"}) as r:
        img = await r.read()
    return uuid, img


async def qr_login_poll(session, uuid, timeout=180, on_status=None):
    """轮询扫码状态。

    返回 (state, cookies)：
      state = ok / expired / nocookie / timeout
    """
    import aiohttp

    jar = session.cookie_jar
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        raw = ""
        set_cookies = []
        try:
            async with session.get(QR_STATUS % uuid,
                                   headers={"User-Agent": UA, "Referer": "https://ds.163.com/"},
                                   timeout=aiohttp.ClientTimeout(total=12)) as r:
                raw = await r.text()
                data = _jsonp(raw)
                try:
                    set_cookies = r.headers.getall("Set-Cookie", [])
                except Exception:
                    set_cookies = []
        except Exception:
            data = {}
        code = str(data.get("retCode") or "")
        if on_status:
            try:
                on_status(code, raw[:400])
            except Exception:
                pass
        if code == "200" or (code and code not in ("403", "408", "400", "401", "402", "404", "410") and set_cookies):
            # 收集 cookie（状态接口本身可能就下发登录态）
            cookies = _jar_cookies(jar)
            if set_cookies and not cookies:
                merged = {}
                for sc in set_cookies:
                    k, _, rest = sc.partition("=")
                    v = rest.split(";", 1)[0]
                    if k and v:
                        merged[k.strip()] = v.strip()
                cookies = "; ".join("%s=%s" % (k, v) for k, v in merged.items())
            if not cookies:
                urls = set(re.findall(r"""https?://[^"'<>\s]+""", raw))
                try:
                    content = json.loads(data.get("content") or "{}")

                    def walk(o):
                        if isinstance(o, str) and o.startswith("http"):
                            urls.add(o)
                        elif isinstance(o, dict):
                            for v in o.values():
                                walk(v)
                        elif isinstance(o, list):
                            for v in o:
                                walk(v)

                    walk(content)
                except Exception:
                    pass
                for u in list(urls)[:4]:
                    try:
                        async with session.get(u, headers={"User-Agent": UA},
                                               timeout=aiohttp.ClientTimeout(total=15)) as r:
                            await r.read()
                    except Exception:
                        pass
                try:
                    async with session.get("https://ds.163.com/", headers={"User-Agent": UA},
                                           timeout=aiohttp.ClientTimeout(total=15)) as r:
                        await r.read()
                except Exception:
                    pass
                cookies = _jar_cookies(jar)
            if cookies:
                return "ok", cookies
            return "nocookie", raw
        if code in ("400", "401", "402", "404", "410"):
            return "expired", code
        last = code
        await asyncio.sleep(2)
    return "timeout", last


def _jar_cookies(jar):
    out = {}
    try:
        for c in jar:
            if c["domain"].endswith("163.com") or c["domain"].endswith("netease.com"):
                out[c.key] = c.value
    except Exception:
        pass
    return "; ".join("%s=%s" % (k, v) for k, v in out.items())
