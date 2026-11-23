/**
 * dsh-pet-control · 浏览器半边
 *
 * 在 Harness 左侧栏（「插件 / 自动化任务 / 上下文洞察 …」那一列）加一个「桌面助手」入口，
 * 点开是一页：小深在不在、一个打开/关闭按钮。真正的启停在宿主半边（index.js 的
 * POST /pet-control/api/*），这里只是调它。
 *
 * 写法照着 dsh-context / dsh-better-sidebar 的成品：
 * - 包装：window.__ModuleLoader__.load({ id, factory: (require) => exports })
 * - React 由宿主提供：require('react')
 * - 侧栏入口：slots.register({ name: 'sidebar.panellist', id, order, label }, Icon)
 *   页面：    slots.register({ name: 'main', key: id }, Page)   —— id 与 key 相同即配对
 * - 两个 slot 都用 slots.inject 包一层：声明还没上台账时会等它，而不是抛错
 * 没有构建步骤，手写的 ES5+ 浏览器代码，不用 JSX。
 */
window.__ModuleLoader__.load({
  id: 'dsh-pet-control',
  factory: (require) => {
    const React = require('react')
    const h = React.createElement
    const { useCallback, useEffect, useState } = React

    const ID = 'dsh-pet-control'
    const LABEL = '桌面助手'

    // 相对路径 + 页面自己的 base：桌面端页面是 dsh-app://app/，壳会把非静态路径转给宿主；
    // 网页部署可能挂在反向代理的子目录下，开头不能写 '/'（见 better-sidebar 的 host-route-url.ts）
    function apiUrl(action) {
      const base = new URL(document.baseURI)
      base.search = ''
      base.hash = ''
      if (!base.pathname.endsWith('/')) base.pathname = base.pathname.replace(/[^/]*$/, '')
      return new URL('pet-control/api/' + action, base)
    }

    async function call(action, payload) {
      const res = await fetch(apiUrl(action), {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload || {}),
        credentials: 'same-origin',
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || ('HTTP ' + res.status))
      return body
    }

    // 侧栏图标：一枚小胶囊 + 中间的声波（和桌面上的小深长得一样），跟随文字颜色
    function Icon(props) {
      const size = typeof props.size === 'number' ? props.size : 20
      const line = (x, y1, y2) => h('line', { x1: x, y1, x2: x, y2, strokeLinecap: 'round' })
      return h('svg', {
        width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
        stroke: 'currentColor', strokeWidth: 1.6, 'aria-hidden': true,
      },
      h('rect', { x: 2.5, y: 6.5, width: 19, height: 11, rx: 5.5 }),
      line(9, 10.5, 13.5), line(12, 9.5, 14.5), line(15, 10.5, 13.5))
    }

    // ------------------------------------------------------------ 皮肤
    // 缺的颜色用经典白补齐，和 pet.py 的规则一样（坏值也回退）
    const BASE = {
      card: '#FFFFFF', border: '#E4E6EA', ink: '#1F2328', muted: '#8A919E', accent: '#2FC9A8',
      button: '#2B2F36', on_button: '#FFFFFF', stack: '#F7F8FA', chip: '#F1F2F4',
    }
    const HEX = /^#[0-9A-Fa-f]{6}$/
    function palette(skin) {
      const out = { ...BASE }
      for (const k of Object.keys(BASE)) {
        const v = skin.colors && skin.colors[k]
        if (typeof v === 'string' && HEX.test(v)) out[k] = v
      }
      return out
    }
    function radius(v, fallback) {
      return typeof v === 'number' && v >= 0 && v <= 40 ? v : fallback
    }

    // 一张缩略图：右上一枚胶囊（✎ 声波 ⌄），下面一张任务卡片，后面露一截叠放的卡片。按 0.6 缩小
    function SkinPreview(props) {
      const c = palette(props.skin)
      const sh = props.skin.shape || {}
      const k = 0.6
      const barH = 20
      const barR = sh.bar_radius === 'round' || sh.bar_radius === undefined
        ? barH / 2 : Math.min(barH / 2, radius(sh.bar_radius, 99) * k)
      const cardR = Math.min(24, radius(sh.card_radius, 24) * k)
      const line = (x1, y1, x2, y2, color, w) => h('line', {
        x1, y1, x2, y2, stroke: color, strokeWidth: w || 1.3, strokeLinecap: 'round',
      })
      return h('svg', { viewBox: '0 0 160 100', width: '100%', style: { display: 'block' }, 'aria-hidden': true },
        h('rect', { x: 0, y: 0, width: 160, height: 100, fill: 'rgba(127,127,127,0.14)' }),
        // 胶囊
        h('rect', { x: 84, y: 8, width: 68, height: barH, rx: barR, fill: c.card, stroke: c.border }),
        line(96, 22, 101, 14, c.ink),
        line(113, 15.5, 113, 20.5, c.ink), line(116, 13.5, 116, 22.5, c.ink), line(119, 15.5, 119, 20.5, c.ink),
        h('polyline', { points: '134,16 137,19 140,16', fill: 'none', stroke: c.muted, strokeWidth: 1.3, strokeLinecap: 'round', strokeLinejoin: 'round' }),
        // 叠在后面的卡片露出一截
        h('rect', { x: 14, y: 40, width: 132, height: 52, rx: Math.min(cardR, 8), fill: c.stack, stroke: c.border }),
        // 卡片
        h('rect', { x: 8, y: 34, width: 144, height: 54, rx: cardR, fill: c.card, stroke: c.border }),
        h('rect', { x: 20, y: 45, width: 46, height: 6, rx: 3, fill: c.ink }),
        h('rect', { x: 20, y: 57, width: 104, height: 4, rx: 2, fill: c.muted, opacity: 0.75 }),
        h('rect', { x: 20, y: 66, width: 78, height: 4, rx: 2, fill: c.muted, opacity: 0.75 }),
        h('circle', { cx: 136, cy: 47, r: 6, fill: c.button }),
        line(133.6, 44.6, 138.4, 49.4, c.on_button, 1.2), line(133.6, 49.4, 138.4, 44.6, c.on_button, 1.2),
        h('circle', { cx: 136, cy: 74, r: 6, fill: c.accent }),
        line(136, 77, 136, 71, c.on_button, 1.4), line(133.5, 73.3, 136, 70.8, c.on_button, 1.4), line(136, 70.8, 138.5, 73.3, c.on_button, 1.4))
    }

    function SkinSection() {
      const [data, setData] = useState({ skins: [], current: null })
      const [msg, setMsg] = useState('')
      const [busy, setBusy] = useState(null)

      const load = useCallback(() => {
        call('skins').then((b) => setData({ skins: b.skins || [], current: b.current })).catch(() => {})
      }, [])
      useEffect(() => {
        load()
        // 你在文件夹里新放的皮肤，几秒内就会出现在这里
        const timer = setInterval(load, 3000)
        return () => clearInterval(timer)
      }, [load])

      const pick = (id) => {
        if (id === data.current || busy) return
        setBusy(id)
        call('skin', { id })
          .then((b) => { setData({ skins: b.skins || [], current: b.current }); setMsg(b.message || '') })
          .catch((e) => setMsg(e.message))
          .finally(() => setBusy(null))
      }
      const openFolder = () => {
        call('skins-folder').then((b) => setMsg(b.message || '')).catch((e) => setMsg(e.message))
      }

      return h('div', { style: { marginTop: 40 } },
        h('div', { style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 14 } },
          h('h2', { style: { fontSize: 17, fontWeight: 600, margin: 0 } }, '皮肤'),
          h('button', {
            type: 'button', onClick: openFolder,
            style: {
              border: 'none', background: 'none', padding: 0, cursor: 'pointer', fontSize: 13,
              color: 'inherit', opacity: 0.6, textDecoration: 'underline', textUnderlineOffset: 3,
            },
          }, '打开我的皮肤文件夹')),
        h('div', {
          role: 'radiogroup', 'aria-label': '皮肤',
          style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(168px, 1fr))', gap: 14 },
        },
        data.skins.map((skin) => {
          const on = skin.id === data.current
          return h('button', {
            key: skin.id, type: 'button', role: 'radio', 'aria-checked': on,
            disabled: skin.broken, title: skin.broken ? '这个皮肤文件不是合法的 JSON' : skin.description || skin.name,
            onClick: () => pick(skin.id),
            style: {
              textAlign: 'left', padding: 0, overflow: 'hidden', cursor: skin.broken ? 'not-allowed' : 'pointer',
              borderRadius: 14, background: 'transparent', color: 'inherit', font: 'inherit',
              border: on ? '2px solid currentColor' : '1px solid rgba(127,127,127,0.28)',
              margin: on ? 0 : 1, opacity: skin.broken ? 0.45 : busy && busy !== skin.id ? 0.7 : 1,
            },
          },
          skin.broken ? h('div', { style: { height: 105, display: 'grid', placeItems: 'center', fontSize: 12, opacity: 0.6 } }, '文件有误')
            : h(SkinPreview, { skin }),
          h('div', { style: { padding: '9px 12px 11px' } },
            h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, fontSize: 14 } },
              h('span', { style: { fontWeight: on ? 600 : 400 } }, skin.name),
              on ? h('span', { style: { fontSize: 12, opacity: 0.6 } }, '使用中')
                : busy === skin.id ? h('span', { style: { fontSize: 12, opacity: 0.6 } }, '…') : null),
            h('div', { style: { fontSize: 12, opacity: 0.5, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
              skin.builtin ? '内置' : '我的' + (skin.author ? ' · ' + skin.author : ''))))
        })),
        msg ? h('p', { style: { marginTop: 12, opacity: 0.6, fontSize: 13 } }, msg) : null,
        h('p', { style: { marginTop: 14, opacity: 0.5, fontSize: 12, lineHeight: 1.6 } },
          '自己设计的皮肤（JSON 文件）放进「我的皮肤文件夹」就会出现在这里；文件夹里有格式说明。正在使用的皮肤改完保存，桌面上的小深一秒内就会更新。'))
    }

    function Page() {
      const [state, setState] = useState({ running: null, message: '', busy: false, error: '' })

      const refresh = useCallback(() => {
        call('status')
          .then((b) => setState((s) => (s.busy ? s : { ...s, running: b.running, error: '' })))
          .catch((e) => setState((s) => ({ ...s, error: e.message })))
      }, [])

      useEffect(() => {
        refresh()
        // 小深也可能从它自己的右键菜单退出，或被另一处打开：每 2 秒对一次
        const timer = setInterval(refresh, 2000)
        return () => clearInterval(timer)
      }, [refresh])

      const toggle = () => {
        const action = state.running ? 'close' : 'open'
        setState((s) => ({ ...s, busy: true, error: '' }))
        call(action)
          .then((b) => setState({ running: b.running, message: b.message || '', busy: false, error: b.ok ? '' : b.message }))
          .catch((e) => setState((s) => ({ ...s, busy: false, error: e.message })))
      }

      const on = state.running === true
      const known = state.running !== null
      const dot = h('span', {
        style: {
          display: 'inline-block', width: 8, height: 8, borderRadius: 4, marginRight: 8,
          background: !known ? '#C9CDD4' : on ? '#3DBF64' : '#C9CDD4',
        },
      })

      return h('section', {
        'aria-label': LABEL,
        style: { padding: '48px 40px', maxWidth: 760, color: 'inherit', fontFamily: 'inherit' },
      },
      h('h1', { style: { fontSize: 22, fontWeight: 600, margin: '0 0 8px' } }, LABEL),
      h('p', { style: { margin: '0 0 28px', opacity: 0.65, lineHeight: 1.6, fontSize: 14 } },
        '小深是一个独立运行的桌面小助手：在这里打开后，就算关掉 DeepSeek Harness 它也会一直在桌面上；想关掉它，回到这里点「关闭」。'),
      h('div', {
        style: {
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
          padding: '18px 20px', borderRadius: 16, border: '1px solid rgba(127,127,127,0.25)',
        },
      },
      h('div', { style: { display: 'flex', alignItems: 'center', fontSize: 15 } },
        dot, !known ? '正在查看…' : on ? '小深在桌面上' : '小深没有在运行'),
      h('button', {
        type: 'button',
        onClick: toggle,
        disabled: state.busy || !known,
        style: {
          minWidth: 88, padding: '8px 18px', borderRadius: 999, fontSize: 14, cursor: 'pointer',
          border: on ? '1px solid rgba(127,127,127,0.35)' : '1px solid transparent',
          background: on ? 'transparent' : 'currentColor',
          opacity: state.busy || !known ? 0.5 : 1,
        },
      }, h('span', { style: { color: on ? 'inherit' : 'Canvas'} },
        state.busy ? '请稍候…' : on ? '关闭' : '打开'))),
      state.error
        ? h('p', { style: { marginTop: 14, color: '#D1453B', fontSize: 13 } }, state.error)
        : state.message
          ? h('p', { style: { marginTop: 14, opacity: 0.6, fontSize: 13 } }, state.message)
          : null,
      h(SkinSection),
      h('p', { style: { marginTop: 36, opacity: 0.5, fontSize: 12, lineHeight: 1.6 } },
        '也可以在对话框里用 /pet open、/pet close、/pet status。'))
    }

    function apply(ctx) {
      const register = () => [
        ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: ID }, Page)),
        ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
          name: 'sidebar.panellist', id: ID, order: 30, label: () => LABEL,
        }, Icon)),
      ]
      if (typeof ctx.effect === 'function') {
        ctx.effect(() => {
          const disposers = register()
          return () => disposers.forEach((d) => typeof d === 'function' && d())
        }, 'dsh-pet-control: sidebar entry')
      } else {
        register()
      }
    }

    return { name: ID, inject: ['slots'], apply }
  },
})
