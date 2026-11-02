/**
 * 抓取阴阳师灰机 wiki 的 Data 数据页到 tools/raw/
 *
 * 依赖：Node.js + playwright-core + 本机 Edge/Chrome
 *   npm i playwright-core
 *   node tools/scrape_wiki.js
 *
 * 可用环境变量：
 *   EDGE_PATH 浏览器可执行文件路径（默认 Windows Edge）
 *   RAW_DIR   输出目录（默认 tools/raw）
 *   HEADLESS  1/0（默认 1）
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const OUT = process.env.RAW_DIR || path.join(__dirname, 'raw');
const EDGE = process.env.EDGE_PATH
  || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const HEADLESS = process.env.HEADLESS !== '0';

const WANT = [
  'CharacterIndex.json', 'Attribute.json', 'Skin.json', 'Soul.json',
  'SkillBuffs.json', 'SkillTips.json', 'SkillAI.json', 'Gift.json',
  'Character.schema',
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: EDGE,
    headless: HEADLESS,
    args: ['--disable-blink-features=AutomationControlled'],
  });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      + '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'zh-CN',
  });
  const page = await ctx.newPage();
  await page.goto('https://yys.huijiwiki.com/wiki/%E9%A6%96%E9%A1%B5', {
    waitUntil: 'domcontentloaded', timeout: 90000,
  });
  await sleep(5000);
  console.log('landed:', await page.title());

  const get = async (url) => page.evaluate(async (u) => {
    const r = await fetch(u, { credentials: 'include' });
    return { status: r.status, text: await r.text() };
  }, url);

  // 列出 Data 命名空间所有页面
  let titles = [];
  let cont = '';
  for (let i = 0; i < 10; i++) {
    const u = 'https://yys.huijiwiki.com/api.php?action=query&list=allpages'
      + '&apnamespace=3500&aplimit=500&format=json&formatversion=2' + cont;
    const r = await get(u);
    const j = JSON.parse(r.text);
    titles = titles.concat(j.query.allpages.map((p) => p.title));
    if (j.continue && j.continue.apcontinue) {
      cont = '&apcontinue=' + encodeURIComponent(j.continue.apcontinue);
    } else break;
  }
  console.log('Data pages:', titles.length);

  const want = (t) => {
    const n = t.slice(5);
    if (/^Character\/\d+\.json$/.test(n)) return true;
    return WANT.includes(n);
  };
  const list = titles.filter(want);
  console.log('to download:', list.length);

  let ok = 0;
  for (const t of list) {
    const name = t.replace(/^Data:/, '').replace(/\//g, '__');
    const dest = path.join(OUT, name);
    if (fs.existsSync(dest) && fs.statSync(dest).size > 10) { ok++; continue; }
    try {
      const r = await get('https://yys.huijiwiki.com/index.php?title='
        + encodeURIComponent(t) + '&action=raw');
      if (r.status !== 200 || r.text.length < 5) throw new Error('status ' + r.status);
      fs.writeFileSync(dest, r.text);
      ok++;
    } catch (e) {
      console.warn('failed:', t, e.message);
    }
  }
  console.log('done:', ok, 'files ->', OUT);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
