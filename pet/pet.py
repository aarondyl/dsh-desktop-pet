#!/usr/bin/env python3
"""小深 · 桌面小精灵（胶囊版）

收起时是一枚小小的白色胶囊；点一下变成一条输入栏，说完话回车，
它把回复做成一张小纸条浮在胶囊上方。
所有界面都是 Tk 画布上的矢量图形 —— macOS 的透明窗口里画不出图片。
"""
from __future__ import annotations

import json
import math
import os
import re
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

from pathlib import Path

import brain

# ---------------------------------------------------------------- palette
CARD = "#FFFFFF"
BORDER = "#E4E6EA"
INK = "#1F2328"
MUTED = "#8A919E"
MINT = "#2FC9A8"
MINT_DARK = "#1FA88C"
SEND_OFF = "#C9D2DC"
CHIP = "#F1F2F4"
BADGE = "#E6E8EC"        # 铃铛角标：无色（浅灰底 + 深色数字），用户不要绿色

# ---------------------------------------------------------------- layout
# 竖直方向：顶部一条「栏」（胶囊或输入栏，块高 BAR_H，内缩 4px 画圆角），
# 下方是任务卡片（离屏幕底太近时整体翻到栏的上方）。锚点 = 栏的右上角。
W = 294                 # 有卡片/输入栏时窗口的宽度（本体 282）。352 会挡浏览器地址栏，280 又嫌短；按用户截图量的
BAR_H = 42              # 栏所占的块高（含上下各 4px 透明边）→ 胶囊本体高 34，和 ChatGPT 桌面助手一样
PILL_W = 130            # 只有胶囊时窗口的宽度 → 胶囊本体宽 122
CARD_MIN_H = 64
CARD_LINES = 3          # 卡片默认最多显示几行回复，点卡片展开到 CARD_LINES_OPEN
CARD_LINES_OPEN = 14
STACK = 8               # 多张卡片时，后面那张露出来的高度
LIST_MAX = 3            # 摊开时一次显示几张卡片
TASKS_KEEP = 6          # 最多保留几张卡片（多余的最旧的已完成卡片被丢掉）
UPLOADS_KEEP = 30       # uploads/ 里最多保留几张图
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp", ".tif", ".tiff", ".bmp"}
HISTORY_KEEP = 30       # ⊕ 面板里的历史对话最多留几条

NO_LINE_START = set("，。、；：？！）》」』】’”…—,.;:?!)]}%")

STATUS = {"creating": "正在创建聊天", "thinking": "正在思考", "tool": "正在看图片"}
RUNNING = tuple(STATUS)

ERR = "#D1453B"
HOVER = "#ECEEF1"
DARK = "#2B2F36"
STACK_FILL = "#F7F8FA"
ON_BUTTON = "#FFFFFF"     # 强调色 / 深色圆钮上的图标颜色
PLACEHOLDER = "#AEB6C2"   # 输入栏提示字、面板里的浅灰字
HOVER_STRONG = "#E3E6EA"  # 「↩ 接着聊」的悬停底
CARD_R = 24               # 卡片圆角
PANEL_R = 20              # ⊕ 面板圆角
BAR_R = None              # 胶囊 / 输入栏圆角；None = 两头全圆
FONT_FAMILY = "PingFang SC"


def bar_r(h):
    return h / 2 if BAR_R is None else min(BAR_R, h / 2)


# ---------------------------------------------------------------- skins
# 一套皮肤 = 一个 JSON 文件，见 skins/README.md。内置的在 pet/skins/，
# 用户自己做的放 ~/.dsh-pet/skins/（插件更新不会覆盖；同名时用户的优先）。
# 当前选中哪一套写在 ~/.dsh-pet/skin.json：{"skin": "<文件名去掉 .json>"}，
# 桌面助手页面改的就是这个文件，小深每秒看一次，变了就换装重画。
SKIN_TOKENS = {
    "colors": {
        "card": "CARD", "border": "BORDER", "ink": "INK", "muted": "MUTED",
        "accent": "MINT", "accent_dark": "MINT_DARK", "send_off": "SEND_OFF",
        "chip": "CHIP", "badge": "BADGE", "error": "ERR", "hover": "HOVER",
        "hover_strong": "HOVER_STRONG", "button": "DARK", "on_button": "ON_BUTTON",
        "stack": "STACK_FILL", "placeholder": "PLACEHOLDER",
    },
    "shape": {"card_radius": "CARD_R", "panel_radius": "PANEL_R", "bar_radius": "BAR_R"},
    "font": {"family": "FONT_FAMILY"},
}
SKINS_BUILTIN = Path(__file__).resolve().parent / "skins"
SKINS_USER = brain.APP_HOME / "skins"
SKIN_CHOICE = brain.APP_HOME / "skin.json"
DEFAULT_SKIN = "classic"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SKIN_BASE = {name: globals()[name] for group in SKIN_TOKENS.values() for name in group.values()}


def skin_files() -> dict:
    found = {}
    for folder in (SKINS_BUILTIN, SKINS_USER):   # 后面的覆盖前面的：用户皮肤优先
        try:
            for f in sorted(folder.glob("*.json")):
                found[f.stem] = f
        except OSError:
            pass
    return found


def chosen_skin() -> str:
    try:
        sid = json.loads(SKIN_CHOICE.read_text(encoding="utf-8")).get("skin")
        return sid if isinstance(sid, str) and sid else DEFAULT_SKIN
    except (OSError, ValueError, AttributeError):
        return DEFAULT_SKIN


# 伙伴：站在胶囊左边的像素小角色。一个伙伴 = 一张 PNG（可选同名 .json 写名字和介绍）。
# 内置在 pet/companions/，用户的放 ~/.dsh-pet/companions/；选择也记在 skin.json 的 "companion"。
COMPANIONS_BUILTIN = Path(__file__).resolve().parent / "companions"
COMPANIONS_USER = brain.APP_HOME / "companions"
NO_COMPANION = "none"
SPRITE_TARGET_H = 46    # 伙伴显示高度大约这么高（像素图按整数倍放大，保持像素锐利）
SPRITE_MAX = (84, 64)   # 最大显示宽高；更大的图会按整数步长抽样缩小


def companion_files() -> dict:
    found = {}
    for folder in (COMPANIONS_BUILTIN, COMPANIONS_USER):
        try:
            for f in sorted(folder.glob("*.png")):
                found[f.stem] = f
        except OSError:
            pass
    return found


def _choice() -> dict:
    try:
        d = json.loads(SKIN_CHOICE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def chosen_companion() -> str:
    cid = _choice().get("companion")
    return cid if isinstance(cid, str) and cid else NO_COMPANION


def skin_signature():
    """选择文件、皮肤文件、伙伴图的修改时间：任何一个变了就重新换装（设计时改文件也能实时看到）。"""
    sid, cid = chosen_skin(), chosen_companion()
    sig = []
    for f in (SKIN_CHOICE, skin_files().get(sid), companion_files().get(cid)):
        try:
            sig.append(f.stat().st_mtime_ns if f else None)
        except OSError:
            sig.append(None)
    return sid, cid, tuple(sig)


def load_sprite(path: Path) -> dict | None:
    """PNG → 一组色块。macOS 上 Tk 的透明窗口画不出位图，但画得出矩形：
    逐像素读出颜色（读图不受影响），同一行相邻同色的像素合并成一个矩形。"""
    try:
        img = tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None
    try:
        iw, ih = img.width(), img.height()
        if not iw or not ih:
            return None
        step = max(1, math.ceil(max(iw / SPRITE_MAX[0], ih / SPRITE_MAX[1])))
        sw, sh = iw // step, ih // step
        scale = max(1, min(round(SPRITE_TARGET_H / sh), SPRITE_MAX[1] // sh, SPRITE_MAX[0] // sw))
        runs = []
        for y in range(sh):
            run_x, run_c = 0, None
            for x in range(sw + 1):
                col = None
                if x < sw:
                    px, py = x * step, y * step
                    if not img.transparency_get(px, py):
                        r, g, b = img.get(px, py)[:3]
                        col = f"#{r:02x}{g:02x}{b:02x}"
                if col != run_c:
                    if run_c is not None:
                        runs.append((run_x * scale, y * scale, x * scale, (y + 1) * scale, run_c))
                    run_x, run_c = x, col
        if not runs:
            return None
        return {"w": sw * scale, "h": sh * scale, "runs": runs}
    finally:
        img = None


def apply_skin(skin_id: str) -> str:
    """先恢复默认，再把皮肤里写了的、合法的值盖上去；坏值忽略。返回实际生效的皮肤 id。"""
    g = globals()
    g.update(_SKIN_BASE)
    path = skin_files().get(skin_id)
    if path is None:
        return DEFAULT_SKIN if skin_id != DEFAULT_SKIN else skin_id
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_SKIN
    if not isinstance(data, dict):
        return DEFAULT_SKIN
    for group, keys in SKIN_TOKENS.items():
        section = data.get(group)
        if not isinstance(section, dict):
            continue
        for key, name in keys.items():
            v = section.get(key)
            if group == "colors" and isinstance(v, str) and _HEX.match(v):
                g[name] = v
            elif group == "shape" and name == "BAR_R" and v == "round":
                g[name] = None
            elif group == "shape" and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 40:
                g[name] = v
            elif group == "font" and isinstance(v, str) and v.strip():
                g[name] = v.strip()
    return skin_id

TRANSPARENT = "systemTransparent"

# ------------------------------------------------------------ macOS window
class _ObjC:
    """最小的 ctypes Objective-C 桥（这台机器没有 pyobjc）。

    每次调用都现造一个 CFUNCTYPE：objc_msgSend 的参数/返回类型因方法而异，
    共用一个签名会在 arm64 上传错寄存器。
    """

    def __init__(self) -> None:
        import ctypes
        import ctypes.util
        self.c = ctypes
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        for name, res, args in (
            ("objc_getClass", ctypes.c_void_p, [ctypes.c_char_p]),
            ("sel_registerName", ctypes.c_void_p, [ctypes.c_char_p]),
            ("object_getClass", ctypes.c_void_p, [ctypes.c_void_p]),
            ("class_replaceMethod", ctypes.c_void_p,
             [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]),
        ):
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = res, args
        self.lib = lib

    def cls(self, name: str):
        return self.lib.objc_getClass(name.encode())

    def sel(self, name: str):
        return self.lib.sel_registerName(name.encode())

    def send(self, ret, obj, sel: str, *args, argtypes=()):
        c = self.c
        fn = c.CFUNCTYPE(ret, c.c_void_p, c.c_void_p, *argtypes)(("objc_msgSend", self.lib))
        return fn(obj, self.sel(sel), *args)

    def app(self):
        return self.send(self.c.c_void_p, self.cls("NSApplication"), "sharedApplication")

    def nsstr(self, s: str):
        return self.send(self.c.c_void_p, self.cls("NSString"), "stringWithUTF8String:",
                         s.encode(), argtypes=[self.c.c_char_p])

    def pystr(self, ns) -> str:
        if not ns:
            return ""
        raw = self.send(self.c.c_char_p, ns, "UTF8String")
        return raw.decode("utf-8", "replace") if raw else ""

    def windows(self):
        c = self.c
        wins = self.send(c.c_void_p, self.app(), "windows")
        for i in range(self.send(c.c_ulong, wins, "count")):
            w = self.send(c.c_void_p, wins, "objectAtIndex:", i, argtypes=[c.c_ulong])
            if w and self.send(c.c_bool, w, "isVisible"):
                yield w


_OBJC_BRIDGE: _ObjC | None = None


def objc() -> _ObjC:
    global _OBJC_BRIDGE
    if _OBJC_BRIDGE is None:
        _OBJC_BRIDGE = _ObjC()
    return _OBJC_BRIDGE


# 浮在所有 App（包括全屏 App）之上。NSStatusWindowLevel：比普通窗口(0)、
# 其他 App 的浮动面板(3)、Dock(20) 都高，比弹出菜单(101)低。
PET_LEVEL = 25
# CanJoinAllSpaces | Stationary（Mission Control 里不跟着飞）| IgnoresCycle（⌘` 不切到它）
# | FullScreenAuxiliary（能出现在别的 App 的全屏空间里）
PET_BEHAVIOR = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)


def make_chromeless(root: tk.Tk) -> bool:
    """去掉标题栏，但让窗口仍能成为 key window（否则收不到键盘输入）。

    macOS 上 overrideredirect 的窗口 canBecomeKeyWindow 是 NO，输入框永远
    打不了字；这里改成「有标题栏样式 + 全尺寸内容视图 + 隐藏标题栏与三个
    按钮」，视觉上仍然是一条无边框的胶囊。
    第五轮起还做三件事：App 改成 accessory（没有 Dock 图标，才能浮在别的 App
    的全屏空间里）、窗口层级提到 PET_LEVEL、内容视图接受「第一下点击」。
    """
    try:
        o = objc()
        c = o.c
        app = o.app()
        # NSApplicationActivationPolicyAccessory：像 ChatGPT 桌面助手一样不占 Dock。
        # 普通 App 的窗口进不了别的 App 的全屏 Space，FullScreenAuxiliary 也没用。
        o.send(c.c_bool, app, "setActivationPolicy:", 1, argtypes=[c.c_long])
        for w in o.windows():
            mask = o.send(c.c_ulong, w, "styleMask")
            o.send(None, w, "setStyleMask:", mask | 1 | (1 << 15), argtypes=[c.c_ulong])
            o.send(None, w, "setTitleVisibility:", 1, argtypes=[c.c_long])
            o.send(None, w, "setTitlebarAppearsTransparent:", True, argtypes=[c.c_bool])
            for b in (0, 1, 2):
                btn = o.send(c.c_void_p, w, "standardWindowButton:", b, argtypes=[c.c_long])
                if btn:
                    o.send(None, btn, "setHidden:", True, argtypes=[c.c_bool])
            keep_floating(w)
            view = o.send(c.c_void_p, w, "contentView")
            if view:
                _accept_first_mouse(view)
                _register_drop(view)
        o.send(None, app, "activateIgnoringOtherApps:", True, argtypes=[c.c_bool])
        return True
    except Exception:
        return False


def keep_floating(w=None) -> None:
    """（重新）设置层级与 Spaces 行为。setStyleMask 和 Tk 的 -topmost 都会把层级改回去，
    所以 tick 里也会定期调一次。"""
    try:
        o = objc()
        c = o.c
        for win in ([w] if w else list(o.windows())):
            if o.send(c.c_long, win, "level") != PET_LEVEL:
                o.send(None, win, "setLevel:", PET_LEVEL, argtypes=[c.c_long])
            o.send(None, win, "setHidesOnDeactivate:", False, argtypes=[c.c_bool])
            o.send(None, win, "setCollectionBehavior:", PET_BEHAVIOR, argtypes=[c.c_ulong])
            o.send(None, win, "setCanHide:", False, argtypes=[c.c_bool])  # ⌘H / 「隐藏其他」不藏它
    except Exception:
        pass


_KEEP: list = []        # 交给 Objective-C 的 Python 回调必须一直持有，否则会被回收后崩溃
DROPS: list = []        # 拖进来的东西：("file", 路径) / ("data", 路径)；Pet.poll 取走


def _accept_first_mouse(view) -> None:
    """TKContentView 默认 acceptsFirstMouse: = NO：别的 App 在前台时，点小深的第一下
    只会激活它、不会传给 Tk，于是拖不动、点不开。改成 YES。"""
    o = objc()
    c = o.c
    if any(k[0] == "afm" for k in _KEEP):
        return
    imp = c.CFUNCTYPE(c.c_bool, c.c_void_p, c.c_void_p, c.c_void_p)(lambda s, cmd, ev: True)
    _KEEP.append(("afm", imp))
    o.lib.class_replaceMethod(o.lib.object_getClass(view), o.sel("acceptsFirstMouse:"),
                              c.cast(imp, c.c_void_p), b"B@:@")


def _register_drop(view) -> None:
    """把图片拖进小深：给 Tk 的内容视图补上 NSDraggingDestination 的几个方法。

    Tk 8.6 自己不支持拖放，这台机器也没有 tkdnd。TKContentView 是整个窗口唯一的
    NSView（没有子视图），所以注册在它上面就覆盖了胶囊、输入栏和卡片。
    """
    o = objc()
    c = o.c
    if not any(k[0] == "drop" for k in _KEEP):
        def entered(_self, _cmd, sender):
            return 1  # NSDragOperationCopy：鼠标上显示绿色的 +

        def prepare(_self, _cmd, sender):
            return True

        def perform(_self, _cmd, sender):
            try:
                return _take_drop(sender)
            except Exception:
                return False

        op_t = c.CFUNCTYPE(c.c_ulong, c.c_void_p, c.c_void_p, c.c_void_p)
        ok_t = c.CFUNCTYPE(c.c_bool, c.c_void_p, c.c_void_p, c.c_void_p)
        imps = {"draggingEntered:": (op_t(entered), b"Q@:@"),
                "draggingUpdated:": (op_t(entered), b"Q@:@"),
                "prepareForDragOperation:": (ok_t(prepare), b"B@:@"),
                "performDragOperation:": (ok_t(perform), b"B@:@")}
        klass = o.lib.object_getClass(view)
        for name, (imp, enc) in imps.items():
            _KEEP.append(("drop", imp))
            o.lib.class_replaceMethod(klass, o.sel(name), c.cast(imp, c.c_void_p), enc)
    types = [o.nsstr(t) for t in ("public.file-url", "public.png", "public.tiff")]
    arr = (c.c_void_p * len(types))(*types)
    nsarr = o.send(c.c_void_p, o.cls("NSArray"), "arrayWithObjects:count:",
                   c.cast(arr, c.c_void_p), len(types), argtypes=[c.c_void_p, c.c_ulong])
    o.send(None, view, "registerForDraggedTypes:", nsarr, argtypes=[c.c_void_p])


def _take_drop(sender) -> bool:
    """在 performDragOperation: 里读拖拽剪贴板：优先文件，其次 PNG/TIFF 原始数据
    （从浏览器里直接拖图片时常见）。这里只落盘、记下路径，转格式交给 Pet。"""
    from urllib.parse import unquote, urlparse
    o = objc()
    c = o.c
    pb = o.send(c.c_void_p, sender, "draggingPasteboard")
    url = o.pystr(o.send(c.c_void_p, pb, "stringForType:", o.nsstr("public.file-url"),
                         argtypes=[c.c_void_p]))
    if url.startswith("file://"):
        DROPS.append(("file", unquote(urlparse(url).path)))
        return True
    for uti, ext in (("public.png", "png"), ("public.tiff", "tiff")):
        data = o.send(c.c_void_p, pb, "dataForType:", o.nsstr(uti), argtypes=[c.c_void_p])
        if data:
            uploads = brain.WORKSPACE / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            out = uploads / f"drop-{time.strftime('%Y%m%d-%H%M%S')}.{ext}"
            ok = o.send(c.c_bool, data, "writeToFile:atomically:", o.nsstr(str(out)), True,
                        argtypes=[c.c_void_p, c.c_bool])
            if ok:
                DROPS.append(("data", str(out)))
                return True
    return False


def rr(c: tk.Canvas, x1, y1, x2, y2, r, fill, outline="", width=1, tags=()) -> int:
    """圆角矩形：四个角是真正的圆弧（逐点算出来，不靠 smooth）。

    旧版用「重复控制点 + smooth=True」，Tk 的 B 样条会把圆角半径缩到一半左右，
    所以 r = 高/2 的胶囊画出来只是小圆角矩形（用户截图里看得很明显）。
    """
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    n = max(4, int(r / 1.5))
    pts: list[float] = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                       (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return c.create_polygon(pts, fill=fill or "", outline=outline, width=width, tags=tags)


def app_is_active() -> bool | None:
    """[NSApp isActive]。用来实现「点空白处收回」：从激活变成不激活 = 用户点了别处。"""
    try:
        o = objc()
        return bool(o.send(o.c.c_bool, o.app(), "isActive"))
    except Exception:
        return None


# ---------------------------------------------------------------- icons
def icon_edit(c, cx, cy, s=12, color=None, tags=("pill",), width=1.3):
    color = color or INK
    """写作：右上角开口的圆角方框 + 一支斜着的笔。"""
    h = s / 2
    items = [rr(c, cx - h, cy - h + 1, cx + h - 1, cy + h, 3, "", color, width, tags)]
    items.append(c.create_rectangle(cx + h - 5, cy - h - 2, cx + h + 1, cy - h + 4,
                                    fill=CARD, outline="", tags=tags))
    items.append(c.create_line(cx - h + 3.5, cy + h - 3.5, cx + h + 0.5, cy - h + 0.5, fill=color,
                               width=width + 0.3, capstyle="round", tags=tags))
    return items


def icon_wave(c, cx, cy, s=11, color=None, tags=("pill",), phase=0):
    color = color or INK
    weights = (0.4, 0.7, 1.0, 0.7, 0.4)
    out = []
    gap = 2.8
    for i, base in enumerate(weights):
        wobble = 0.18 * ((i + phase) % 5) / 4 if phase else 0.0
        half = s * min(1.0, base + wobble) / 2
        x = cx + (i - 2) * gap
        out.append(c.create_line(x, cy - half, x, cy + half, fill=color,
                                 width=1.5, capstyle="round", tags=tags))
    return out


def icon_chevron(c, cx, cy, s=7, color=None, tags=("pill",), up=False):
    color = color or MUTED
    d = s * (1 if up else -1)
    c.create_line(cx - s, cy - d / 2, cx, cy + d / 2, fill=color, width=1.5,
                  capstyle="round", tags=tags)
    c.create_line(cx, cy + d / 2, cx + s, cy - d / 2, fill=color, width=1.5,
                  capstyle="round", tags=tags)


def icon_plus(c, cx, cy, s=6, color=None, tags=()):
    color = color or INK
    c.create_line(cx - s, cy, cx + s, cy, fill=color, width=1.8, capstyle="round", tags=tags)
    c.create_line(cx, cy - s, cx, cy + s, fill=color, width=1.8, capstyle="round", tags=tags)


def icon_send(c, cx, cy, r=15, enabled=True, tags=()):
    fill = MINT if enabled else SEND_OFF
    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="", tags=tags)
    w = max(1.8, r * 0.14)
    c.create_line(cx, cy + r * 0.46, cx, cy - r * 0.44, fill=ON_BUTTON, width=w,
                  capstyle="round", tags=tags)
    c.create_line(cx - r * 0.34, cy - r * 0.12, cx, cy - r * 0.48, fill=ON_BUTTON, width=w,
                  capstyle="round", tags=tags)
    c.create_line(cx, cy - r * 0.48, cx + r * 0.34, cy - r * 0.12, fill=ON_BUTTON, width=w,
                  capstyle="round", tags=tags)


def badge_check(c, cx, cy, r=11, tags=()):
    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=MINT, outline="", tags=tags)
    c.create_line(cx - r * 0.45, cy + r * 0.02, cx - r * 0.08, cy + r * 0.38,
                  fill=ON_BUTTON, width=max(1.8, r * 0.22), capstyle="round", tags=tags)
    c.create_line(cx - r * 0.08, cy + r * 0.38, cx + r * 0.48, cy - r * 0.34,
                  fill=ON_BUTTON, width=max(1.8, r * 0.22), capstyle="round", tags=tags)




def icon_bell(c, cx, cy, color=None, tags=()):
    color = color or INK
    kw = dict(fill=color, width=1.3, capstyle="round", joinstyle="round", tags=tags)
    c.create_arc(cx - 4.5, cy - 7, cx + 4.5, cy + 2, start=0, extent=180, style="arc",
                 outline=color, width=1.3, tags=tags)
    c.create_line(cx - 4.5, cy - 2.5, cx - 4.5, cy + 1.5, cx - 6, cy + 4, **kw)
    c.create_line(cx + 4.5, cy - 2.5, cx + 4.5, cy + 1.5, cx + 6, cy + 4, **kw)
    c.create_line(cx - 6, cy + 4, cx + 6, cy + 4, **kw)
    c.create_line(cx - 1.5, cy + 6.5, cx + 1.5, cy + 6.5, **kw)


def badge_count(c, cx, cy, n, font, tags=()):
    c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=BADGE, outline=CARD, width=1.2, tags=tags)
    c.create_text(cx, cy, text=str(n) if n < 10 else "9+", fill=INK, font=font, tags=tags)


def badge_error(c, cx, cy, r=9, font=None, tags=()):
    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ERR, outline="", tags=tags)
    c.create_text(cx, cy, text="!", fill=ON_BUTTON, font=font, tags=tags)


def icon_return(c, cx, cy, color=None, tags=()):
    color = color or INK
    c.create_line(cx + 5, cy - 5, cx + 5, cy + 2, cx - 5, cy + 2, fill=color, width=1.6,
                  arrow="last", arrowshape=(5, 6, 3), capstyle="round", joinstyle="round", tags=tags)


def icon_stop(c, cx, cy, r=15, tags=()):
    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=DARK, outline="", tags=tags)
    rr(c, cx - 5, cy - 5, cx + 5, cy + 5, 2, ON_BUTTON, "", 0, tags)


def btn_close(c, cx, cy, r=9, tags=()):
    c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=DARK, outline=CARD, width=1.5, tags=tags)
    d = r * 0.38
    for a, b in ((-d, -d), (-d, d)):
        c.create_line(cx + a, cy + b, cx - a, cy - b, fill=ON_BUTTON, width=1.6, capstyle="round", tags=tags)



def icon_bubble(c, cx, cy, color=None, tags=()):
    color = color or INK
    """对话气泡（历史对话）。"""
    rr(c, cx - 7, cy - 6, cx + 7, cy + 4, 5, "", color, 1.4, tags)
    c.create_line(cx - 3, cy + 4, cx - 5, cy + 8, cx + 1, cy + 4, fill=color, width=1.4,
                  joinstyle="round", tags=tags)


def icon_crop(c, cx, cy, color=None, tags=()):
    color = color or INK
    """截图：四个角的取景框。"""
    kw = dict(fill=color, width=1.6, capstyle="round", joinstyle="round", tags=tags)
    s, k = 7, 4
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = cx + sx * s, cy + sy * s
        c.create_line(x, y - sy * k, x, y, x - sx * k, y, **kw)


def icon_image(c, cx, cy, color=None, tags=()):
    color = color or INK
    rr(c, cx - 7, cy - 6, cx + 7, cy + 6, 2.5, "", color, 1.4, tags)
    c.create_line(cx - 6, cy + 4, cx - 2, cy, cx + 1, cy + 3, cx + 3, cy + 1, cx + 6, cy + 4,
                  fill=color, width=1.4, joinstyle="round", tags=tags)
    c.create_oval(cx + 1.5, cy - 4, cx + 4.5, cy - 1, fill=color, outline="", tags=tags)


def icon_app(c, cx, cy, color=None, tags=()):
    color = color or INK
    """打开完整版：一个窗口 + 右上角往外的箭头。"""
    rr(c, cx - 7, cy - 5, cx + 5, cy + 7, 2.5, "", color, 1.4, tags)
    c.create_line(cx - 1, cy + 1, cx + 7, cy - 7, fill=color, width=1.4, capstyle="round", tags=tags)
    c.create_line(cx + 2, cy - 7, cx + 7, cy - 7, cx + 7, cy - 2, fill=color, width=1.4,
                  capstyle="round", joinstyle="round", tags=tags)


def grab_clipboard_image() -> str | None:
    """把剪贴板里的图片落到工作区 uploads/ 下，返回路径；没有图片返回 None。

    支持三种来源：截图直接进剪贴板（PNG/TIFF）、在 Finder 里 ⌘C 的图片文件。
    """
    try:
        uploads = brain.WORKSPACE / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = uploads / f"img-{stamp}.png"
        tmp = uploads / f"tmp-{stamp}.tiff"
        script = f"""
try
  set d to the clipboard as «class PNGf»
  set f to open for access POSIX file "{out}" with write permission
  set eof f to 0
  write d to f
  close access f
  return "OK"
on error
  try
    set d to the clipboard as «class TIFF»
    set tf to open for access POSIX file "{tmp}" with write permission
    set eof tf to 0
    write d to tf
    close access tf
    do shell script "sips -s format png " & quoted form of "{tmp}" & " --out " & quoted form of "{out}" & " >/dev/null 2>&1"
    return "OK"
  on error
    try
      set p to POSIX path of (the clipboard as «class furl»)
      return "FILE:" & p
    on error
      return "NOIMAGE"
    end try
  end try
end try
"""
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        status = res.stdout.strip()
        if status == "OK" and out.exists() and out.stat().st_size > 0:
            return str(out)
        if status.startswith("FILE:"):
            src = status[5:]
            if src.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".heic", ".webp")):
                conv = subprocess.run(
                    ["sips", "-s", "format", "png", src, "--out", str(out)],
                    capture_output=True, text=True, timeout=20,
                )
                if conv.returncode == 0 and out.exists() and out.stat().st_size > 0:
                    return str(out)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    except Exception:
        pass
    return None


def prune_uploads(keep: int = UPLOADS_KEEP) -> None:
    """启动时清理 uploads/：删掉残留的 tmp-*.tiff，图片只留最新的 keep 张。"""
    try:
        uploads = brain.WORKSPACE / "uploads"
        if not uploads.is_dir():
            return
        for f in uploads.glob("tmp-*.tiff"):
            f.unlink(missing_ok=True)
        imgs = sorted(uploads.glob("img-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in imgs[keep:]:
            f.unlink(missing_ok=True)
    except Exception:
        pass


def plain_text(md: str) -> str:
    """卡片里只有纯文字：去掉 Markdown 记号（**粗体**、`代码`、# 标题、[链接](url)）。"""
    s = md or ""
    s = re.sub(r"```[a-zA-Z]*\n?", "", s)
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", s)
    s = re.sub(r"(?m)^\s*[-*]\s+", "· ", s)
    return s.strip()


def _is_latin(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in "_-'")


def wrap_text(font: tkfont.Font, text: str, width: int, max_lines: int) -> list[str]:
    """按像素宽度逐字折行（中文没有空格，Tk 的 width= 折行对它不可靠且量不出高度）。"""
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        cur = ""
        for ch in para:
            # 避头：标点不放到行首，宁可让这一行略超一点点
            if font.measure(cur + ch) > width and cur and ch not in NO_LINE_START:
                # 英文单词不拆开：退回到这一行最后一个空格处换行（整行都是一个词才硬拆）
                if _is_latin(ch) and _is_latin(cur[-1]):
                    cut = cur.rfind(" ")
                    if cut > 0:
                        lines.append(cur[:cut])
                        cur = cur[cut + 1:] + ch
                        continue
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    lines = [ln for ln in lines if ln.strip()] or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and font.measure(last + "…") > width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


class Task:
    """一张任务卡片 = 一段独立的 dsh 会话。不同卡片可以并行，同一卡片内串行。"""

    _n = 0

    def __init__(self, title: str, session_id: str | None = None) -> None:
        Task._n += 1
        self.id = f"t{int(time.time() * 1000)}-{Task._n}"
        self.title = title          # 用户这句话（运行中显示在卡片标题）
        self.gen_title = ""         # 模型给的【小标题】（完成后显示）
        self.session_id = session_id
        self.status = "done"        # creating | thinking | tool | done | error | stopped
        self.text = ""              # 回复全文（或错误信息）
        self.backlog: list[str] = []
        self.proc = None
        self.stopped = False
        self.reveal: int | None = None   # 打字机效果：已显示的字数；None = 全部显示
        self.expanded = False

    @property
    def running(self) -> bool:
        return self.status in RUNNING

    @property
    def name(self) -> str:
        return self.gen_title or self.title or "小深"

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "gen_title": self.gen_title,
                "session_id": self.session_id, "status": self.status, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        t = cls(d.get("title") or "", d.get("session_id"))
        t.id = d.get("id") or t.id
        t.gen_title = d.get("gen_title") or ""
        t.status = d.get("status") if d.get("status") in ("done", "error", "stopped") else "stopped"
        t.text = d.get("text") or ""
        return t


ACTIONS = [
    ("shot", icon_crop, "截图提问", "框选屏幕上的一块区域发给小深"),
    ("image", icon_image, "图片", "用剪贴板里的图，没有就从文件里选"),
    ("app", icon_app, "DeepSeek Harness", "要改文件、跑命令时，去完整版里做"),
]


def when(ts: float) -> str:
    if not ts:
        return ""
    lt, now = time.localtime(ts), time.localtime()
    if lt.tm_year == now.tm_year and lt.tm_yday == now.tm_yday:
        return time.strftime("%H:%M", lt)
    if time.time() - ts < 2 * 86400 and (now.tm_yday - lt.tm_yday) % 365 == 1:
        return "昨天"
    return f"{lt.tm_mon}月{lt.tm_mday}日"


class Pet:
    def __init__(self, anchor=None, demo: bool = False) -> None:
        self.state = brain.load_state()
        self.messages: list[dict] = list(self.state.get("messages") or [])
        self.tasks: list[Task] = [Task.from_dict(d) for d in self.state.get("tasks") or []]
        # 历史对话：比卡片多、比卡片久（卡片关掉了，历史还在 ⊕ 面板里）
        self.history: list[dict] = list(self.state.get("history") or [])
        for t in self.tasks:
            if not any(h.get("id") == t.id for h in self.history):
                self.history.append({**t.to_dict(), "updated": 0})
        self.cards_hidden = bool(self.state.get("cards_hidden")) and bool(self.tasks)
        self.mode = "pill"              # pill | input
        self.panel_open = False         # ⊕ 面板
        self.panel_rows: list[dict] = []
        self.list_open = False          # 滚轮/双指滑动：把叠着的卡片摊开成列表
        self.list_top = 0               # 摊开时从第几张开始显示
        self._wheel_at = 0.0
        self.reply_to: Task | None = None
        self.attach: str | None = None
        self.hover: str | None = None
        self.phase = 0
        self.zones: list[tuple] = []    # (key, x1, y1, x2, y2)，后加的优先命中
        self.icon_xy: dict[str, tuple] = {}
        self.boxes: dict[str, tuple] = {}   # "card:i" / "item:j" → 外框
        self.entry: tk.Entry | None = None
        self.hint: tk.Label | None = None
        self.hint_win = None
        self.send_xy = None
        self.events: queue.Queue = queue.Queue()   # 后台线程 → UI
        self._drag = None
        self._moved = False
        self._reveal_job = None
        self._modal = 0                 # 弹菜单/文件框/截图时 >0，失焦不算「点了别处」
        self._was_active = True
        self._ticks = 0
        self._move_job = None
        self._btn_prev = False
        self.solid: list[tuple] = []      # 画出来的实体区域（窗口坐标）；其余透明处鼠标穿透
        self._through = False             # 当前是否 ignoresMouseEvents
        self.down = True
        self._win = (PILL_W, BAR_H, 0)  # 上次的 (w, h, bar_y)
        prune_uploads()
        self.skin = apply_skin(chosen_skin())   # 字体要用皮肤里的字体名，所以在建字体之前换装
        self._skin_sig = skin_signature()
        self._sprite_key = ("stale",)
        self._sprite = None
        self._bob_n = 0
        self._bob = 0           # 思考时伙伴上下跳的当前偏移
        self._cw = 0            # 为伙伴在左边多出来的那一列宽度

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("小深")
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparent", True)
            self.root.config(bg=TRANSPARENT)
        except tk.TclError:
            self.root.config(bg="#FFFFFF")

        self.font = tkfont.Font(family=FONT_FAMILY, size=13)
        # 卡片标题：常规字重（用户嫌粗体太粗；Tk 只能选常规/粗体，选不到 PingFang 的 Medium），
        # 靠深色 + 比正文大一号来和灰色正文区分
        self.font_bold = tkfont.Font(family=FONT_FAMILY, size=14)
        self.font_small = tkfont.Font(family=FONT_FAMILY, size=12)
        self.font_tiny = tkfont.Font(family=FONT_FAMILY, size=9, weight="bold")
        self.lh = self.font_small.metrics("linespace")

        self.canvas = tk.Canvas(self.root, width=PILL_W, height=BAR_H, bg=TRANSPARENT,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-2>", self.on_menu)
        self.canvas.bind("<Button-3>", self.on_menu)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="新聊天", command=lambda: self.open_input(None))
        self.menu.add_command(label="收起 / 展开卡片", command=self.toggle_cards)
        self.menu.add_command(label="清空卡片", command=self.clear_tasks)
        self.menu.add_separator()
        self.menu.add_command(label="退出小深", command=self.quit)

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        st = self.state
        if st.get("anchor_tr"):
            ax, ay = st["anchor_tr"]
        elif st.get("anchor"):
            # 旧版（v1）存的是「胶囊窗口右下角」，换算成栏的右上角
            ax, ay = st["anchor"][0], st["anchor"][1] - BAR_H
        else:
            ax, ay = sw - 40, sh - 110 - BAR_H
        if anchor:
            ax, ay = anchor
        self.anchor = [int(ax), int(ay)]

        self.root.bind("<Escape>", lambda e: self.on_escape())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.root.deiconify()
        self.root.update_idletasks()
        make_chromeless(self.root)   # 不要在这之后再设 -topmost：Tk 会把层级改回 3
        self.render()

        if demo:
            self.open_input(None)
            self.entry.insert(0, "今天有点累，陪我聊两句吧")
            self.refresh_send()

    # ================================================================ layout
    @property
    def front(self) -> Task | None:
        return self.tasks[0] if self.tasks else None

    def cards_visible(self) -> bool:
        return bool(self.tasks) and not self.cards_hidden and not self.panel_open

    def _card_text(self, t: Task) -> list[str]:
        if t.running:
            return [STATUS[t.status]]
        if t.status == "stopped" and not t.text:
            return ["已停止"]
        return wrap_text(self.font_small, plain_text(t.text) or "（空）", W - 12 - 32,
                         CARD_LINES_OPEN if t.expanded else CARD_LINES)

    def _card_h(self, t: Task) -> int:
        return max(CARD_MIN_H, 14 + 20 + 4 + len(self._card_text(t)) * self.lh + 12)

    def _blocks(self) -> tuple[list, int]:
        """栏下方（或上方）要放的东西：[(高度, 画法)]，从栏往外排；以及叠放露出的高度。"""
        if self.mode == "input" and self.panel_open:
            self.panel_rows = self._panel_rows()
            return [(self._panel_h(), self._draw_panel)], 0
        if not self.cards_visible():
            return [], 0
        if self.list_open and len(self.tasks) > 1:
            # 摊开：一次最多 LIST_MAX 张，从 list_top 开始；后面还有就在最后一张下面露一截
            top = self.list_top
            shown = self.tasks[top: top + LIST_MAX]
            more = top + LIST_MAX < len(self.tasks)
            blocks = [(self._card_h(t), self._card_drawer(t, top + k, more and k == len(shown) - 1))
                      for k, t in enumerate(shown)]
            return blocks, (STACK if more else 0)
        stacked = len(self.tasks) > 1
        return [(self._card_h(self.front), self._card_drawer(self.front, 0, stacked))], \
            (STACK if stacked else 0)

    def _card_drawer(self, t, i, stacked):
        return lambda x1, y1, x2, y2: self._draw_card(t, i, stacked, x1, y1, x2, y2)

    def render(self) -> None:
        """整窗重画。只在状态变化时调用；动画（声波、打字机、悬停）都是增量更新。"""
        c = self.canvas
        blocks, stack = self._blocks()
        gap = 8
        wide = bool(blocks) or self.mode == "input"
        base = W if wide else PILL_W
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()

        # 伙伴站在栏的左边、脚踩栏的底边。栏左边已经有空地（胶囊 + 卡片时）就不加宽；
        # 否则在窗口左边多加一列。比栏高出来的部分在上面留出 top。
        sp = self.sprite()
        bar_left = 8 if self.mode == "input" else base - 4 - (PILL_W - 8)
        cw = max(0, sp["w"] + 6 + 4 - bar_left) if sp else 0
        top = max(0, sp["h"] - (BAR_H - 4)) if sp else 0
        self._cw = cw
        w = base + cw

        if not blocks:
            bar_y, total = top, top + BAR_H
            self.down = True
        else:
            extra = sum(h for h, _ in blocks) + gap * (len(blocks) - 1) + stack + 4 + 6
            self.down = self.anchor[1] + BAR_H + extra <= sh - 8
            bar_y = top if self.down else max(extra, top)   # 放不下就整体翻到栏上方
            total = bar_y + BAR_H + (extra if self.down else 0)

        x = max(0, min(self.anchor[0] - w, sw - w))
        y = max(0, self.anchor[1] - bar_y)
        self._win = (w, total, bar_y)
        self.root.geometry(f"{w}x{total}+{x}+{y}")
        c.config(width=w, height=total)

        had_focus = self.entry is not None and self.root.focus_get() == self.entry
        c.delete("all")
        self.zones, self.icon_xy, self.boxes, self.solid = [], {}, {}, []
        cur = bar_y + BAR_H + 4 if self.down else bar_y - 4
        for h, draw in blocks:
            if self.down:
                draw(8 + cw, cur, w - 4, cur + h)
                cur += h + gap
            else:
                draw(8 + cw, cur - h, w - 4, cur)
                cur -= h + gap
        if self.mode == "input":
            self._draw_input(bar_y, w)
            if had_focus:
                self.entry.focus_set()
        else:
            self._draw_pill(bar_y, w)
        if sp:
            self._draw_sprite(sp, bar_left + cw - 6 - sp["w"], bar_y + BAR_H - 4 - sp["h"])
        self._draw_hover()

    def sprite(self) -> dict | None:
        cid = chosen_companion()
        path = companion_files().get(cid) if cid != NO_COMPANION else None
        try:
            key = (str(path), path.stat().st_mtime_ns) if path else None
        except OSError:
            key = None
        if key != self._sprite_key:
            self._sprite_key = key
            self._sprite = load_sprite(path) if key else None
        return self._sprite

    def _draw_sprite(self, sp: dict, x0: float, y0: float) -> None:
        c = self.canvas
        self._bob = 0
        for x1, y1, x2, y2, col in sp["runs"]:
            c.create_rectangle(x0 + x1, y0 + y1, x0 + x2, y0 + y2, fill=col, outline="", tags=("buddy",))
        box = (x0, y0, x0 + sp["w"], y0 + sp["h"])
        self.solid.append(box)
        self.zones.append(("buddy", *box))

    def _bob_step(self, running: bool) -> None:
        """思考时伙伴一上一下（每两拍换一次），停下就落回原位。"""
        self._bob_n += 1
        want = (-2 if (self._bob_n // 2) % 2 else 0) if running else 0
        if want != self._bob:
            self.canvas.move("buddy", 0, want - self._bob)
            self._bob = want

    def _place(self) -> None:
        """拖动时只挪窗口，不重画。"""
        w, h, bar_y = self._win
        sw = self.root.winfo_screenwidth()
        x = max(0, min(self.anchor[0] - w, sw - w))
        y = max(0, self.anchor[1] - bar_y)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------ pill
    def _draw_pill(self, by: int, w: int) -> None:
        c = self.canvas
        x2 = w - 4
        x1 = x2 - (PILL_W - 8)
        y1, y2 = by + 4, by + BAR_H - 4
        mid = (y1 + y2) / 2
        # 图标中心：20 / 60 / 101，分隔线在 41 / 81（照 ChatGPT 桌面助手的比例量的）
        ex, wx, bx = x1 + 21, x1 + 61, x1 + 101
        rr(c, x1, y1, x2, y2, bar_r(y2 - y1), CARD, BORDER, 1, ("pill",))
        self.solid.append((x1, y1, x2, y2))
        icon_edit(c, ex, mid, 12, INK, tags=("pill", "icon"))
        c.create_line(x1 + 41, mid - 7, x1 + 41, mid + 7, fill=BORDER, width=1, tags=("pill",))
        self.icon_xy["wave"] = (wx, mid)
        self._draw_wave()
        c.create_line(x1 + 81, mid - 7, x1 + 81, mid + 7, fill=BORDER, width=1, tags=("pill",))
        if self.tasks and self.cards_hidden:
            icon_bell(c, bx, mid, INK, tags=("pill", "icon"))
            badge_count(c, bx + 6, mid - 7, len(self.tasks), self.font_tiny, tags=("pill", "icon"))
        else:
            icon_chevron(c, bx, mid, 5, MUTED if not self.tasks else INK,
                         tags=("pill", "icon"), up=True)
        self.icon_xy["edit"] = (ex, mid)
        self.icon_xy["chev"] = (bx, mid)
        self.zones += [("edit", x1, y1, x1 + 41, y2), ("wave", x1 + 41, y1, x1 + 81, y2),
                       ("chev", x1 + 81, y1, x2, y2)]

    def _draw_wave(self) -> None:
        if self.mode != "pill" or "wave" not in self.icon_xy:
            return
        self.canvas.delete("wave")
        busy = any(t.running for t in self.tasks)
        cx, cy = self.icon_xy["wave"]
        icon_wave(self.canvas, cx, cy, 11, INK, tags=("wave", "icon"),
                  phase=self.phase if busy else 0)

    # ----------------------------------------------------------------- input
    def _draw_input(self, by: int, w: int) -> None:
        c = self.canvas
        x1, x2 = 8 + self._cw, w - 4
        y1, y2 = by + 4, by + BAR_H - 4
        cy = (y1 + y2) / 2
        rr(c, x1, y1, x2, y2, bar_r(y2 - y1), CARD, BORDER, 1, ("input",))
        self.solid.append((x1, y1, x2, y2))
        c.create_oval(x1 + 6, cy - 11, x1 + 28, cy + 11, fill=HOVER if self.panel_open else CHIP,
                      outline="", tags=("input",))
        icon_plus(c, x1 + 17, cy, 5, INK, tags=("input",))
        self.zones.append(("plus", x1, y1, x1 + 34, y2))

        left = x1 + 38
        if self.attach:
            chip_w = 72
            rr(c, left, cy - 10, left + chip_w, cy + 10, 10, CHIP, "", 0, ("input",))
            c.create_text(left + 26, cy, text="🖼 图片", font=self.font_small, fill=INK)
            c.create_text(left + chip_w - 13, cy, text="×", font=self.font_small, fill=MUTED)
            self.zones.append(("attachx", left + chip_w - 26, y1, left + chip_w, y2))
            left += chip_w + 8

        ew = x2 - 40 - left
        c.create_window(left, cy, anchor="w", window=self.entry, width=ew, height=22)
        if self.panel_open:
            hint = "搜索历史对话，或直接输入"
        elif self.reply_to is not None and self.reply_to in self.tasks:
            hint = wrap_text(self.font, f"回复「{self.reply_to.name}」", ew - 10, 1)[0]
        else:
            hint = "开始新聊天"
        self.hint.config(text=hint)
        self.hint_win = c.create_window(left + 2, cy, anchor="w", window=self.hint,
                                        width=ew - 4, height=22)
        self.send_xy = (x2 - 18, cy)
        self.zones.append(("send", x2 - 36, y1, x2, y2))
        self.refresh_send()

    def open_input(self, task: Task | None) -> None:
        if self.mode == "input" and self.reply_to is task:
            self._focus_force()
            return
        self.mode = "input"
        self.reply_to = task
        self.attach = None
        self.panel_open = False
        if self.entry is None:
            self.entry = tk.Entry(self.canvas, font=self.font, bg=CARD, relief="flat", bd=0,
                                  highlightthickness=0, insertbackground=INK, fg=INK)
            self.entry.bind("<KeyRelease>", self.on_key)
            self.entry.bind("<Return>", lambda e: self.on_return())
            self.entry.bind("<Escape>", lambda e: (self.on_escape(), "break")[1])
            self.entry.bind("<Down>", lambda e: (self.move_sel(1), "break")[1])
            self.entry.bind("<Up>", lambda e: (self.move_sel(-1), "break")[1])
            self.entry.bind("<Command-v>", self.on_paste)
            self.hint = tk.Label(self.canvas, font=self.font, bg=CARD, fg=PLACEHOLDER,
                                 anchor="w", padx=2)
            self.hint.bind("<Button-1>", lambda e: self._focus_force())
        self.render()
        for delay in (60, 220, 500):
            self.root.after(delay, self._focus_force)

    def close_input(self) -> None:
        if self.mode != "input":
            return
        self.mode = "pill"
        self.reply_to = None
        self.attach = None
        self.panel_open = False
        for wdg in (self.entry, self.hint):
            if wdg is not None:
                try:
                    wdg.destroy()
                except tk.TclError:
                    pass
        self.entry = self.hint = self.hint_win = None
        self.render()

    def on_key(self, event=None) -> None:
        if event is not None and event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        if self.panel_open:
            self.hover = None
            self.render()      # 打字 = 过滤面板
        else:
            self.refresh_send()

    def on_return(self) -> None:
        if self.panel_open and self.hover and self.hover.startswith("item:"):
            self.pick(int(self.hover.split(":")[1]))
        else:
            self.send()

    def on_escape(self) -> None:
        if self.panel_open:
            self.panel_open = False
            self.render()
        elif self.mode == "input":
            self.close_input()
        elif self.cards_visible():
            self.toggle_cards()

    def refresh_send(self) -> None:
        if self.mode != "input" or self.entry is None or self.send_xy is None:
            return
        has = bool(self.entry.get().strip() or self.attach)
        if self.hint_win:
            try:
                self.canvas.itemconfig(self.hint_win, state="hidden" if self.entry.get() else "normal")
            except tk.TclError:
                pass
        self.canvas.delete("send")
        icon_send(self.canvas, *self.send_xy, 12, has, tags=("send",))

    def _focus_force(self) -> None:
        if self.mode != "input" or self.entry is None:
            return
        try:
            self.root.focus_force()
            self.entry.focus_set()
            self.entry.focus_force()
        except tk.TclError:
            pass

    # ----------------------------------------------------------- ⊕ panel
    def _panel_rows(self) -> list[dict]:
        q = (self.entry.get().strip().lower() if self.entry is not None else "")
        rows: list[dict] = []
        acts = [a for a in ACTIONS if not q or q in a[2].lower() or q in a[3].lower()]
        if acts:
            rows.append({"kind": "head", "text": "功能"})
            rows += [{"kind": "action", "key": k, "icon": ic, "name": n, "desc": d, "meta": ""}
                     for k, ic, n, d in acts]
        hist = sorted(self.history, key=lambda h: h.get("updated") or 0, reverse=True)
        if q:
            hist = [h for h in hist if q in (h.get("gen_title", "") + h.get("title", "")
                                              + h.get("text", "")).lower()]
        rows.append({"kind": "head", "text": "历史对话"})
        if not hist:
            rows.append({"kind": "note", "text": "没有找到相关对话" if q else "还没有聊过天"})
        for h in hist[:8 if q else 6]:
            rows.append({"kind": "history", "h": h, "icon": icon_bubble,
                         "name": h.get("gen_title") or h.get("title") or "对话",
                         "desc": "", "meta": when(h.get("updated") or 0)})
        return rows

    def _row_h(self, r: dict) -> int:
        return 30 if r["kind"] in ("head", "note") else 34

    def _panel_h(self) -> int:
        return 8 + sum(self._row_h(r) for r in self.panel_rows) + 8

    def _draw_panel(self, x1, y1, x2, y2) -> None:
        c = self.canvas
        self._panel_bg = rr(c, x1, y1, x2, y2, PANEL_R, CARD, BORDER, 1, ("panel",))
        self.solid.append((x1, y1, x2, y2))
        y = y1 + 8
        for j, r in enumerate(self.panel_rows):
            h = self._row_h(r)
            cy = y + h / 2
            if r["kind"] == "head":
                c.create_text(x1 + 18, cy + 2, text=r["text"], anchor="w", font=self.font_small,
                              fill=MUTED, tags=("panel",))
            elif r["kind"] == "note":
                c.create_text(x1 + 18, cy, text=r["text"], anchor="w", font=self.font_small,
                              fill=PLACEHOLDER, tags=("panel",))
            else:
                self.boxes[f"item:{j}"] = (x1 + 6, y + 1, x2 - 6, y + h - 1)
                self.zones.append((f"item:{j}", x1, y, x2, y + h))
                r["icon"](c, x1 + 26, cy, INK, tags=("panel",))
                name_w = int((x2 - x1) * 0.55)   # 名字最多占一半多一点，剩下给说明/时间
                c.create_text(x1 + 44, cy, text=wrap_text(self.font, r["name"], name_w, 1)[0],
                              anchor="w", font=self.font, fill=INK, tags=("panel", "pname"))
                right = x2 - 16
                if r["meta"]:
                    c.create_text(right, cy, text=r["meta"], anchor="e", font=self.font_small,
                                  fill=PLACEHOLDER, tags=("panel",))
                    right -= self.font_small.measure(r["meta"]) + 12
                if r["desc"]:
                    nx = x1 + 44 + min(name_w, self.font.measure(r["name"])) + 10
                    room = right - nx
                    if room > 30:
                        c.create_text(nx, cy, text=wrap_text(self.font_small, r["desc"], room, 1)[0],
                                      anchor="w", font=self.font_small, fill=PLACEHOLDER,
                                      tags=("panel",))
            y += h

    def move_sel(self, d: int) -> None:
        if not self.panel_open:
            return
        items = [j for j, r in enumerate(self.panel_rows) if r["kind"] in ("action", "history")]
        if not items:
            return
        cur = int(self.hover.split(":")[1]) if self.hover and self.hover.startswith("item:") else None
        if cur not in items:
            nxt = items[0] if d > 0 else items[-1]
        else:
            nxt = items[(items.index(cur) + d) % len(items)]
        self.hover = f"item:{nxt}"
        self._draw_hover()

    def pick(self, j: int) -> None:
        if not (0 <= j < len(self.panel_rows)):
            return
        r = self.panel_rows[j]
        self.panel_open = False
        self.hover = None
        if r["kind"] == "action":
            if r["key"] == "shot":
                self.render()
                self.take_screenshot()
            elif r["key"] == "image":
                self.render()
                self.pick_image()
            elif r["key"] == "app":
                subprocess.Popen(["open", "-a", "DeepSeek Harness"])
                self.collapse()
        elif r["kind"] == "history":
            h = r["h"]
            t = next((x for x in self.tasks if x.id == h.get("id")), None)
            if t is None:
                t = Task.from_dict(h)
                self.tasks.insert(0, t)
                self._trim_tasks()
            else:
                self.tasks.remove(t)
                self.tasks.insert(0, t)
            self.cards_hidden = False
            if self.entry is not None:
                self.entry.delete(0, "end")
            self.reply_to = None
            self.open_input(t)   # 「回复『xxx』」，卡片在下面
            self.save()

    # ------------------------------------------------------------- images
    def on_paste(self, _event=None):
        """⌘V：剪贴板里是图片就挂到这条消息上，否则走默认的文字粘贴。"""
        path = grab_clipboard_image()
        if not path:
            return None
        self._set_attach(path)
        return "break"

    def pick_image(self) -> None:
        """先看剪贴板有没有图，没有就弹文件选择框。"""
        path = grab_clipboard_image()
        if not path:
            from tkinter import filedialog
            self._modal += 1
            try:
                src = filedialog.askopenfilename(
                    parent=self.root, title="选一张图片给小深看",
                    filetypes=[("图片", "*.png *.jpg *.jpeg *.heic *.webp *.tif *.tiff *.gif")])
            finally:
                self._modal -= 1
            if not src:
                self._focus_force()
                return
            out = self._upload_path()
            r = subprocess.run(["sips", "-s", "format", "png", src, "--out", str(out)],
                               capture_output=True, timeout=20)
            if r.returncode != 0 or not out.exists():
                self._focus_force()
                return
            path = str(out)
        self._set_attach(path)

    def _upload_path(self):
        uploads = brain.WORKSPACE / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        return uploads / f"img-{time.strftime('%Y%m%d-%H%M%S')}.png"

    def take_screenshot(self) -> None:
        """系统的框选截图（和 ⌘⇧4 一样），截完挂到输入栏上。小深先藏起来免得挡住。"""
        out = self._upload_path()
        self._modal += 1
        self.root.withdraw()

        def run():
            try:
                subprocess.run(["screencapture", "-i", "-x", str(out)], timeout=120)
            except Exception:
                pass
            self.events.put((None, "shot", str(out) if out.exists() and out.stat().st_size else None))

        threading.Thread(target=run, daemon=True).start()

    def _on_drop(self, kind: str, path: str) -> None:
        """图片拖进来了：统一转成 uploads/ 里的 PNG，挂到输入栏上（没开输入栏就打开）。"""
        src = Path(path)
        if kind == "file" and src.suffix.lower() not in IMAGE_EXTS:
            return  # 只收图片；别的文件拖进来不理
        out = src
        if kind == "file" or src.suffix.lower() != ".png":
            out = self._upload_path()
            r = subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(out)],
                               capture_output=True, timeout=20)
            if kind == "data":
                src.unlink(missing_ok=True)
            if r.returncode != 0 or not out.exists():
                return
        if self.mode != "input":
            self.open_input(self.front if self.cards_visible() else None)
        self.panel_open = False
        self._set_attach(str(out))

    def _set_attach(self, path: str | None) -> None:
        self.attach = path
        self.render()
        self.root.after(80, self._focus_force)

    # ------------------------------------------------------------------ card
    def _draw_card(self, t: Task, i: int, stacked: bool, x1, y1, x2, y2) -> None:
        c = self.canvas
        if stacked:  # 后面还有卡片：露出一截（鼠标放上来就摊开）
            if self.down:
                box = (x1 + 14, y2 - 12, x2 - 14, y2 + STACK)
            else:
                box = (x1 + 14, y1 - STACK, x2 - 14, y1 + 12)
            rr(c, *box, 12, STACK_FILL, BORDER, 1, ("card",))
            self.zones.append(("stack", *box))
            self.solid.append(box)
        rr(c, x1, y1, x2, y2, min(CARD_R, (y2 - y1) / 2), CARD, BORDER, 1, ("card",))
        self.boxes[f"card:{i}"] = (x1, y1, x2, y2)
        self.solid.append((x1 - 6, y1 - 6, x2, y2))   # 含左上角 × 按钮探出去的那一块
        self.zones.append((f"card:{i}", x1, y1, x2, y2))

        revealing = t.reveal is not None
        tx = x1 + 16
        ty = y1 + 14 + 10
        if t.status == "error":   # 完成的卡片不再画 ✅（用户要求去掉），出错仍然标红
            badge_error(c, tx + 8, ty, 8, self.font_tiny, tags=("card",))
            tx += 22
        title = t.name if (t.status == "done" and not revealing) else (t.title or "小深")
        title = wrap_text(self.font_bold, title.replace("\n", " "), x2 - 16 - tx, 1)[0]
        c.create_text(tx, ty, text=title, anchor="w", font=self.font_bold, fill=INK, tags=("card",))

        full = "\n".join(self._card_text(t))
        shown = full[: t.reveal] if revealing else full
        color = ERR if t.status == "error" else MUTED
        tags = ("card", f"cardtext:{t.id}") + ((f"status:{t.id}",) if t.running else ())
        c.create_text(x1 + 16, y1 + 14 + 20 + 4, text=shown, anchor="nw",
                      font=self.font_small, fill=color, tags=tags)

        cy = (y1 + y2) / 2
        self.zones.append((f"close:{i}", x1 - 4, y1 - 4, x1 + 16, y1 + 16))
        if t.running:
            self.zones += [(f"stop:{i}", x2 - 42, cy - 16, x2 - 10, cy + 16),
                           (f"reply:{i}", x2 - 78, cy - 16, x2 - 46, cy + 16)]
        else:
            self.zones.append((f"reply:{i}", x2 - 42, cy - 16, x2 - 10, cy + 16))

    # ----------------------------------------------------------------- hover
    def _draw_hover(self) -> None:
        c = self.canvas
        c.delete("hov")
        key = self.hover
        if not key:
            return
        kind, _, idx = key.partition(":")
        if key in self.icon_xy and self.mode == "pill":
            cx, cy = self.icon_xy[key]
            c.create_oval(cx - 14, cy - 14, cx + 14, cy + 14, fill=HOVER, outline="", tags=("hov",))
            c.tag_lower("hov", "icon")
        elif kind == "item" and key in self.boxes:
            rr(c, *self.boxes[key], 10, HOVER, "", 0, ("hov",))
            c.tag_raise("hov", self._panel_bg)   # 只压在面板底色上面，图标文字仍在最上
        elif kind in ("card", "close", "reply", "stop") and f"card:{idx}" in self.boxes:
            i = int(idx)
            if i >= len(self.tasks):
                return
            t = self.tasks[i]
            x1, y1, x2, y2 = self.boxes[f"card:{idx}"]
            cy = (y1 + y2) / 2
            n = 2 if t.running else 1
            # 按钮后面垫一块白，免得压在回复文字上
            c.create_rectangle(x2 - 10 - 36 * n - 6, cy - 17, x2 - 10, cy + 17,
                               fill=CARD, outline="", tags=("hov",))
            rx = x2 - 62 if t.running else x2 - 26
            c.create_oval(rx - 15, cy - 15, rx + 15, cy + 15,
                          fill=HOVER_STRONG if kind == "reply" else HOVER, outline="", tags=("hov",))
            icon_return(c, rx, cy, INK, tags=("hov",))
            if t.running:
                icon_stop(c, x2 - 26, cy, 15, tags=("hov",))
            btn_close(c, x1 + 5, y1 + 5, 9, tags=("hov",))

    def on_motion(self, event) -> None:
        key = self.hit(event.x, event.y)
        if key == self.hover:
            return
        self.hover = key
        kind = (key or "").partition(":")[0]
        self._draw_hover()   # 悬停不再摊开卡片（用户要求默认叠着，用滚轮/双指滑动才展开）

    def on_wheel(self, event) -> None:
        """滚轮 / 触控板双指滑动：叠着时先摊开，摊开后一格一张地翻。

        触控板一次滑动会连发很多小 delta，鼠标滚轮一格可能只有 ±1，
        两者的量级差很多，所以不按 delta 累加，而是「每 120ms 最多翻一张」：
        滚轮每格翻一张，双指滑得越久翻得越多。
        """
        if not self.cards_visible() or len(self.tasks) < 2:
            return
        now = time.monotonic()
        if now - self._wheel_at < 0.12:
            return
        self._wheel_at = now
        if not self.list_open:
            self.list_open, self.list_top = True, 0
        else:
            step = 1 if event.delta < 0 else -1   # 手指往上推 / 滚轮往下 → 看后面的卡片
            self.list_top = max(0, min(len(self.tasks) - min(len(self.tasks), LIST_MAX),
                                       self.list_top + step))
        self.hover = None
        self.render()

    def on_leave(self, _event=None) -> None:
        if self._through:
            inside = False   # 从 hover_poll 调过来：鼠标在透明处，算离开
        else:
            inside = self._pointer_in_widget()
        if inside:
            return
        self.hover = None
        if self.list_open:
            self.list_open = False
            self.render()
        else:
            self._draw_hover()

    def _pointer_in_widget(self) -> bool:
        # 鼠标钻进 Entry 也会触发 Leave，那不算离开窗口
        try:
            px, py = self.root.winfo_pointerxy()
            inside = self.root.winfo_containing(px, py) is not None and \
                str(self.root.winfo_containing(px, py)).startswith(str(self.root))
        except (tk.TclError, KeyError):
            inside = False
        return inside

    # ----------------------------------------------------------- interaction
    def hit(self, x: int, y: int) -> str | None:
        for key, x1, y1, x2, y2 in reversed(self.zones):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return key
        return None

    # 拖动：为什么不用 event.x_root
    # macOS 上 Tk 的 x_root = 事件在窗口内的坐标 + 窗口「当前」原点。窗口一动，队列里
    # 还没处理的旧事件会按新原点换算 → 算出的位置来回过冲 → 窗口乱抖（正反馈）。
    # 改成每次直接问系统要鼠标的屏幕坐标（winfo_pointerxy 就是 [NSEvent mouseLocation]，
    # 和窗口在哪无关），并且把移动合并到空闲时做，一次空闲最多挪一次窗口。
    def on_press(self, event) -> None:
        px, py = self.root.winfo_pointerxy()
        self._drag = (px, py, self.anchor[0], self.anchor[1])
        self._moved = False
        self._set_click_through(False)
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def on_drag(self, _event=None) -> None:
        if self._drag is None or self._move_job is not None:
            return
        self._move_job = self.root.after_idle(self._drag_step)

    def _drag_step(self) -> None:
        self._move_job = None
        if self._drag is None:
            return
        px, py = self.root.winfo_pointerxy()
        dx, dy = px - self._drag[0], py - self._drag[1]
        if not self._moved and (abs(dx) > 4 or abs(dy) > 4):
            self._moved = True
        if self._moved:
            target = [self._drag[2] + dx, self._drag[3] + dy]
            if target != self.anchor:
                self.anchor = target
                self._place()

    def on_release(self, event) -> None:
        if self._move_job is not None:
            self.root.after_cancel(self._move_job)
            self._move_job = None
        if self._drag is not None and self._moved:
            self._drag_step()   # 松手那一刻的位置
        moved, self._drag = self._moved, None
        if moved:
            self.render()  # 换了位置，卡片可能要翻面
            self.save()
            return
        key = self.hit(event.x, event.y)
        kind, _, idx = (key or "").partition(":")
        t = self.tasks[int(idx)] if idx.isdigit() and int(idx) < len(self.tasks) else self.front
        if key in ("edit", "buddy"):
            self.open_input(None)
        elif key == "wave":
            self.open_input(self.front if self.front and not self.cards_hidden else None)
        elif key == "chev":
            self.toggle_cards()
        elif key == "plus":
            self.panel_open = not self.panel_open
            self.hover = None
            self.render()
            self._focus_force()
        elif key == "attachx":
            self._set_attach(None)
        elif key == "send":
            self.send()
        elif kind == "item":
            self.pick(int(idx))
        elif kind == "card" and t:
            t.expanded = not t.expanded
            self.render()
        elif kind == "close" and t:
            self.dismiss(t)
        elif kind == "reply" and t:
            self.tasks.remove(t)
            self.tasks.insert(0, t)
            self.list_open = False
            self.open_input(t)
        elif kind == "stop" and t:
            self.stop(t)

    def on_menu(self, event) -> None:
        self._modal += 1
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
            self.root.after(300, self._end_modal)

    def _end_modal(self) -> None:
        self._modal = max(0, self._modal - 1)

    def toggle_cards(self) -> None:
        if not self.tasks:
            return
        self.cards_hidden = not self.cards_hidden
        self.list_open = False
        if self.cards_hidden:
            self._finish_reveal()
        self.render()
        self.save()

    def collapse(self) -> None:
        """点了空白处（小深失去激活）：收回到初始的胶囊，卡片收进铃铛。"""
        self.panel_open = False
        self.list_open = False
        self.hover = None
        if self.tasks:
            self.cards_hidden = True
            self._finish_reveal()
        if self.mode == "input":
            self.close_input()     # 里面会 render
        else:
            self.render()
        self.save()

    def dismiss(self, t: Task) -> None:
        if t.running:
            self.stop(t)
        if t in self.tasks:
            self.tasks.remove(t)
        if self.reply_to is t:
            self.reply_to = None
        if len(self.tasks) <= 1:
            self.list_open = False
        if not self.tasks:
            self.cards_hidden = False
        self.hover = None
        self.render()
        self.save()

    def clear_tasks(self) -> None:
        for t in list(self.tasks):
            if t.running:
                self.stop(t)
        self.tasks = []
        self.cards_hidden = False
        self.list_open = False
        self.reply_to = None
        self.render()
        self.save()

    def _trim_tasks(self) -> None:
        done = [x for x in self.tasks if not x.running]
        while len(self.tasks) > TASKS_KEEP and done:
            self.tasks.remove(done.pop())

    def _remember(self, t: Task) -> None:
        """把这张卡片写进历史对话（按 id 覆盖），最多留 HISTORY_KEEP 条。"""
        rec = {**t.to_dict(), "updated": time.time()}
        self.history = [h for h in self.history if h.get("id") != t.id]
        self.history.insert(0, rec)
        del self.history[HISTORY_KEEP:]

    # ----------------------------------------------------------------- brain
    def send(self) -> None:
        if self.mode != "input" or self.entry is None:
            return
        text = self.entry.get().strip()
        if not text and not self.attach:
            self._focus_force()
            return
        shown = text or "（发了张图片）"
        payload = text
        if self.attach:
            payload = (text + "\n\n" if text else "") + f"[图片: {self.attach}]"
        t = self.reply_to if self.reply_to in self.tasks else None
        if t is None:
            t = Task(shown)
            self.tasks.insert(0, t)
            self._trim_tasks()
        else:
            self.tasks.remove(t)
            self.tasks.insert(0, t)
            t.title = shown
        self.messages.append({"role": "user", "task": t.id, "text": shown})
        self._finish_reveal()
        if t.running:
            t.backlog.append(payload)   # 同一张卡片里：排队，按顺序问
        else:
            self._start(t, payload)
        self.cards_hidden = False
        self.list_open = False
        self.close_input()
        self.save()

    def _start(self, t: Task, payload: str) -> None:
        t.status = "thinking" if t.session_id else "creating"
        t.stopped = False
        t.gen_title = ""
        t.text = ""
        t.reveal = None
        t.expanded = False
        threading.Thread(target=self._run, args=(t, payload), daemon=True).start()

    def _run(self, t: Task, payload: str) -> None:
        def on_proc(p):
            t.proc = p
            if t.stopped:  # 在进程起来之前就点了停止
                p.kill()
        res = brain.ask(payload, t.session_id,
                        on_event=lambda ev: self.events.put((t, "ev", ev)),
                        on_proc=on_proc)
        self.events.put((t, "done", res))

    def stop(self, t: Task) -> None:
        t.stopped = True
        t.backlog.clear()
        p = t.proc
        if p is not None:
            try:
                p.kill()
            except Exception:
                pass

    def poll(self) -> None:
        dirty = False
        try:
            while DROPS:
                self._on_drop(*DROPS.pop(0))
            while True:
                t, kind, data = self.events.get_nowait()
                if kind == "shot":
                    self.root.deiconify()
                    self.root.update_idletasks()
                    make_chromeless(self.root)
                    self._end_modal()
                    if self.mode != "input":
                        self.open_input(self.reply_to)
                    if data:
                        self._set_attach(data)
                    else:
                        dirty = True
                    continue
                if kind == "ev":
                    typ = str(data.get("type") or "")
                    before = t.status
                    if typ == "session" and data.get("sessionId"):
                        t.session_id = data["sessionId"]
                    if t.running and not t.stopped:
                        if "tool" in typ:
                            t.status = "tool"
                        elif typ in ("thinking", "text") or data.get("phase") == "turn_start":
                            t.status = "thinking"
                    dirty |= t.status != before
                    continue
                # done
                t.proc = None
                t.session_id = data.get("session_id") or t.session_id
                if t.stopped:
                    t.status, t.text = "stopped", "已停止"
                elif data.get("error"):
                    t.status, t.text = "error", data["error"]
                else:
                    t.status = "done"
                    t.text = data.get("reply") or "唔，我没想出怎么回你。"
                    t.gen_title = data.get("title") or ""
                self.messages.append({"role": "pet", "task": t.id, "text": t.text})
                self._remember(t)
                if t.backlog and t in self.tasks:
                    self._start(t, t.backlog.pop(0))
                elif t is self.front and self.cards_visible() and t.status == "done":
                    t.reveal = 0
                    self._reveal_step()
                dirty = True
                self.save()
        except queue.Empty:
            pass
        if dirty:
            self.render()
        self.root.after(150, self.poll)

    # --------------------------------------------------------- typewriter
    def _reveal_step(self) -> None:
        self._reveal_job = None
        t = self.front
        if t is None or t.reveal is None:
            return
        full = "\n".join(self._card_text(t))
        t.reveal += max(1, len(full) // 40)
        if t.reveal >= len(full):
            t.reveal = None
            self.render()  # 打完字：换成 ✅ + 小标题
            return
        try:
            self.canvas.itemconfig(f"cardtext:{t.id}", text=full[: t.reveal])
        except tk.TclError:
            pass
        self._reveal_job = self.root.after(25, self._reveal_step)

    def _finish_reveal(self) -> None:
        for t in self.tasks:
            t.reveal = None
        if self._reveal_job is not None:
            try:
                self.root.after_cancel(self._reveal_job)
            except tk.TclError:
                pass
            self._reveal_job = None

    # ------------------------------------------------------- click-through
    def _set_click_through(self, on: bool) -> None:
        if on == self._through:
            return
        self._through = on
        try:
            o = objc()
            for w in o.windows():
                o.send(None, w, "setIgnoresMouseEvents:", on, argtypes=[o.c.c_bool])
        except Exception:
            pass

    def hover_poll(self) -> None:
        """窗口里没画东西的透明处让鼠标穿透到下面的 App（参考 whale-mate 的逐像素命中）。

        穿透时 Tk 收不到任何鼠标事件，所以用定时器直接问系统鼠标在哪，回到实体区域
        就立刻关掉穿透。拖动中、弹菜单/文件框时不穿透。
        """
        try:
            px, py = self.root.winfo_pointerxy()
            lx, ly = px - self.root.winfo_rootx(), py - self.root.winfo_rooty()
            w, h, _ = self._win
            in_win = 0 <= lx < w and 0 <= ly < h
            solid = in_win and any(x1 <= lx <= x2 and y1 <= ly <= y2
                                   for x1, y1, x2, y2 in self.solid)
            if self._drag is not None or self._modal:
                self._set_click_through(False)
            elif in_win:
                self._set_click_through(not solid)
                if not solid and (self.hover or self.list_open):
                    self.on_leave()   # 穿透后收不到 <Leave>，在这里补上
            else:
                self._set_click_through(False)
            self._watch_outside_click(solid)
        except tk.TclError:
            pass
        self.root.after(40, self.hover_poll)

    def _check_skin(self) -> None:
        """桌面助手页面换了皮肤，或者设计者改了皮肤 JSON：换装、改字体、整窗重画。"""
        sig = skin_signature()
        if sig == self._skin_sig:
            return
        self._skin_sig = sig
        self.skin = apply_skin(sig[0])
        self._sprite_key = ("stale",)   # 不能用 None：None 本身表示「没有伙伴」
        for f in (self.font, self.font_bold, self.font_small, self.font_tiny):
            f.configure(family=FONT_FAMILY)
        if self.entry is not None:
            self.entry.config(bg=CARD, fg=INK, insertbackground=INK)
        if self.hint is not None:
            self.hint.config(bg=CARD, fg=PLACEHOLDER)
        self.render()

    def _watch_outside_click(self, on_pet: bool) -> None:
        """点空白处收回（第十三轮重写）。

        旧做法是看小深是否从「当前 App」变成「不是」：如果用户根本没点过小深
        （只是悬停、或者回复是在别的 App 里到的），它从来不是当前 App，点别处就毫无反应；
        而且每 260ms 才查一次。现在直接看系统全局的鼠标按键状态
        [NSEvent pressedMouseButtons]（不需要任何权限，别的 App 里的点击也算），
        在「按下」那一下、且鼠标不在小深身上，就收回。40ms 内生效。
        """
        try:
            o = objc()
            pressed = bool(o.send(o.c.c_ulong, o.cls("NSEvent"), "pressedMouseButtons") & 0b11)
        except Exception:
            return
        if pressed and not self._btn_prev and not on_pet and not self._modal and self._drag is None:
            if self.mode == "input" or self.cards_visible() or self.list_open:
                self.collapse()
        self._btn_prev = pressed

    # ---------------------------------------------------------------- tick
    def tick(self) -> None:
        self._ticks += 1
        if self._ticks % 8 == 0:
            keep_floating()   # 偶尔有东西（Tk 的 -topmost、deiconify）会把层级改回去
        if self._ticks % 4 == 0:
            self._check_skin()
        # 点空白处收回：小深从「当前 App」变成「不是」的那一下
        active = app_is_active()
        if active is not None:
            if self._was_active and not active and not self._modal:
                if self.mode == "input" or self.cards_visible() or self.list_open:
                    self.collapse()
            self._was_active = active
        running = any(t.running for t in self.tasks)
        try:
            self._bob_step(running)
        except tk.TclError:
            pass
        if running:
            self.phase = (self.phase + 1) % 5
            try:
                self._draw_wave()
                for t in self.tasks:
                    if t.running:
                        self.canvas.itemconfig(f"status:{t.id}",
                                               text=STATUS[t.status] + "." * (self.phase % 4))
            except tk.TclError:
                pass
        self.root.after(260, self.tick)

    # ---------------------------------------------------------------- save
    def save(self) -> None:
        st = brain.load_state()
        st.pop("anchor", None)       # v1 字段，已迁移到 anchor_tr
        st.pop("session_id", None)   # v1 单会话，现在每张卡片各有 session_id
        st.update({
            "version": 2,
            "anchor_tr": self.anchor,
            "cards_hidden": self.cards_hidden,
            "tasks": [t.to_dict() for t in self.tasks if not t.running],
            "history": self.history[:HISTORY_KEEP],
            "messages": self.messages[-40:],
        })
        brain.save_state(st)

    def quit(self) -> None:
        for t in self.tasks:
            if t.running:
                self.stop(t)
                t.status = "stopped"   # 退出时还在想的那张卡片：存成「已停止」，下次打开还在
                self._remember(t)
        self.save()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def cli() -> None:
    print("小深 · 终端模式（输入 /new 开新对话，/q 退出）")
    st = brain.load_state()
    sid = st.get("session_id")
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("/q", "/quit", "exit"):
            break
        if text == "/new":
            brain.new_session()
            sid = None
            print("小深 > 好呀，重新开始～")
            continue
        res = brain.ask(text, sid)
        sid = res.get("session_id") or sid
        st["session_id"] = sid
        brain.save_state(st)
        print("小深 >", res.get("reply") or res.get("error"))


def single_instance():
    """同一时间只允许一只小深（run.command 和 /pet 可能各开一个）。

    用 flock 而不是 pid 文件：进程不管怎么死的（包括 kill -9），锁都会被系统释放，
    不会出现「残留 pid 文件导致再也打不开」。返回的文件对象要一直拿着。
    """
    import fcntl
    try:
        brain.APP_HOME.mkdir(parents=True, exist_ok=True)
        fh = open(brain.APP_HOME / "pet.lock", "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid()))
        fh.flush()
        return fh
    except BlockingIOError:
        return None
    except OSError:
        return True   # 锁文件都建不了时不拦着，照常启动


def main() -> None:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(
            "小深 · 桌面小精灵\n"
            "  python3 pet.py            打开\n"
            "  python3 pet.py --cli      终端里聊\n"
            "  --pos x,y                 指定出现位置\n"
        )
        return
    if "--cli" in args:
        cli()
        return
    anchor = None
    if "--pos" in args:
        try:
            anchor = [int(v) for v in args[args.index("--pos") + 1].split(",")]
        except (IndexError, ValueError):
            anchor = None
    lock = single_instance()
    if lock is None:
        print("小深已经在桌面上了（另一个进程拿着 ~/.dsh-pet/pet.lock）。")
        return
    pet = Pet(anchor=anchor, demo="--demo" in args)
    # /pet close 发的是 SIGTERM：停掉还在跑的 dsh、保存，再退出（不然会留下孤儿 dsh 进程）。
    # Python 的信号处理只在解释器跑 Python 代码时执行；tick 每 260ms 跑一次，足够及时。
    signal.signal(signal.SIGTERM, lambda *_: pet.root.after(0, pet.quit))
    signal.signal(signal.SIGHUP, signal.SIG_IGN)   # 启动它的终端/宿主关了也不受影响
    pet.root.after(150, pet.poll)
    pet.root.after(260, pet.tick)
    pet.root.after(300, pet.hover_poll)
    pet.root.mainloop()


if __name__ == "__main__":
    main()
