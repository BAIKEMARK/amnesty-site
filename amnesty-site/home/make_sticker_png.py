"""把表情包墙上的 webp 导出成 240×240 透明 png，放进 home/sticker-png/，打包 zip 时一并带上。

为什么要预先生成：CI 只装了 fonttools，没有 Pillow，所以 png 在本地生成后随仓库提交。
微信、B 站对 webp 的支持不稳，png 才是通用的。新增或改动表情后重新跑一遍：

    python amnesty-site/home/make_sticker_png.py
"""
from pathlib import Path

from PIL import Image

HOME = Path(__file__).resolve().parent
OUT = HOME / "sticker-png"
SIZE = 240


def sources() -> dict[str, Path]:
    found = {p.stem: p for p in (HOME / "assets").glob("stk-*.webp")}
    for p in (HOME.parent / "mbti" / "assets" / "types-cut").glob("*.webp"):
        found[f"mbti-{p.stem}"] = p
    return found


def main() -> None:
    OUT.mkdir(exist_ok=True)
    n = 0
    for key, path in sorted(sources().items()):
        im = Image.open(path).convert("RGBA")
        im.thumbnail((SIZE, SIZE), Image.LANCZOS)
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        canvas.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)
        canvas.save(OUT / f"{key}.png", optimize=True)
        n += 1
    print(f"{n} png -> {OUT}")


if __name__ == "__main__":
    main()
