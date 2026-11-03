"""把 assets/types/ 的 16 张结果图去掉米色底，输出透明底表情到 assets/types-cut/。

图片是纯色米色背景，从四边做连通填充就能去掉；再给人物描一圈白边，和主页其它表情包（白描边贴纸）风格一致。
只在换图时重跑一次：python amnesty-site/mbti/cutout.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
SRC = HERE / "assets" / "types"
DST = HERE / "assets" / "types-cut"
TOL = 26          # 与背景色的最大色差
OUTLINE = 5       # 白描边宽度（像素，按 480 边长）


def cut(path: Path) -> Image.Image:
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    near = np.abs(rgb - bg).max(axis=2) <= TOL
    labels, _ = ndimage.label(near)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    background = np.isin(labels, edge[edge > 0])
    subject = ~background
    subject = ndimage.binary_opening(subject, iterations=1)
    labels, n = ndimage.label(subject)          # 只留最大的一块，去掉零星斑点
    if n > 1:
        sizes = ndimage.sum(subject, labels, range(1, n + 1))
        subject = labels == (1 + int(np.argmax(sizes)))
    subject = ndimage.binary_fill_holes(subject)
    outer = ndimage.binary_dilation(subject, structure=np.ones((3, 3)), iterations=OUTLINE)
    alpha = ndimage.gaussian_filter(outer.astype(np.float32), 1.0)
    alpha = np.clip((alpha - 0.35) / 0.4, 0, 1)
    inner = ndimage.gaussian_filter(subject.astype(np.float32), 0.8)[..., None]
    out = rgb.astype(np.float32) * inner + 255.0 * (1 - inner)   # 描边区域是白色
    rgba = np.dstack([out, alpha * 255]).clip(0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def main() -> int:
    DST.mkdir(exist_ok=True)
    for src in sorted(SRC.glob("*.webp")):
        cut(src).save(DST / src.name, "WEBP", quality=88, method=6)
    print(f"已输出 {len(list(DST.glob('*.webp')))} 张到 {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
