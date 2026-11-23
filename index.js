/**
 * 小深桌宠控制 —— 在 DSH 里用 /pet 打开、关闭桌面上的小深。
 *
 * 桌宠是一个独立的 Python/Tk 进程：这里用 detached 方式启动它，
 * 所以 DeepSeek Harness 关掉之后，小深仍然留在桌面上。
 */
import { execFileSync, spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
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

function writeJson(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(body))
}

function handleApi(ctx, dir, req, res) {
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
