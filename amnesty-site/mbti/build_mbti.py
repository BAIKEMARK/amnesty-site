"""鲸鱼娘 MBTI 小测验页面打包：把 template/style/core/app/questions 内联成一个 index.html。
页面风格与主页（home/）一致：同一套配色、顶栏、底部 tab、页脚，标题用同一款手写字体（按本页用字子集化成 hand.woff）。

  python amnesty-site/mbti/build_mbti.py                 # 输出到 amnesty-site/mbti/dist/mbti/index.html
  python amnesty-site/mbti/build_mbti.py --out <目录>     # 输出到 <目录>/mbti/index.html（挂在站点的 /mbti/ 下）

纯静态：题库在页面里，计分在浏览器里算，不请求任何接口，不上传答案。
需要 pip install fonttools（requirements.txt 已有）；没装时退回整套手写字体（体积大但字全）。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = HERE.parent / "home"
HOME_ASSETS = HOME / "assets"
FONT = HOME / "fonts" / "MaShanZheng-Regular.ttf"
IMAGES = {"avatar": "avatar.webp", "smug": "ex-smug.webp", "think": "ex-think.webp"}
SPACE_FALLBACK = "https://www.bilibili.com"


def space_url() -> str:
    """B 站空间链接，取法和 home/build_home.py 一致。"""
    try:
        bili = json.loads((HOME / "bili.json").read_text(encoding="utf-8"))
        return bili.get("space") or f"https://space.bilibili.com/{bili['uid']}"
    except (OSError, ValueError, KeyError):
        return SPACE_FALLBACK


def write_font(dest: Path, text: str) -> None:
    """手写体只保留本页用到的字，避免「半截手写半截黑体」。"""
    chars = set(text) | {chr(c) for c in range(0x20, 0x7F)} | set("，。！？、：；“”‘’（）《》「」…—～·")
    chars = {c for c in chars if c.isprintable()}
    try:
        from fontTools import subset
    except ImportError:
        shutil.copy2(FONT, dest)
        print("warning: 未安装 fonttools，手写字体未子集化")
        return
    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = ["*"]
    opts.notdef_outline = True
    font = subset.load_font(str(FONT), opts)
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(font)
    subset.save_font(font, str(dest), opts)


def write_zip(dest: Path, types: dict) -> None:
    """16 张透明底表情（types-cut）打成一个包，文件名带类型和称号，固定时间戳让重复打包结果一致。"""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as zf:
        for key, info in types.items():
            src = HERE / "assets" / "types-cut" / f"{key}.webp"
            item = zipfile.ZipInfo(f"{key}-{info['name']}.webp", date_time=(2026, 11, 3, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED
            zf.writestr(item, src.read_bytes())


def build(out: Path | str | None = None) -> Path:
    out = Path(out) if out else HERE / "dist"
    template = (HERE / "template.html").read_text(encoding="utf-8")
    questions = (HERE / "questions.json").read_text(encoding="utf-8")
    data = json.loads(questions)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    css = (HERE / "style.css").read_text(encoding="utf-8")
    core = (HERE / "core.js").read_text(encoding="utf-8")
    app = (HERE / "app.js").read_text(encoding="utf-8")

    html = template.replace("__CSS__", css).replace("__DATA__", payload).replace("__CORE__", core).replace("__JS__", app)
    html = html.replace("__SPACE__", space_url())
    for key in IMAGES:  # 头像和表情在页面里会用好几次，单独放一份文件，不内联
        html = html.replace(f"__img_{key}__", f"/mbti/img/ui-{key}.webp")
    left = re.findall(r"__(?:CSS|DATA|CORE|JS|SPACE|img_[a-z]+)__", html)  # 页面自己的 window.__QUIZ__ 不算占位符
    assert not left, f"mbti 页面仍有未替换的占位符：{sorted(set(left))}"

    target = out / "mbti"
    target.mkdir(parents=True, exist_ok=True)
    (target / "index.html").write_text(html, encoding="utf-8")
    write_font(target / "hand.woff", template + app + questions)
    # 16 张结果图（鲸鱼娘 Q 版 MBTI 角色）不内联，单独放 /mbti/img/，出结果时才加载那一张
    img = target / "img"
    img.mkdir(exist_ok=True)
    for src in (HERE / "assets" / "types").glob("*.webp"):
        (img / src.name).write_bytes(src.read_bytes())
    write_zip(target / "whale-mbti-16.zip", data["types"])
    for key, name in IMAGES.items():
        (img / f"ui-{key}.webp").write_bytes((HOME_ASSETS / name).read_bytes())
    return target / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="输出目录，页面会写到 <out>/mbti/index.html")
    args = parser.parse_args(argv)
    path = build(args.out)
    print(f"已打包：{path}（{path.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
