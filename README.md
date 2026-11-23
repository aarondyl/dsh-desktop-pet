# 小深 · DeepSeek Harness 桌面助手

一个 [DeepSeek Harness](https://www.npmjs.com/package/@deepseek-ai/dsh) 插件：在 macOS 桌面上放一枚白色小胶囊，
点一下就能和 DeepSeek 聊天，交互参考 ChatGPT 的 macOS 桌面小窗。

- 浮在所有 App 之上（包括全屏 App），可以随意拖动，不占 Dock 和 ⌘Tab
- 每次提问是一张任务卡片，多张卡片可以同时思考；默认叠在一起，滚轮 / 双指滑动展开翻看
- 支持拖入图片、⌘V 粘贴图片、截图提问
- 点屏幕别处就收回成胶囊，回复收进 🔔
- **独立进程**：在 Harness 里打开后，关掉 Harness 它也照样在桌面上

*A DeepSeek Harness plugin that puts a small floating chat pill on your macOS desktop. macOS only.*

## 环境要求

- **macOS**（用到了 macOS 的窗口 API，不支持 Windows / Linux）
- 已安装 **DeepSeek Harness** 桌面版，并且**已登录**（小深复用你的账号，不需要 API Key）
- 带 **Tk 8.6** 的 **Python 3**，不需要装任何 Python 包。
  python.org 安装包、conda、Homebrew 的 `python-tk` 都可以；macOS 自带的 `/usr/bin/python3` 通常也行。

## 安装

在终端里运行（`desktop` 是 Harness 桌面版的配置名）：

```sh
"/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh" \
  plugin --profile desktop add github:aarondyl/dsh-desktop-pet
```

然后**重启 DeepSeek Harness**（⌘Q 退出再打开）。

更新到最新版：把上面的 `add` 换成 `update dsh-pet-control`；卸载：换成 `remove dsh-pet-control`。

## 使用

**打开 / 关闭**

- Harness 左侧栏 → **桌面助手** → 「打开」/「关闭」
- 或在对话框里输入 `/pet open`、`/pet close`、`/pet status`、`/pet`（开关切换）
- 或右键胶囊 →「退出小深」

**操作**

| 操作 | 效果 |
| --- | --- |
| ✎ | 开始新聊天 |
| 声波 | 继续最前面那张卡片的对话 |
| ⌄ / 🔔 | 收起 / 展开卡片 |
| 点屏幕别处 | 收回成胶囊（卡片收进 🔔） |
| ⊕ | 截图提问 / 图片 / 打开 DeepSeek Harness / 历史对话（打字搜索，↑↓ + 回车选择） |
| 鼠标放到卡片上 | 出现 ×（关闭）、↩（接着聊）、■（停止） |
| 点卡片正文 | 展开 / 收起长回复 |
| 在卡片上滚轮 / 双指滑动 | 叠着的卡片摊开，继续滑动一张张翻 |
| 拖图片到小深上 / ⌘V | 附上图片 |
| 拖动 | 移动到任意位置（会记住） |
| 右键 | 新聊天 / 收起展开卡片 / 清空卡片 / 退出小深 |
| `Esc` | 关面板 → 收输入栏 → 收卡片 |

## 它是怎么工作的

每句话都在后台跑一次本机的 `dsh`（Harness 自带的命令行），用一个单独的配置 `dsh-pet`：

```sh
dsh --profile dsh-pet --json --session-id <会话> "你说的话"
```

第一次运行会自动创建 `~/.dsh/profiles/dsh-pet/`，不会改动你现有的 Harness 设置。
聊天记录、窗口位置存在 `~/.dsh-pet/`。

## 常见问题

- **侧栏里没有「桌面助手」**：确认装完后重启过 Harness；在对话框里输入 `/pet` 看能不能用。
- **提示没有找到带 Tk 8.6 的 python3**：装一个 python.org 的 Python 3，或者设置环境变量 `DSH_PET_PYTHON=/路径/python3`。
- **提示没有找到本机的 dsh**：Harness 不在 `/Applications` 时，设置 `DSH_PET_CLI=/路径/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`。
- **提示去登录**：先打开 DeepSeek Harness 登录一次。
- **想从头开始**：右键「清空卡片」，或删掉 `~/.dsh-pet/state.json`。

## 不装插件，直接运行

```sh
cd pet && python3 pet.py        # 或者双击 pet/run.command
python3 pet.py --cli            # 只在终端里聊
```

## 已知限制

- 回复是整段到达的，「一字一字写出来」是界面上的打字机效果。
- 每条消息只能带一张图片。
- 界面全部用 Tk 画布矢量绘制（macOS 上 Tk 的透明窗口画不出位图），所以没有阴影和淡入淡出。

## 文件

```
index.js           插件宿主半边：/pet 命令、启停小深的接口
client.js          插件网页半边：左侧栏「桌面助手」入口和页面
cordis.patch.yml   插件注册
pet/pet.py         小深的界面（Python + Tk）
pet/brain.py       小深的大脑（调用本机 dsh）
pet/run.command    双击启动
```

## License

MIT
