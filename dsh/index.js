/**
 * 阴阳师助手 — DeepSeek Harness 插件
 *
 * 提供 5 个工具：yys_lookup / yys_skills / yys_calc / yys_guide / yys_card
 * 数据来自仓库根目录 data/（可通过 YYS_DATA_DIR 覆盖）。
 *
 * @module dsh-plugin-yys
 */
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const name = 'onmyoji-guide'
export const inject = ['tools']

const HERE = fileURLToPath(new URL('.', import.meta.url))
const DATA_DIR = process.env.YYS_DATA_DIR
  ? process.env.YYS_DATA_DIR.replace(/[\\/]+$/, '')
  : fileURLToPath(new URL('../data/', import.meta.url)).replace(/[\\/]+$/, '')

const MOBILE_UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
  + '(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36'

let cache = null

function loadData() {
  if (cache) return cache
  const read = (name) => JSON.parse(readFileSync(`${DATA_DIR}/${name}`, 'utf8'))
  const chars = read('characters.json')
  const souls = read('souls.json')
  const onmyoji = read('onmyoji.json')
  const recommend = read('recommend.json')
  const index = []
  for (const c of chars) {
    for (const a of c.aliases || []) index.push([a, c])
  }
  cache = { chars, souls, onmyoji, recommend, index }
  return cache
}

const norm = (s) => String(s || '').toLowerCase()
  .replace(/[\s,，。.!！?？:：;；"'“”‘’()（）\[\]【】<>《》~～、|/\\]+/g, '')

const pct = (v) => (v === null || v === undefined ? '-' : `${Math.round(v * 1000) / 10}%`)

function findChar(text) {
  const { chars, index } = loadData()
  const n = norm(text)
  if (!n) return null
  for (const [a, c] of index) {
    if (norm(a) === n) return c
  }
  let best = null
  let bestLen = 0
  for (const [a, c] of index) {
    const na = norm(a)
    if (na.length >= 2 && n.includes(na) && na.length > bestLen) {
      best = c
      bestLen = na.length
    }
  }
  if (best) return best
  for (const c of chars) {
    if (norm(c.name) === n) return c
  }
  return null
}

function findSoul(text) {
  const { souls } = loadData()
  const n = norm(text)
  if (!n) return null
  for (const s of souls) if (norm(s.name) === n) return s
  for (const s of souls) if (n.includes(norm(s.name))) return s
  return null
}

function findOnmyoji(text) {
  const { onmyoji } = loadData()
  for (const o of onmyoji) if (text.includes(o.name)) return o
  return null
}

function charText(c) {
  const st = c.stats || {}
  const lines = []
  lines.push(`【${c.rarity || ''} ${c.name}】攻击${st.atk ?? '?'}｜生命${st.hp ?? '?'}｜防御${st.def ?? '?'}｜速度${st.spd ?? '?'}｜暴击${pct(st.cri)}｜暴伤${pct(st.crid)}`)
  lines.push(`定位：${(c.tags || []).join('/') || '综合'}`)
  const skills = (c.skills || []).map((s) => {
    const cost = s.cost === -1 || s.type === '被动' ? '被动' : `${s.cost || 0}火`
    return `${s.name}（${cost}）`
  })
  if (skills.length) lines.push(`技能：${skills.join('、')}`)
  const rec = loadData().recommend[c.name]
  if (rec) {
    lines.push(`御魂参考：${rec.souls}`)
    lines.push(`246：${rec.pos}｜目标：${rec.target}`)
    if (rec.note) lines.push(`说明：${rec.note}`)
  } else {
    lines.push('御魂参考：输出优先满暴，再比较攻击×暴伤；控制堆命中，辅助堆速度/生存。')
  }
  return lines.join('\n')
}

function skillsText(c) {
  const lines = [`【${c.name} 技能】`]
  for (const [i, s] of (c.skills || []).entries()) {
    const cost = s.cost === -1 || s.type === '被动' ? '被动' : `${s.cost || 0}鬼火`
    lines.push(`${i + 1}. ${s.name}（${cost}）`)
    if (s.desc) lines.push(s.desc.replace(/\n/g, ' '))
    for (const u of s.upgrades || []) lines.push(`Lv.${u.level} ${u.effect}`)
    for (const b of s.buffs || []) lines.push(`〔${b.name}〕${b.buffDesc || ''}`)
    for (const t of s.tips || []) lines.push(`〔${t.skill_tips_name}〕${t.skill_tips_text || ''}`)
  }
  return lines.join('\n')
}

function soulText(s) {
  return `【${s.name}】（${s.type || '御魂'}）\n2件套：${s.suit}\n4件套：${s.desc}\n获取：${(s.way || '').split('\n')[0]}`
}

function onmyojiText(o) {
  const lines = [`【${o.name}（${o.grade || '阴阳师'}）】`]
  for (const s of o.skills || []) lines.push(`· ${s.name}：${s.desc}`)
  if (o.advice) lines.push(`建议：${o.advice}`)
  return lines.join('\n')
}

function calcText(args) {
  const atk = Number(args.atk) || 0
  let crit = Number(args.crit) || 0
  const critdmg = Number(args.critdmg) || 150
  crit = Math.max(0, Math.min(100, crit))
  const full = 1 + critdmg / 100
  const expected = (crit / 100) * full + (1 - crit / 100)
  const lines = []
  lines.push(`面板：攻击 ${atk || '?'}｜暴击 ${crit}%｜暴伤 ${critdmg}%`)
  if (crit >= 100) lines.push('✅ 满暴达成（暴击 100%），溢出无收益。')
  else lines.push(`⚠️ 未满暴：还差 ${100 - crit}% 暴击。输出必须满暴，否则每段伤害都在赌。`)
  lines.push(`满暴系数（攻击×暴伤）：×${full.toFixed(3)}`)
  lines.push(`当前期望系数：×${expected.toFixed(3)}（暴击率 ${crit}%）`)
  if (crit < 100) lines.push(`补满暴后期望提升：+${(((full - expected) / expected) * 100).toFixed(1)}%`)
  if (atk) lines.push(`${crit >= 100 ? '满暴后 ' : ''}攻击×暴伤 = ${atk} × ${full.toFixed(2)} = ${Math.round(atk * full)}`)
  return lines.join('\n')
}

const CODE_RE = /\|\s*TA[C]?\s*\|\s*[0-9a-fA-F]{16,64}/g

function extractCodes(text) {
  const out = []
  for (const m of String(text || '').match(CODE_RE) || []) {
    const code = m.replace(/\s+/g, '')
    if (!out.includes(code)) out.push(code)
  }
  return out
}

function stripHtml(html) {
  return String(html || '')
    .replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/[ \t\u00a0]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

async function fetchText(url, timeoutMs = 15000) {
  const res = await fetch(url, {
    headers: { 'User-Agent': MOBILE_UA, Referer: 'https://ds.163.com/' },
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.text()
}

async function fetchJson(url, timeoutMs = 15000) {
  const res = await fetch(url, {
    headers: { 'User-Agent': MOBILE_UA, Referer: 'https://ds.163.com/' },
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function guideText(subject) {
  const q = encodeURIComponent(`site:ds.163.com ${subject} 阵容 配置`)
  let html = ''
  try {
    html = await fetchText(`https://m.so.com/s?q=${q}`)
  } catch {
    html = ''
  }
  const ids = [...new Set((html.match(/ds\.163\.com\/(?:feed|article)\/([0-9a-f]{20,32})/g) || [])
    .map((u) => u.split('/').pop()))]
  if (!ids.length) return `没搜到「${subject}」的最新攻略（搜索源暂时不可用）。`
  const guides = []
  for (const id of ids.slice(0, 10)) {
    try {
      const j = await fetchJson(`https://inf.ds.163.com/v1/web/feed/basic/facade?feedId=${id}`)
      const feed = j?.result?.feed
      if (!feed) continue
      const content = JSON.parse(feed.content || '{}')
      const body = content.body || {}
      const text = body.text || ''
      const longText = stripHtml(body.longText || '')
      const codes = extractCodes(`${text}\n${longText}`)
      const title = body.title || text.split('\n')[0] || ''
      guides.push({ id, text, longText, title, codes, time: Number(feed.createTime) || 0 })
    } catch {
      /* skip */
    }
  }
  if (!guides.length) return `没搜到「${subject}」的最新攻略。`
  const now = Date.now()
  for (const g of guides) {
    let score = 0
    const body = `${g.title} ${g.text} ${g.longText.slice(0, 1500)}`
    if (g.title.includes(subject)) score += 3
    if (body.includes(subject)) score += 1.5
    for (const kw of ['御魂', '配置', '配装', '阵容', '阵容码', '满暴', '面板', '配速']) {
      if (body.includes(kw)) score += 0.5
    }
    if (g.codes.length) score += 2.5
    const days = g.time ? (now - g.time) / 86400000 : 9999
    if (days <= 180) score += 2
    else if (days <= 365) score += 0.8
    g.score = score
    g.days = days
  }
  guides.sort((a, b) => (b.codes.length ? 1 : 0) - (a.codes.length ? 1 : 0) || b.score - a.score || a.days - b.days)
  const g = guides[0]
  const date = g.time ? new Date(g.time).toISOString().slice(0, 10) : '未知'
  const body = (g.longText || g.text || '').replace(/#[^#]{1,20}#/g, '').replace(/\s+/g, ' ').trim()
  const lines = [
    `【大神攻略】${g.title}`,
    `日期：${date}${g.codes.length ? `｜阵容码：${g.codes.slice(0, 3).join('；')}` : ''}`,
    body.slice(0, 900),
    `原文：https://ds.163.com/feed/${g.id}/`,
  ]
  if (g.days > 365) lines.unshift(`（注意：这条攻略是 ${date} 的，可能已过时）`)
  return lines.join('\n')
}

export function apply(ctx) {
  ctx.tools.register({
    name: 'yys_lookup',
    description: '查询《阴阳师》式神/御魂/阴阳师（主角）资料：面板、技能列表、御魂推荐。输入式神名、御魂名或主角名。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        query: { type: 'string', description: '名字，如 天照 / 破势 / 晴明' },
      },
      required: ['query'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          text: { type: 'string', description: '格式化后的资料' },
          card: { type: 'string', description: '图卡本地路径（可选）' },
        },
        required: ['text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.card ? `${value.text}
图卡：${value.card}` : value.text }],
    },
    async execute(args) {
      const q = String(args.query || '')
      const c = findChar(q)
      if (c) {
        const card = `${DATA_DIR}/cards/char_${c.id}.png`
        return { text: charText(c), ...(existsSync(card) ? { card } : {}) }
      }
      const s = findSoul(q)
      if (s) {
        const card = `${DATA_DIR}/cards/soul_${s.id}.png`
        return { text: soulText(s), ...(existsSync(card) ? { card } : {}) }
      }
      const o = findOnmyoji(q)
      if (o) {
        const card = `${DATA_DIR}/cards/onmyoji_${o.id}.png`
        return { text: onmyojiText(o), ...(existsSync(card) ? { card } : {}) }
      }
      return { text: `没找到「${q}」。可以试试式神名（天照）、御魂名（破势）或主角（晴明）。` }
    },
  })

  ctx.tools.register({
    name: 'yys_skills',
    description: '查询《阴阳师》某个式神的完整技能描述（含升级效果与 buff/印记词条）。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        name: { type: 'string', description: '式神名，如 天照' },
      },
      required: ['name'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: { text: { type: 'string', description: '技能全文' } },
        required: ['text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    },
    async execute(args) {
      const c = findChar(String(args.name || ''))
      if (!c) return { text: `没找到式神「${args.name}」。` }
      return { text: skillsText(c) }
    },
  })

  ctx.tools.register({
    name: 'yys_calc',
    description: '阴阳师面板计算：满暴判定、期望系数、攻击×暴伤。用于配装/面板收益问题。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        atk: { type: 'number', description: '面板攻击' },
        crit: { type: 'number', description: '面板暴击（百分数，如 95）' },
        critdmg: { type: 'number', description: '面板暴击伤害（百分数，如 260）' },
      },
      required: ['atk', 'crit', 'critdmg'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: { text: { type: 'string', description: '计算结果' } },
        required: ['text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    },
    async execute(args) {
      return { text: calcText(args) }
    },
  })

  ctx.tools.register({
    name: 'yys_guide',
    description: '检索网易大神上《阴阳师》最新阵容/配置攻略（优先带阵容码），返回标题、日期、阵容码、摘要和原文链接。主题可以是式神或玩法，如 魂土配置 / 真蛇 / 斗技阵容 / 天照。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        subject: { type: 'string', description: '查询主题，如 魂土配置、真蛇、斗技、天照' },
      },
      required: ['subject'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: { text: { type: 'string', description: '攻略摘要' } },
        required: ['text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    },
    async execute(args) {
      const subject = String(args.subject || '').trim()
      if (!subject) return { text: '请提供式神或玩法名称。' }
      try {
        return { text: await guideText(subject) }
      } catch (error) {
        return { text: `攻略检索失败：${error instanceof Error ? error.message : String(error)}` }
      }
    },
  })

  ctx.tools.register({
    name: 'yys_card',
    description: '获取《阴阳师》式神/御魂/阴阳师的介绍图卡路径（PNG），可用于展示图片。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        name: { type: 'string', description: '式神/御魂/主角名字' },
      },
      required: ['name'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          path: { type: 'string', description: '图卡绝对路径' },
          text: { type: 'string', description: '说明' },
        },
        required: ['path', 'text'],
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    },
    async execute(args) {
      const q = String(args.name || '')
      const c = findChar(q)
      if (c) {
        const p = `${DATA_DIR}/cards/char_${c.id}.png`
        return existsSync(p)
          ? { path: p, text: `已找到 ${c.name} 的图卡：${p}` }
          : { path: '', text: `暂无 ${c.name} 的图卡。` }
      }
      const s = findSoul(q)
      if (s) {
        const p = `${DATA_DIR}/cards/soul_${s.id}.png`
        return existsSync(p) ? { path: p, text: `已找到 ${s.name} 的图卡：${p}` } : { path: '', text: `暂无 ${s.name} 的图卡。` }
      }
      const o = findOnmyoji(q)
      if (o) {
        const p = `${DATA_DIR}/cards/onmyoji_${o.id}.png`
        return existsSync(p) ? { path: p, text: `已找到 ${o.name} 的图卡：${p}` } : { path: '', text: `暂无 ${o.name} 的图卡。` }
      }
      return { path: '', text: `没找到「${q}」。` }
    },
  })
}
