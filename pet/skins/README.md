# 小深的皮肤

一套皮肤就是一个 JSON 文件。文件名（去掉 `.json`）就是皮肤的 id。

- 内置皮肤：这个文件夹（`pet/skins/`）。
- **自己做的皮肤放 `~/.dsh-pet/skins/`**：插件更新不会覆盖它；和内置皮肤同名时，用你的。

做好以后，在 DeepSeek Harness 左侧栏「桌面助手」的皮肤区就能看到并选用。
选中的皮肤每次改 JSON 并保存，小深大约 1 秒内就会自动换上，方便边改边看。

## 格式

```json
{
  "name": "樱花",
  "author": "你的名字",
  "description": "一句话介绍",
  "colors": {
    "card": "#FFF7F9",
    "border": "#F4D6DF",
    "ink": "#4A2A35",
    "muted": "#A77F8C",
    "accent": "#F07EA0",
    "accent_dark": "#D9607F",
    "send_off": "#EBC6D1",
    "chip": "#FCE8EE",
    "badge": "#F8DCE5",
    "error": "#D1453B",
    "hover": "#FBE4EB",
    "hover_strong": "#F7D3DE",
    "button": "#5A3442",
    "on_button": "#FFFFFF",
    "stack": "#FDEFF3",
    "placeholder": "#C9A3B0"
  },
  "shape": { "card_radius": 28, "panel_radius": 24, "bar_radius": "round" },
  "font": { "family": "PingFang SC" }
}
```

每一项都可以省略，省略的用经典白的值。写错的值（不是 `#RRGGBB`、圆角不在 0~40）会被忽略。

| 键 | 用在哪 |
| --- | --- |
| `card` | 胶囊、输入栏、卡片、面板的底色 |
| `border` | 它们的描边 |
| `ink` | 正文、标题、图标 |
| `muted` | 次要文字（状态、时间）、⌄ |
| `accent` | 发送按钮（可发送时） |
| `accent_dark` | 强调色的深一档 |
| `send_off` | 发送按钮（不可发送时） |
| `chip` | 输入栏里 ⊕ 的底、「🖼 图片」标签的底 |
| `badge` | 🔔 上数字角标的底 |
| `error` | 出错的提示 |
| `hover` | 鼠标悬停在按钮 / 列表项上的底 |
| `hover_strong` | 卡片上「↩ 接着聊」的悬停底 |
| `button` | 卡片上 ×、■ 等深色小圆钮 |
| `on_button` | 深色圆钮、发送按钮上的图标颜色 |
| `stack` | 叠着的卡片后面露出来的那一截 |
| `placeholder` | 输入栏的提示字、面板里的浅灰字 |
| `card_radius` | 卡片圆角（像素） |
| `panel_radius` | ⊕ 面板圆角 |
| `bar_radius` | 胶囊和输入栏的圆角，`"round"` = 两头全圆 |
| `family` | 字体名（系统里装了的字体，比如 `"PingFang SC"`、`"Hiragino Sans GB"`） |

## 现在做不到的

小深的窗口是透明的，macOS 上 Tk 的透明窗口**画不出图片**，界面全部是矢量画出来的。
所以皮肤目前只能换颜色、圆角和字体，不能贴图片、换图标造型或加阴影。
如果你的设计需要图片或新的图标形状，告诉开发者，需要换一种绘制方式。
