# -*- coding: utf-8 -*-
"""抓取网易大神阴阳师圈子最新动态，缓存为插件可检索的攻略库。"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ds_cache.json")
OUT = os.path.abspath(OUT)
SQUARE = "5bed6281d545682b8bb8a761"
TAG = "5af7dbbbd54568048c609f3b"
API = "https://inf.ds.163.com"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
     "Referer": "https://ds.163.com/"}


def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def feed_ids(page, count=60):
    query = json.dumps({
        "sortType": "time", "inRecommend": 1, "recommendDays": 0,
        "categoryId": "-1", "title": "推荐", "tags": [TAG], "feedTypes": [3],
    }, separators=(",", ":"))
    url = (API + "/v1/web/recommend/square/feed/custom/with-fixed-feedIds"
           "?count=%d&page=%d&squareId=%s&query=%s&feedIdList=" % (count, page, SQUARE, urllib.parse.quote(query)))
    d = http_json(url)
    return (d.get("result") or {}).get("feedIdList") or []


def feed_detail(fid):
    d = http_json(API + "/v1/web/feed/basic/facade?feedId=" + fid)
    return (d.get("result") or {}).get("feed")


def parse(f):
    if not f:
        return None
    try:
        content = json.loads(f.get("content") or "{}")
        body = content.get("body") or {}
    except Exception:
        return None
    text = (body.get("text") or "").strip()
    if len(text) < 10:
        return None
    images, videos = [], []
    for m in body.get("media") or []:
        mt = (m.get("mimeType") or "").lower()
        u = m.get("url") or ""
        if not u:
            continue
        if mt.startswith("image/"):
            images.append(u)
        elif mt.startswith("video/"):
            videos.append(u)
            cov = m.get("cover")
            if cov:
                images.append(cov)
    nick = ""
    try:
        role = json.loads(f.get("appRole") or "{}")
        nick = role.get("nick") or ""
    except Exception:
        pass
    topics = [t.get("topicName") for t in (f.get("topicInfoList") or []) if t.get("topicName")]
    rec = f.get("record") or {}
    return {
        "id": f.get("id"),
        "time": int(f.get("createTime") or 0),
        "nick": nick,
        "text": text,
        "images": images,
        "videos": videos,
        "topics": topics,
        "likes": rec.get("likeCount") or 0,
        "comments": rec.get("commentCount") or 0,
    }


def main():
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    old = {}
    if os.path.exists(OUT):
        try:
            for p in json.load(open(OUT, encoding="utf-8")):
                old[p["id"]] = p
        except Exception:
            old = {}
    ids = []
    seen = set()
    for pg in range(pages):
        try:
            got = feed_ids(pg)
        except Exception as e:
            print("list page %d error: %s" % (pg, e))
            continue
        for fid in got:
            if fid not in seen:
                seen.add(fid)
                ids.append(fid)
        time.sleep(0.3)
    print("ids", len(ids), "cached", len(old))

    todo = [i for i in ids if i not in old]
    print("to fetch", len(todo))

    def work(fid):
        try:
            return parse(feed_detail(fid))
        except Exception:
            return None

    new = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for p in ex.map(work, todo):
            if p:
                new.append(p)
    allp = list(old.values()) + new
    dedup = {}
    for p in allp:
        dedup[p["id"]] = p
    allp = sorted(dedup.values(), key=lambda x: -x["time"])
    allp = allp[:4000]
    json.dump(allp, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("saved", len(allp), "size", os.path.getsize(OUT) // 1024, "KB")
    guides = [p for p in allp if re.search(r"御魂|配装|阵容|攻略|满暴|面板", p["text"])]
    print("guide-like", len(guides), "with images", sum(1 for p in allp if p["images"]))


if __name__ == "__main__":
    main()
