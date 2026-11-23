/**
 * 小深桌宠控制 —— 在 DSH 里用 /pet 打开、关闭桌面上的小深。
 *
 * 桌宠是一个独立的 Python/Tk 进程：这里用 detached 方式启动它，
 * 所以 DeepSeek Harness 关掉之后，小深仍然留在桌面上。
 */
import { execFileSync, spawn } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const inject = ['commands']

// 桌宠程序随插件一起分发，就在插件目录的 pet/ 里；也可以用配置项 dir 指到别处
const DEFAULT_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'pet')

function petDir(config) {
  return (config && typeof config.dir === 'string' && config.dir) || DEFAULT_DIR
}

function petScript(dir) {
  return path.join(dir, 'pet.py')
}

function hasTk(candidate) {
  try {
    execFileSync(candidate, [
      '-c',
      'import tkinter, sys; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)',
    ], { stdio: 'ignore', timeout: 8000 })
    return true
  } catch {
    return false
  }
}

function pickPython() {
  const candidates = [
    process.env.DSH_PET_PYTHON,
    '/opt/miniconda3/bin/python3',
    '/opt/homebrew/bin/python3',
    '/usr/local/bin/python3',
    '/usr/bin/python3',
  ].filter(Boolean)
  for (const candidate of candidates) {
    if (existsSync(candidate) && hasTk(candidate)) return candidate
  }
  return null
}

function running(dir) {
  try {
    execFileSync('pgrep', ['-f', petScript(dir)], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

// Harness 的插件宿主是 Electron 以 node 身份跑的，它的环境里带着 node 的 IPC 通道标记
// （NODE_CHANNEL_FD 等）。桌宠是要脱离 Harness 独立活着的进程，不该继承这些。
const HOST_ONLY_ENV = [
  'NODE_CHANNEL_FD',
  'NODE_CHANNEL_SERIALIZATION_MODE',
  'ELECTRON_RUN_AS_NODE',
  'NODE_OPTIONS',
]

function petEnv() {
  const env = { ...process.env }
  for (const key of HOST_ONLY_ENV) delete env[key]
  return env
}

function openPet(dir) {
  if (running(dir)) return { kind: 'success', text: '小深已经在桌面上了～' }
  if (!existsSync(petScript(dir))) {
    return { kind: 'error', text: `找不到桌宠程序：${petScript(dir)}` }
  }
  const python = pickPython()
  if (!python) {
    return { kind: 'error', text: '没有找到带 Tk 8.6 的 python3，小深起不来。' }
  }
  // detached：自成一个进程组/会话，Harness 退出时不会被一起带走；
  // 必须用绝对路径启动，closePet/running 才能用 pgrep/pkill 按路径找到它。
  const child = spawn(python, [petScript(dir)], {
    cwd: dir,
    detached: true,
    stdio: 'ignore',
    env: petEnv(),
  })
  child.unref()
  return { kind: 'success', text: '小深出来啦！它就在屏幕右下角，点一下就能聊天。' }
}

function closePet(dir) {
  if (!running(dir)) return { kind: 'success', text: '小深已经休息了。' }
  try {
    // SIGTERM：桌宠会先停掉正在跑的 dsh、保存状态，再退出
    execFileSync('pkill', ['-TERM', '-f', petScript(dir)], { stdio: 'ignore' })
  } catch {
    // 进程刚自己退出时 pkill 会返回非 0，不算失败
  }
  return { kind: 'success', text: '小深回窝里睡觉了，下次喊它就好。' }
}

export function apply(ctx, config) {
  const dir = petDir(config)

  const register = () => ctx.commands.register({
    name: 'pet',
    description: '打开 / 关闭桌面上的小深桌宠',
    input: { hint: '[open|close|status]' },
    handler: ({ rawInput }) => {
      const action = (rawInput || '').trim().toLowerCase() || 'toggle'
      if (action === 'open' || action === 'start' || action === '打开') return openPet(dir)
      if (action === 'close' || action === 'stop' || action === 'quit' || action === '关闭') {
        return closePet(dir)
      }
      if (action === 'status' || action === '状态') {
        return {
          kind: 'success',
          text: running(dir) ? '小深在桌面上陪着你。' : '小深现在不在。',
        }
      }
      if (action === 'toggle') return running(dir) ? closePet(dir) : openPet(dir)
      return { kind: 'error', text: `看不懂「${action}」，可以试 /pet open、/pet close、/pet status。` }
    },
  })

  if (typeof ctx.effect === 'function') ctx.effect(register)
  else register()

  // 左侧栏「桌面助手」页面（client.js）用的接口：POST /pet-control/api/{status|open|close}。
  // webServer / connection 不是每种部署都有，所以按需注入，没有就只剩 /pet 命令。
  if (typeof ctx.inject === 'function') {
    ctx.inject(['webServer', 'connection'], (sub) => {
      sub.effect(() => sub.webServer.register({
        kind: 'prefix',
        path: API_PREFIX,
        handler: (req, res) => handleApi(sub, dir, req, res),
      }), 'dsh-pet-control: /pet-control/api')
    })
  }
}

const API_PREFIX = '/pet-control/api'

// ---------------------------------------------------------------- skins
// 和 pet.py 里的约定一致：内置皮肤在 <dir>/skins/，用户皮肤在 ~/.dsh-pet/skins/（同名用户优先），
// 当前选择写在 ~/.dsh-pet/skin.json。小深每秒看一次这个文件，变了就自己换装。
const DEFAULT_SKIN = 'classic'
const SKIN_ID = /^[A-Za-z0-9_\-一-鿿]{1,64}$/

function appHome() {
  return process.env.DSH_PET_HOME || path.join(os.homedir(), '.dsh-pet')
}

function userSkinsDir() {
  return path.join(appHome(), 'skins')
}

function skinFiles(dir) {
  const found = new Map()
  for (const [folder, builtin] of [[path.join(dir, 'skins'), true], [userSkinsDir(), false]]) {
    let names = []
    try { names = readdirSync(folder) } catch { continue }
    for (const name of names.sort()) {
      if (!name.endsWith('.json')) continue
      const id = name.slice(0, -5)
      if (SKIN_ID.test(id)) found.set(id, { file: path.join(folder, name), builtin })
    }
  }
  return found
}

function readChoice() {
  try {
    const d = JSON.parse(readFileSync(path.join(appHome(), 'skin.json'), 'utf8'))
    return d && typeof d === 'object' && !Array.isArray(d) ? d : {}
  } catch {
    return {}
  }
}

// skin.json 里同时记着配色和伙伴：改一个时保留另一个
function writeChoice(patch) {
  mkdirSync(appHome(), { recursive: true })
  writeFileSync(path.join(appHome(), 'skin.json'), JSON.stringify({ ...readChoice(), ...patch }) + '\n')
}

function currentSkin() {
  const id = readChoice().skin
  return typeof id === 'string' && id ? id : DEFAULT_SKIN
}

// ---------------------------------------------------------------- companions
// 伙伴 = 一张 PNG 像素图（可选同名 .json：name / author / description）。
// 内置 <dir>/companions/，用户 ~/.dsh-pet/companions/。页面用 data: URL 显示，图不大（限 512KB）。
const NO_COMPANION = 'none'
const SPRITE_BYTES = 512 * 1024

function userCompanionsDir() {
  return path.join(appHome(), 'companions')
}

function companionFiles(dir) {
  const found = new Map()
  for (const [folder, builtin] of [[path.join(dir, 'companions'), true], [userCompanionsDir(), false]]) {
    let names = []
    try { names = readdirSync(folder) } catch { continue }
    for (const name of names.sort()) {
      if (!name.toLowerCase().endsWith('.png')) continue
      const id = name.slice(0, -4)
      if (SKIN_ID.test(id) && id !== NO_COMPANION) found.set(id, { file: path.join(folder, name), builtin })
    }
  }
  return found
}

function listCompanions(dir) {
  const list = []
  for (const [id, { file, builtin }] of companionFiles(dir)) {
    let meta = {}
    try { meta = JSON.parse(readFileSync(file.slice(0, -4) + '.json', 'utf8')) || {} } catch {}
    const str = (v) => (typeof v === 'string' ? v.slice(0, 200) : '')
    let image = ''
    try {
      const buf = readFileSync(file)
      if (buf.length <= SPRITE_BYTES) image = 'data:image/png;base64,' + buf.toString('base64')
    } catch {}
    const order = typeof meta.order === 'number' ? meta.order : 999
    list.push({ id, builtin, order, name: str(meta.name) || id, author: str(meta.author), description: str(meta.description), image })
  }
  // 内置在前，再按 .json 里可选的 order 排（没写就排后面），最后按 id
  list.sort((a, b) => Number(b.builtin) - Number(a.builtin) || a.order - b.order || a.id.localeCompare(b.id))
  const cur = readChoice().companion
  const companion = typeof cur === 'string' && list.some((c) => c.id === cur) ? cur : NO_COMPANION
  return { companion, companions: list, companionsDir: userCompanionsDir() }
}

function chooseCompanion(dir, id) {
  if (id !== NO_COMPANION && (typeof id !== 'string' || !companionFiles(dir).has(id))) {
    return { kind: 'error', text: `没有叫「${id}」的伙伴。` }
  }
  writeChoice({ companion: id })
  const who = id === NO_COMPANION ? '只留胶囊' : '换好伙伴了'
  return { kind: 'success', text: running(dir) ? `${who}，看看桌面上的小深～` : `选好了，下次打开小深就是这样。` }
}

function listSkins(dir) {
  const skins = []
  for (const [id, { file, builtin }] of skinFiles(dir)) {
    let data
    try { data = JSON.parse(readFileSync(file, 'utf8')) } catch { data = null }
    if (!data || typeof data !== 'object') {
      skins.push({ id, name: id, builtin, broken: true })
      continue
    }
    const str = (v) => (typeof v === 'string' ? v.slice(0, 200) : '')
    skins.push({
      id,
      builtin,
      name: str(data.name) || id,
      author: str(data.author),
      description: str(data.description),
      colors: data.colors && typeof data.colors === 'object' ? data.colors : {},
      shape: data.shape && typeof data.shape === 'object' ? data.shape : {},
    })
  }
  const order = (s) => (s.id === DEFAULT_SKIN ? 0 : s.builtin ? 1 : 2)
  skins.sort((a, b) => order(a) - order(b))
  const current = currentSkin()
  return { current: skins.some((s) => s.id === current) ? current : DEFAULT_SKIN, skins, userDir: userSkinsDir() }
}

function chooseSkin(dir, id) {
  if (typeof id !== 'string' || !skinFiles(dir).has(id)) {
    return { kind: 'error', text: `没有叫「${id}」的皮肤。` }
  }
  try {
    const data = JSON.parse(readFileSync(skinFiles(dir).get(id).file, 'utf8'))
    if (!data || typeof data !== 'object') throw new Error('not an object')
  } catch {
    return { kind: 'error', text: `「${id}」这个皮肤文件不是合法的 JSON，先修好它再选。` }
  }
  writeChoice({ skin: id })
  return { kind: 'success', text: running(dir) ? '换好了，看看桌面上的小深～' : '选好了，下次打开小深就是这套皮肤。' }
}

function openCompanionsFolder(dir) {
  const target = userCompanionsDir()
  mkdirSync(target, { recursive: true })
  const guide = path.join(dir, 'companions', 'README.md')
  if (existsSync(guide) && !existsSync(path.join(target, 'README.md'))) copyFileSync(guide, path.join(target, 'README.md'))
  spawn('open', [target], { detached: true, stdio: 'ignore' }).unref()
  return { kind: 'success', text: `已在访达打开 ${target}，把 PNG 像素图放进去就行。` }
}

function openSkinsFolder(dir) {
  const target = userSkinsDir()
  mkdirSync(target, { recursive: true })
  // 第一次打开时放一份格式说明和一个可以照着改的范例
  const guide = path.join(dir, 'skins', 'README.md')
  const example = path.join(dir, 'skins', 'sakura.json')
  if (existsSync(guide) && !existsSync(path.join(target, 'README.md'))) copyFileSync(guide, path.join(target, 'README.md'))
  if (existsSync(example) && !existsSync(path.join(target, 'my-skin.json.example'))) {
    copyFileSync(example, path.join(target, 'my-skin.json.example'))
  }
  spawn('open', [target], { detached: true, stdio: 'ignore' }).unref()
  return { kind: 'success', text: `已在访达打开 ${target}` }
}

function readBody(req, limit = 4096) {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks = []
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > limit) { reject(new Error('body too large')); req.destroy?.(); return }
      chunks.push(chunk)
    })
    req.on('end', () => {
      try { resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}) } catch { resolve({}) }
    })
    req.on('error', reject)
  })
}

function writeJson(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(body))
}

async function handleApi(ctx, dir, req, res) {
  // 和 Harness 自己的界面走同一道门：登录、Host/Origin 校验都交给 connection 服务，
  // 不自己判断（照 dsh-better-sidebar 的写法）。只收 POST，免得被网页用 <img> 之类触发。
  if (ctx.connection.requestRejection(req) !== undefined) {
    writeJson(res, 403, { ok: false, error: 'forbidden' })
    return
  }
  if (req.method !== 'POST') {
    writeJson(res, 405, { ok: false, error: 'method not allowed' })
    return
  }
  const pathname = new URL(req.url ?? '/', 'http://dsh.internal').pathname
  const action = pathname.slice(API_PREFIX.length + 1)
  try {
    let result
    if (action === 'skins') {
      writeJson(res, 200, { ok: true, ...listSkins(dir), ...listCompanions(dir) })
      return
    }
    if (action === 'companion') {
      const body = await readBody(req)
      const r = chooseCompanion(dir, body?.id)
      writeJson(res, r.kind === 'error' ? 400 : 200, { ok: r.kind !== 'error', message: r.text, ...listSkins(dir), ...listCompanions(dir) })
      return
    }
    if (action === 'companions-folder') {
      const r = openCompanionsFolder(dir)
      writeJson(res, 200, { ok: true, message: r.text })
      return
    }
    if (action === 'skin') {
      const body = await readBody(req)
      const r = chooseSkin(dir, body?.id)
      writeJson(res, r.kind === 'error' ? 400 : 200, { ok: r.kind !== 'error', message: r.text, ...listSkins(dir), ...listCompanions(dir) })
      return
    }
    if (action === 'skins-folder') {
      const r = openSkinsFolder(dir)
      writeJson(res, 200, { ok: true, message: r.text })
      return
    }
    if (action === 'status') result = { kind: 'success', text: running(dir) ? '小深在桌面上陪着你。' : '小深现在不在。' }
    else if (action === 'open') result = openPet(dir)
    else if (action === 'close') result = closePet(dir)
    else {
      writeJson(res, 404, { ok: false, error: `unknown action "${action}"` })
      return
    }
    // 刚 pkill 时进程还在退出，pgrep 仍会找到它；open/close 成功就直接报目标状态，页面之后会轮询纠正
    const ok = result.kind !== 'error'
    const now = action === 'status' || !ok ? running(dir) : action === 'open'
    writeJson(res, 200, { ok, running: now, message: result.text })
  } catch (error) {
    writeJson(res, 500, { ok: false, error: String(error?.message ?? error) })
  }
}
