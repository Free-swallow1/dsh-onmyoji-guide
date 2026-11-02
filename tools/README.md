# tools

数据抓取 / 构建 / 本地测试脚本。

## 环境

- Python 3.10+
- Node.js 18+（仅 `scrape_wiki.js` 需要）
- 本机安装 Edge 或 Chrome（`scrape_wiki.js` 用来过灰机 wiki 的 Cloudflare 校验）

```bash
cd tools
npm i playwright-core
```

## 步骤

```bash
# 1. 抓灰机 wiki 的 Data 页到 tools/raw/
node tools/scrape_wiki.js

# 2. 生成知识库 JSON（data/characters.json、souls.json、onmyoji.json）
python tools/build_data.py

# 3. 主角技能补充（可选，data/onmyoji.json 已包含）
python tools/merge_onmyoji.py

# 4. 图片（可选，仅本地识别索引需要）
python tools/download_images.py     # 下载 S_/Skin_/御魂图到 tools/img/
python tools/build_index.py         # 生成 data/image_index.json

# 5. 生成式神/御魂/阴阳师图卡（可选，输出 data/cards/）
python tools/build_cards.py --img-dir tools/img

# 6. 大神最新动态（可选，输出 tools/ds_cache.json）
python tools/fetch_ds.py 6

# 7. 本地冒烟测试（stub 掉 astrbot）
python tools/test_local.py
```

## 说明

- `tools/raw/`、`tools/img/` 是中间产物，已在 `.gitignore` 中忽略。
- `download_images.py` 依赖 `curl`（Windows 10+ 自带）；没有 curl 会跳过。
- 图片索引 `data/image_index.json` 已随仓库提供，重新构建是可选的。
