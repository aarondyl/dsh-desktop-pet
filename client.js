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

    async function call(action) {
      const res = await fetch(apiUrl(action), {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: '{}',
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
        style: { padding: '48px 40px', maxWidth: 560, color: 'inherit', fontFamily: 'inherit' },
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
      h('p', { style: { marginTop: 28, opacity: 0.5, fontSize: 12, lineHeight: 1.6 } },
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
