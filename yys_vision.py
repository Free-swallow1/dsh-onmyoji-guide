# -*- coding: utf-8 -*-
"""图片识别：OCR 截图文字 + 本地图标匹配 + 视觉大模型兜底。"""
from __future__ import annotations

import base64
import io
import json
import os
import re

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_OCR_ENGINE = None
_OCR_TRIED = False


def _get_ocr():
    """懒加载 RapidOCR；没装就返回 None（插件仍可正常用文本功能）。"""
    global _OCR_ENGINE, _OCR_TRIED
    if _OCR_TRIED:
        return _OCR_ENGINE
    _OCR_TRIED = True
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
    except Exception:
        _OCR_ENGINE = None
    return _OCR_ENGINE


def ocr_text(img_bytes):
    """识别图片中的文字，返回拼接字符串。"""
    engine = _get_ocr()
    if engine is None or Image is None:
        return ""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        # 太小的图放大一点，提升识别率
        if max(img.size) < 700:
            scale = 700 / max(img.size)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        import tempfile

        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img.save(tmp)
        result, _ = engine(tmp)
        try:
            os.remove(tmp)
        except Exception:
            pass
        if not result:
            return ""
        return " ".join(str(item[1]) for item in result if len(item) > 1)
    except Exception:
        return ""


def load_index():
    try:
        with open(os.path.join(DATA_DIR, "image_index.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _to_gray(img):
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img).convert("L")
    else:
        img = img.convert("L")
    return img


def dhash_hex(img, size=16):
    """difference hash，返回 256bit 的十六进制串。"""
    if Image is None or np is None:
        return ""
    g = _to_gray(img).resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    out = []
    for i in range(0, len(bits), 4):
        v = 0
        for b in bits[i:i + 4]:
            v = (v << 1) | int(b)
        out.append("%x" % v)
    return "".join(out)


def _hamming(a, b):
    if not a or not b or len(a) != len(b):
        return 999
    x = int(a, 16) ^ int(b, 16)
    return bin(x).count("1")


def _white(im):
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def _content_crop(im, thr=28):
    """白底内容裁剪：去掉截图/立绘周围的白边。"""
    im = _white(im)
    a = np.asarray(im).astype(np.int16)
    mask = np.abs(a - 255).sum(2) > thr
    ys, xs = np.where(mask)
    if len(xs) < 200:
        return im
    return im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def feat_vector(im, size=16):
    """16x16 归一化颜色特征，用于同画作/同立绘匹配。"""
    im = _content_crop(im).resize((size, size), Image.LANCZOS)
    v = np.asarray(im, dtype=np.float32) / 255.0
    v = (v - v.mean()) / (v.std() + 1e-6)
    return v.ravel()


def feat_b64(im, size=16):
    return base64.b64encode(np.asarray(_content_crop(im).resize((size, size), Image.LANCZOS), dtype=np.uint8).tobytes()).decode()


def feat_from_b64(b64, size=16):
    try:
        a = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
        v = a.reshape(size, size, 3).astype(np.float32) / 255.0
        v = (v - v.mean()) / (v.std() + 1e-6)
        return v.ravel()
    except Exception:
        return None


def _cos(a, b):
    if a is None or b is None:
        return -1.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6))


def local_match(img_bytes, index, min_score=0.80, min_margin=0.12):
    """同画作匹配：返回 (best_item, score, margin)。"""
    if Image is None or np is None or not index:
        return None, -1.0, 0.0
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
    except Exception:
        return None, -1.0, 0.0
    if min(img.size) < 60:
        return None, -1.0, 0.0
    q = feat_vector(img)
    best, best_s, second_s = None, -1.0, -1.0
    for item in index:
        f = feat_from_b64(item.get("feat", ""))
        s = _cos(q, f)
        if s > best_s:
            best, second_s, best_s = item, best_s, s
        elif s > second_s:
            second_s = s
    margin = best_s - second_s
    if best_s >= min_score and margin >= min_margin:
        return best, best_s, margin
    return None, best_s, margin


def shortlist(img_bytes, index, k=8):
    """按视觉相似度给候选，用于让视觉模型做对比。"""
    if Image is None or np is None or not index:
        return []
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
    except Exception:
        return []
    q = feat_vector(img)
    scored = []
    seen = set()
    for item in index:
        if item.get("name") in seen:
            continue
        s = _cos(q, feat_from_b64(item.get("feat", "")))
        scored.append((s, item))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, item in scored:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        out.append(item)
        if len(out) >= k:
            break
    return out


def to_data_uri(img_bytes, max_side=1280):
    if Image is None:
        b64 = base64.b64encode(img_bytes).decode()
        return "data:image/png;base64," + b64
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, img).convert("RGB")
        else:
            img = img.convert("RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return "data:image/png;base64," + base64.b64encode(img_bytes).decode()


VLM_SYSTEM = (
    "你是《阴阳师》手游图鉴识别器。你会看到一张截图，可能是式神立绘/头像/战斗画面、"
    "御魂图标、道具图标。只输出 JSON，不要解释。"
)


async def vlm_identify_async(provider, img_bytes, kb, extra_hint=""):
    """自由识别（不给候选列表，避免模型被长列表带偏）。"""
    if provider is None:
        return None
    prompt = (
        "这是《阴阳师》手游的截图。请先读图中出现的文字（尤其是式神名、御魂名、道具名），"
        "再判断主要对象是什么。如果图中直接写着名字，以文字为准。"
        '输出 JSON：{"type":"式神/御魂/物品/未知","name":"游戏内标准名字","confidence":0到1,"text":"图中读到的文字","reason":"一句话"}。'
        "如果不确定，confidence 给低一点，name 仍然给出最可能的答案。"
    )
    if extra_hint:
        prompt += "\n截图里的文字（OCR）：" + extra_hint[:200]
    uri = to_data_uri(img_bytes)
    try:
        resp = await provider.text_chat(
            prompt=prompt,
            contexts=[],
            system_prompt=VLM_SYSTEM,
            image_urls=[uri],
        )
    except Exception as e:
        return {"error": str(e)[:200]}
    text = getattr(resp, "completion_text", None) or str(resp)
    return parse_vlm_json(text)


def parse_vlm_json(text):
    if not text:
        return None
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def ref_url(filename):
    """huiji CDN 图片直链。"""
    if not filename:
        return ""
    import hashlib
    import urllib.parse

    h = hashlib.md5(filename.encode("utf-8")).hexdigest()
    return "https://huiji-public.huijistatic.com/yys/uploads/%s/%s/%s" % (
        h[0], h[:2], urllib.parse.quote(filename)
    )


async def vlm_confirm(provider, img_bytes, ref, name):
    """用官方立绘二次确认识别结果。返回 True/False/None。"""
    if provider is None or not ref:
        return None
    prompt = (
        "第一张是待识别图，第二张是《阴阳师》式神「%s」的官方立绘。"
        '判断第一张图是不是%s，只输出 JSON：{"match":true或false,"confidence":0到1}' % (name, name)
    )
    try:
        resp = await provider.text_chat(
            prompt=prompt,
            contexts=[],
            image_urls=[to_data_uri(img_bytes), ref],
        )
    except Exception:
        return None
    data = parse_vlm_json(getattr(resp, "completion_text", "") or "")
    if isinstance(data, dict):
        m = data.get("match")
        conf = data.get("confidence")
        if isinstance(m, bool):
            if isinstance(conf, (int, float)) and conf < 0.6:
                return None
            return m
    return None
