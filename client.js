/**
 * dsh-pet-control · 浏览器半边
 *
 * 在 Harness 左侧栏（「插件 / 自动化任务 / 上下文洞察 …」那一列）加一个「桌面助手」入口，
 * 点开是一页：小深的开关、「我的伙伴」（像素小角色）和「配色」。真正的启停在宿主半边（index.js 的
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

    // ------------------------------------------------------------ 页面
    const MUTED_BG = 'rgba(127,127,127,0.12)'
    const LINE = 'rgba(127,127,127,0.22)'

    function GreyButton(props) {
      return h('button', {
        type: 'button', onClick: props.onClick, disabled: props.disabled, title: props.title,
        'aria-label': props.label || props.title,
        style: {
          border: 'none', background: MUTED_BG, color: 'inherit', font: 'inherit', fontSize: 14,
          padding: props.icon ? '7px 9px' : '7px 14px', borderRadius: 10, cursor: props.disabled ? 'default' : 'pointer',
          opacity: props.disabled ? 0.5 : 1, display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
        },
      }, props.children)
    }

    function RefreshIcon() {
      return h('svg', { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true },
        h('path', { d: 'M20 11a8 8 0 0 0-14.6-4.5L4 8' }), h('path', { d: 'M4 3v5h5' }),
        h('path', { d: 'M4 13a8 8 0 0 0 14.6 4.5L20 16' }), h('path', { d: 'M20 21v-5h-5' }))
    }

    // 「无」那张卡片里的胶囊：按当前配色画，和桌面上的一样
    function PillPreview(props) {
      const c = palette(props.skin || {})
      const sh = (props.skin && props.skin.shape) || {}
      const r = sh.bar_radius === 'round' || sh.bar_radius === undefined ? 24 : Math.min(24, radius(sh.bar_radius, 24) * 1.4)
      const line = (x1, y1, x2, y2, color) => h('line', { x1, y1, x2, y2, stroke: color, strokeWidth: 2, strokeLinecap: 'round' })
      return h('svg', { width: 216, height: 76, viewBox: '0 0 216 76', 'aria-hidden': true },
        h('defs', null, h('filter', { id: 'pp-shadow', x: '-20%', y: '-40%', width: '140%', height: '180%' },
          h('feDropShadow', { dx: 0, dy: 3, stdDeviation: 5, floodOpacity: 0.12 }))),
        h('rect', { x: 8, y: 14, width: 200, height: 48, rx: r, fill: c.card, stroke: c.border, filter: 'url(#pp-shadow)' }),
        h('path', { d: 'M44 45l2-6 10-10 4 4-10 10z', fill: 'none', stroke: c.ink, strokeWidth: 1.8, strokeLinejoin: 'round' }),
        h('path', { d: 'M38 30v15h15', fill: 'none', stroke: c.ink, strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }),
        line(76, 28, 76, 48, c.border),
        line(100, 34, 100, 42, c.ink), line(105, 30, 105, 46, c.ink), line(110, 34, 110, 42, c.ink), line(115, 36, 115, 40, c.ink),
        line(140, 28, 140, 48, c.border),
        h('polyline', { points: '167,35 174,42 181,35', fill: 'none', stroke: c.ink, strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' }))
    }

    function CompanionCard(props) {
      const on = props.selected
      return h('button', {
        type: 'button', role: 'radio', 'aria-checked': on, onClick: props.onClick, title: props.description || props.name,
        style: {
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 0,
          minHeight: 260, padding: '24px 20px 26px', borderRadius: 18, cursor: 'pointer', textAlign: 'center',
          background: 'transparent', color: 'inherit', font: 'inherit',
          border: on ? '2px solid currentColor' : '1px solid ' + LINE, margin: on ? 0 : 1,
          opacity: props.busy ? 0.6 : 1,
        },
      },
      h('div', { style: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 130 } }, props.art),
      h('div', { style: { fontSize: 16, fontWeight: 500, marginTop: 14 } }, props.name),
      h('div', { style: { fontSize: 14, opacity: 0.6, marginTop: 6, lineHeight: 1.5, minHeight: 42, maxWidth: 240 } },
        props.description || (props.builtin ? '' : '我的伙伴')))
    }

    function sprite(src) {
      return h('img', {
        src, alt: '', draggable: false,
        style: { height: 104, maxWidth: '100%', objectFit: 'contain', imageRendering: 'pixelated' },
      })
    }

    function Page() {
      const [st, setSt] = useState({ running: null, busy: false })
      const [data, setData] = useState({ skins: [], current: null, companions: [], companion: null })
      const [msg, setMsg] = useState({ text: '', error: false })
      const [pending, setPending] = useState(null)

      const refreshStatus = useCallback(() => {
        call('status').then((b) => setSt((s) => (s.busy ? s : { running: b.running, busy: false }))).catch(() => {})
      }, [])
      const refreshList = useCallback(() => {
        call('skins').then((b) => setData({ skins: b.skins || [], current: b.current, companions: b.companions || [], companion: b.companion })).catch(() => {})
      }, [])
      useEffect(() => {
        refreshStatus(); refreshList()
        // 小深可能从别处开关；你往文件夹里新放的伙伴 / 皮肤，也会在几秒内出现
        const a = setInterval(refreshStatus, 2000)
        const b = setInterval(refreshList, 3000)
        return () => { clearInterval(a); clearInterval(b) }
      }, [refreshStatus, refreshList])

      const say = (text, error) => setMsg({ text: text || '', error: !!error })
      const take = (b) => setData({ skins: b.skins || [], current: b.current, companions: b.companions || [], companion: b.companion })

      const toggle = () => {
        const action = st.running ? 'close' : 'open'
        setSt((s) => ({ ...s, busy: true }))
        call(action)
          .then((b) => { setSt({ running: b.running, busy: false }); say(b.ok ? '' : b.message, !b.ok) })
          .catch((e) => { setSt((s) => ({ ...s, busy: false })); say(e.message, true) })
      }
      const choose = (kind, id) => {
        if (pending) return
        if ((kind === 'companion' && id === data.companion) || (kind === 'skin' && id === data.current)) return
        setPending(kind + ':' + id)
        call(kind, { id }).then((b) => { take(b); say(b.message) }).catch((e) => say(e.message, true)).finally(() => setPending(null))
      }
      const folder = (kind) => call(kind + '-folder').then((b) => say(b.message)).catch((e) => say(e.message, true))

      const on = st.running === true
      const known = st.running !== null
      const curSkin = data.skins.find((s) => s.id === data.current)

      const sectionHead = (title, right) => h('div', {
        style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '0 0 14px', borderBottom: '1px solid ' + LINE, marginBottom: 18 },
      }, h('h2', { style: { fontSize: 17, fontWeight: 600, margin: 0 } }, title), h('div', { style: { display: 'flex', gap: 8, alignItems: 'center' } }, right))

      return h('section', {
        'aria-label': LABEL,
        style: { padding: '48px 40px 64px', maxWidth: 1080, color: 'inherit', fontFamily: 'inherit' },
      },
      // 标题 + 开关
      h('div', { style: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 } },
        h('div', null,
          h('h1', { style: { fontSize: 34, fontWeight: 500, margin: 0, letterSpacing: 0.5 } }, LABEL),
          h('p', { style: { margin: '12px 0 0', fontSize: 15, opacity: 0.65, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
            h('span', { style: { width: 8, height: 8, borderRadius: 4, background: on ? '#3DBF64' : '#C9CDD4', display: 'inline-block' } }),
            !known ? '正在查看…' : on ? '小深在桌面上' : '小深没有在运行',
            h('span', { style: { opacity: 0.8 } }, '· 关掉 DeepSeek Harness 它也会一直在'))),
        h(GreyButton, { onClick: toggle, disabled: st.busy || !known }, st.busy ? '请稍候…' : on ? '关闭小深' : '打开小深')),
      msg.text ? h('p', { style: { margin: '14px 0 0', fontSize: 13, color: msg.error ? '#D1453B' : 'inherit', opacity: msg.error ? 1 : 0.6 } }, msg.text) : null,

      // 伙伴
      h('div', { style: { marginTop: 44 } },
        sectionHead('我的伙伴', [
          h(GreyButton, { key: 'r', icon: true, title: '刷新', onClick: refreshList }, h(RefreshIcon)),
          h(GreyButton, { key: 'a', onClick: () => folder('companions') }, '添加伙伴'),
        ]),
        h('div', { role: 'radiogroup', 'aria-label': '伙伴', style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 22 } },
          h(CompanionCard, {
            key: 'none', name: '无', description: '只有胶囊，最安静的样子',
            selected: data.companion === 'none', busy: pending === 'companion:none',
            onClick: () => choose('companion', 'none'), art: h(PillPreview, { skin: curSkin }),
          }),
          data.companions.map((c) => h(CompanionCard, {
            key: c.id, name: c.name, description: c.description, builtin: c.builtin,
            selected: data.companion === c.id, busy: pending === 'companion:' + c.id,
            onClick: () => choose('companion', c.id),
            art: c.image ? sprite(c.image) : h('div', { style: { fontSize: 13, opacity: 0.5 } }, '图片太大，显示不了'),
          })))),

      // 配色
      h('div', { style: { marginTop: 52 } },
        sectionHead('配色', [h(GreyButton, { key: 'f', onClick: () => folder('skins') }, '打开配色文件夹')]),
        h('div', { role: 'radiogroup', 'aria-label': '配色', style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16 } },
          data.skins.map((skin) => {
            const sel = skin.id === data.current
            return h('button', {
              key: skin.id, type: 'button', role: 'radio', 'aria-checked': sel, disabled: skin.broken,
              title: skin.broken ? '这个配色文件不是合法的 JSON' : skin.description || skin.name,
              onClick: () => choose('skin', skin.id),
              style: {
                textAlign: 'left', padding: 0, overflow: 'hidden', cursor: skin.broken ? 'not-allowed' : 'pointer',
                borderRadius: 14, background: 'transparent', color: 'inherit', font: 'inherit',
                border: sel ? '2px solid currentColor' : '1px solid ' + LINE, margin: sel ? 0 : 1,
                opacity: skin.broken ? 0.45 : pending === 'skin:' + skin.id ? 0.6 : 1,
              },
            },
            skin.broken ? h('div', { style: { height: 112, display: 'grid', placeItems: 'center', fontSize: 12, opacity: 0.6 } }, '文件有误')
              : h(SkinPreview, { skin }),
            h('div', { style: { padding: '9px 12px 11px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 } },
              h('span', { style: { fontSize: 14, fontWeight: sel ? 600 : 400 } }, skin.name),
              h('span', { style: { fontSize: 12, opacity: 0.5 } }, sel ? '使用中' : skin.builtin ? '内置' : '我的')))
          }))),

      h('p', { style: { marginTop: 40, opacity: 0.5, fontSize: 12, lineHeight: 1.7 } },
        '伙伴是一张 PNG 像素图（16~24 像素见方最好），配色是一个 JSON 文件；放进对应文件夹就会出现在这里，文件夹里有说明。',
        h('br'), '也可以在对话框里用 /pet open、/pet close、/pet status。'))
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
