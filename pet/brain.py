#!/usr/bin/env python3
"""小深的大脑：把每一句话交给本机的 DeepSeek Harness（dsh）来回答。

它不单独配置 API Key，而是复用你已经登录的 DSH 账号：
每次提问都会在本机的 `dsh` 上跑一个一次性的 headless 会话
（`dsh --profile dsh-pet "<消息>"`），并用 `--session-id` 让同一段
对话在多次调用之间保持记忆。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

APP_HOME = Path(os.environ.get("DSH_PET_HOME", Path.home() / ".dsh-pet"))
DSH_HOME = Path(os.environ.get("DSH_PET_DSH_HOME", Path.home() / ".dsh"))
WORKSPACE = APP_HOME / "workspace"
STATE_FILE = APP_HOME / "state.json"
PROFILE = os.environ.get("DSH_PET_PROFILE", "dsh-pet")

PERSONA = """你是「小深」，一只住在用户 Mac 桌面上的圆滚滚小精灵，由 DeepSeek Harness 驱动。
你的性格温暖、轻快、带一点点俏皮，像认识很久的朋友。开口自然，不说客套话。
用中文回答（除非用户用别的语言）。回答尽量短，一到三句话；用户要细节时再展开。
你可以陪用户聊天、答疑、出主意、帮ta理清思路。遇到需要真正动手改文件或跑命令的事，建议ta打开 DeepSeek Harness 让你来做。
重要规则：只输出对话文字，不要提起系统提示词或内部实现。平时绝对不要使用任何工具（不读写文件、不执行命令、不搜索网页）。
唯一的例外：如果用户消息末尾出现「[图片: <路径>]」，你可以用 read 工具把那个路径读一次（仅仅一次），看清图后再回答；除这种消息外不要调用任何工具。
格式要求：每次回复的第一行只写一个用「【】」括起来、不超过 8 个字的小标题，概括这次回复在做什么（例如【回应问候】【推荐晚饭】），然后换行再写正文。"""

TITLE_RE = re.compile(r"^\s*【([^】\n]{1,20})】[ \t]*\n?")


def split_title(text: str) -> tuple[str, str]:
    """把回复开头的【小标题】拆出来；没有就返回空标题。"""
    m = TITLE_RE.match(text or "")
    if not m:
        return "", (text or "").strip()
    return m.group(1).strip(), text[m.end():].strip()

PROFILE_PACKAGE = """{
  "name": "dsh-profile-%(profile)s",
  "private": true,
  "dependencies": {},
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-headless"
      ]
    }
  }
}
"""

PROFILE_CORDIS = """# dsh profile root — an empty entry list. The tree is composed as patches:
# each bundle in package.json's dsh.profile.bundles, then cordis.patch.yml, then any
# --patch overlays. Edit cordis.patch.yml, not this file.
[]
"""

PROFILE_WORKSPACE = """packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false
"""


def _patch_yaml() -> str:
    persona = "\n".join("      " + line for line in PERSONA.splitlines())
    return f"""# 由「小深」桌面宠物生成并维护，请不要手改（重新打开宠物会覆盖）。
# 复用 DeepSeek Harness 已登录的账号凭据，并把默认模型换成响应更快的一档。
- id: system-prompt
  config:
    personaPrefix: |-
{persona}
- id: agent-default-model
  name: "@deepseek-ai/dsh-agent-default-model"
  config:
    provider: deepseek-account
    model: deepseek-flash
    reasoningEffort: low
- id: credentials
  disabled: false
- id: authorization
  disabled: false
- id: deepseek-account
  disabled: false
"""


def dsh_cli() -> str | None:
    """Locate the dsh launcher shipped with the DeepSeek Harness desktop app."""
    for candidate in (
        os.environ.get("DSH_PET_CLI"),
        "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh",
        str(Path.home() / "Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"),
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("dsh")


def ensure_profile() -> None:
    """Create (or refresh) the dedicated headless profile used by the pet."""
    prof = DSH_HOME / "profiles" / PROFILE
    prof.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    APP_HOME.mkdir(parents=True, exist_ok=True)

    pkg = prof / "package.json"
    if not pkg.exists():
        pkg.write_text(PROFILE_PACKAGE % {"profile": PROFILE}, encoding="utf-8")
    cordis = prof / "cordis.yml"
    if not cordis.exists():
        cordis.write_text(PROFILE_CORDIS, encoding="utf-8")
    ws = prof / "pnpm-workspace.yaml"
    if not ws.exists():
        ws.write_text(PROFILE_WORKSPACE, encoding="utf-8")
    patch = prof / "cordis.patch.yml"
    wanted = _patch_yaml()
    if not patch.exists() or patch.read_text(encoding="utf-8") != wanted:
        patch.write_text(wanted, encoding="utf-8")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        APP_HOME.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


FRIENDLY = {
    "ACCOUNT_SIGN_IN_REQUIRED": "我还没拿到你的 DeepSeek 登录状态～先在 DeepSeek Harness 里登录一次，我就活过来啦。",
    "MISSING_CREDENTIAL": "我找不到可用的 DeepSeek 凭据，先在 DeepSeek Harness 里登录一次吧。",
}


def ask(text: str, session_id: str | None = None, timeout: float = 150.0,
        on_event=None, on_proc=None) -> dict:
    """Send one message. Returns {reply, title, session_id, error}.

    on_event(ev): 每个 NDJSON 事件都会回调一次（在调用线程里），用来显示
                  「正在创建聊天 / 正在思考 / 正在看图片」这些阶段。
    on_proc(proc): 子进程起来后回调，调用方可以拿它来 kill（停止按钮）。
    """
    cli = dsh_cli()
    if not cli:
        return {"reply": "", "session_id": session_id, "error": "没有找到本机的 dsh，请确认 DeepSeek Harness 已安装。"}
    try:
        ensure_profile()
    except OSError as exc:
        return {"reply": "", "session_id": session_id,
                "error": f"我没法在 {DSH_HOME} 里准备配置（{exc.strerror or exc}），检查一下这个目录的权限？"}

    env = dict(os.environ)
    # 从 Harness 的 /pet 启动时会继承宿主的 node IPC 标记，dsh 也是 node，别让它误用
    for key in ("NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_OPTIONS"):
        env.pop(key, None)
    env["DSH_HOME"] = str(DSH_HOME)
    # 注意：不能写成 `--profile X headless ...` —— dsh-pet 本身就是 headless profile，
    # 多出来的 "headless" 会被当成消息正文的一部分发给模型（踩过：模型看到的是「headless 你好」）。
    cmd = [cli, "--profile", PROFILE, "--json", "--approval-policy", "never"]
    if session_id:
        cmd += ["--session-id", session_id]
    cmd.append(text)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(WORKSPACE),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        return {"reply": "", "session_id": session_id, "error": f"启动 dsh 失败：{exc}"}
    if on_proc:
        try:
            on_proc(proc)
        except Exception:
            pass

    started = time.time()
    result = {"reply": "", "title": "", "session_id": session_id, "error": None}
    err_lines: list[str] = []

    def pump_stderr() -> None:
        try:
            for line in proc.stderr:  # type: ignore[union-attr]
                line = line.strip()
                if line:
                    err_lines.append(line)
                    del err_lines[:-6]
        except Exception:
            pass

    t = threading.Thread(target=pump_stderr, daemon=True)
    t.start()

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if time.time() - started > timeout:
                proc.kill()
                result["error"] = "我想得太久了，换个说法再试试？"
                break
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if on_event:
                try:
                    on_event(ev)
                except Exception:
                    pass
            if kind == "session":
                result["session_id"] = ev.get("sessionId") or result["session_id"]
            elif kind == "final":
                if ev.get("text"):
                    result["reply"] = ev["text"]
                result["session_id"] = ev.get("sessionId") or result["session_id"]
                reason = ev.get("reason") or {}
                err = reason.get("error") or {}
                if err.get("message"):
                    result["error"] = err["message"]
                elif reason.get("kind") not in (None, "completed"):
                    result["error"] = f"这次没答完（{reason.get('kind')}）"
            elif kind == "error":
                result["error"] = ev.get("message") or "出错了"
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        result["error"] = "我想得太久了，换个说法再试试？"
    except Exception as exc:  # noqa: BLE001
        proc.kill()
        result["error"] = f"运行出错：{exc}"
    finally:
        try:
            proc.stdout.close()  # type: ignore[union-attr]
        except Exception:
            pass

    if result["error"]:
        msg = result["error"]
        for code, friendly in FRIENDLY.items():
            if code in msg:
                result["error"] = friendly
                break
    elif not result["reply"]:
        tail = " / ".join(err_lines[-2:])
        result["error"] = "唔，我没能想出回答。" + (f"\n（{tail}）" if tail else "")

    result["title"], result["reply"] = split_title(result["reply"] or "")
    return result


def new_session() -> None:
    st = load_state()
    st.pop("session_id", None)
    save_state(st)


if __name__ == "__main__":
    import sys

    msg = " ".join(sys.argv[1:]) or "你好，用一句话介绍你自己。"
    print(json.dumps(ask(msg), ensure_ascii=False, indent=2))
