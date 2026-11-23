"""生成内置伙伴的像素图：companions/<id>.png + <id>.json。

每个伙伴是一张字符画，一个字符 = 一个像素，`.` 是透明。改完运行
    python3 make_companions.py
不依赖任何第三方包（自己写 PNG）。想看放大的效果加 --preview <目录>。
"""
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent / "companions"

SPRITES = {
    "whale": {
        "name": "小深", "description": "一条爱喷水的小蓝鲸，默认的伙伴。",
        "palette": {"K": "#1E3A5F", "B": "#4A90E2", "D": "#2F6DB5", "L": "#DCEBFA",
                    "W": "#FFFFFF", "P": "#F6A5B8", "S": "#8CC8FF"},
        "art": """
.......S..S.......
........SS........
.......S..S.......
..................
.....KKKKKKK......
...KKBBBBBBBKK....
..KBBBBBBBBBBBK...
.KBBBBBBBBBBBBBK..
.KBBWKBBBBBWKBBK..KK
KBBBKKBBBBBKKBBBKKBK
KBBPPBBBBBBBPPBBBBK.
KDBBBBBKKKBBBBBBBK..
KDDLLLLLLLLLLLDDK...
.KDLLLLLLLLLLLDK....
..KKDDLLLLLLDKK.....
....KKKKKKKKKK......
""",
    },
    "orange": {
        "name": "橘子", "description": "一只圆滚滚的橘猫，陪你摸鱼也陪你加班。",
        "palette": {"K": "#4A2C17", "O": "#F39A3D", "D": "#D9772A", "C": "#FFE8C8",
                    "W": "#FFFFFF", "P": "#F6A5B8", "N": "#E86A7A"},
        "art": """
..KK..........KK..
.KOOK........KOOK.
.KOPOK......KOPOK.
.KOOOKKKKKKKKOOOK.
KOOOOOOOOOOOOOOOOK
KODDOOOOOOOOOODDOK
KOOOOOOOOOOOOOOOOK
KOOWKOOOOOOOOWKOOK
KOOKKOOOOOOOOKKOOK
KOPPOOOONNOOOOPPOK
KOOOOOOKKKKOOOOOOK
.KOOOCCCCCCCCOOOK.
.KOOCCCCCCCCCCOOK.
..KOOCCCCCCCCOOK..
..KOOKKOOOOKKOOK..
...KKK.KKKK.KKK...
""",
    },
    "mochi": {
        "name": "团子", "description": "软乎乎的粉色麻薯，脾气很好。",
        "palette": {"K": "#6B3A4A", "M": "#FFD3DF", "H": "#FFFFFF", "S": "#F2AFC2",
                    "G": "#7CC36B", "g": "#4E9A44", "P": "#F28AA6"},
        "art": """
........gG........
.......gGGg.......
........g.........
.....KKKKKKKK.....
...KKMMMMMMMMKK...
..KMMHHMMMMMMMMK..
.KMMHHMMMMMMMMMMK.
.KMMMMMMMMMMMMMMK.
KMMMMKMMMMMMKMMMMK
KMMMMKMMMMMMKMMMMK
KMMPPMMMKKMMMPPMMK
KSMMMMMMMMMMMMMMSK
.KSSMMMMMMMMMMSSK.
..KKSSSSSSSSSSKK..
....KKKKKKKKKK....
""",
    },
    "penguin": {
        "name": "波波", "description": "一只认真的小企鹅，回复前会先想一想。",
        "palette": {"K": "#1B1F2A", "D": "#2E3445", "W": "#FFFFFF", "Y": "#FFB547",
                    "y": "#E8902A", "P": "#F6A5B8", "C": "#F2F4F8"},
        "art": """
.....KKKKKKK......
...KKDDDDDDDKK....
..KDDDDDDDDDDDK...
..KDDWWWDDWWWDK...
.KDDWWKWWWWKWWDK..
.KDDWWKWWWWKWWDK..
.KDDWPWWYYWWPWDK..
.KDDWWWyyyyWWWDK..
KDDDWWWWWWWWWWDDK.
KDDCWWWWWWWWWWCDDK
KDKCWWWWWWWWWWCKDK
.KKDCWWWWWWWWCDKK.
...KDCCWWWWCCDK...
...KKKKKKKKKKKK...
...KYYK....KYYK...
....KK......KK....
""",
    },
}


def png_bytes(rows: list[list[tuple | None]]) -> bytes:
    h, w = len(rows), max(len(r) for r in rows)
    raw = b""
    for r in rows:
        raw += b"\x00" + b"".join(bytes(px) if px else b"\x00\x00\x00\x00" for px in r + [None] * (w - len(r)))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def pixels(spec, scale=1):
    pal = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) + (255,) for k, v in spec["palette"].items()}
    lines = [ln for ln in spec["art"].strip("\n").split("\n")]
    out = []
    for ln in lines:
        row = []
        for ch in ln:
            row += [pal.get(ch)] * scale
        out += [row] * scale
    return out


def main():
    HERE.mkdir(exist_ok=True)
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    for cid, spec in SPRITES.items():
        (HERE / f"{cid}.png").write_bytes(png_bytes(pixels(spec)))
        meta = {"name": spec["name"], "author": "小深", "description": spec["description"],
                "order": list(SPRITES).index(cid) + 1}
        (HERE / f"{cid}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if preview:
            Path(preview, f"{cid}.png").write_bytes(png_bytes(pixels(spec, 14)))
    print("wrote", ", ".join(SPRITES))


if __name__ == "__main__":
    main()
