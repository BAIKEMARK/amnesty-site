"""Bundle the homepage (whaleychan.com/) into the site dist root.

  python build_home.py            # 用现有 bili.json 打包到 ../site/dist
  python build_home.py --fetch    # 先抓 B 站公开数据，再打包

产物：
  dist/index.html        主页（CSS / JS 内联，单页应用，7 个“页面”前端切换）
  dist/{whale,day,log,memes,stats,extra}/index.html  同一份页面的路由副本（直接打开/刷新子页不 404）
  dist/home-data.js      角色设定(content.json) + B 站数据 + 增长曲线 + 名单人数
  dist/home-assets/hand.woff  手写字体：从 fonts/MaShanZheng-Regular.ttf 按页面实际用字子集化
  浏览器打开后还会轮询 /api/bili（Cloudflare Pages Function）拿实时数字
  dist/home-assets/*     图片与字体
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import zipfile
from pathlib import Path

HOME = Path(__file__).parent
SITE = HOME.parent / "site"
DIST = SITE / "dist"
GAMES = HOME.parent / "games"

# 和名单页 / 小游戏共用的素材，直接从原位置拿，不重复入库
SHARED = {
    "logo.webp": SITE / "assets" / "logo.webp",
    "stamp.webp": SITE / "assets" / "stamp.webp",
    "suspect.webp": GAMES / "assets" / "end_suspect.webp",
}
# 主页专属插画：优先用 home/assets/ 里的真文件，没有就从 assets.pack.json（base64）解出来
PACK = HOME / "assets.pack.json"
FONT = HOME / "fonts" / "MaShanZheng-Regular.ttf"
OLD_FONT = SITE / "assets" / "fonts" / "WhaleDecree.woff"
MBTI = HOME.parent / "mbti"  # MBTI 小测验的 16 张结果图，也并入表情包
ROUTES = ["whale", "day", "log", "memes", "stats", "extra"]


def mbti_stickers() -> list[dict]:
    """MBTI 的 16 张鲸鱼娘表情（透明底版，由 mbti/cutout.py 生成），追加在表情包最后。"""
    path = MBTI / "questions.json"
    if not path.exists():
        return []
    types = json.loads(path.read_text(encoding="utf-8")).get("types", {})
    return [{"img": f"mbti-{k}", "name": f"{k} {v['name']}"} for k, v in types.items()
            if (MBTI / "assets" / "types-cut" / f"{k}.webp").exists()]


def amnesty_counts() -> dict:
    status = SITE / "status.json"
    if status.exists():
        data = json.loads(status.read_text(encoding="utf-8"))
        if data.get("people"):
            return {"people": data["people"], "comments": data.get("comments", 0)}
    data = json.loads((SITE / "data.json").read_text(encoding="utf-8"))
    return {"people": len(data["people"]), "comments": data.get("commentCount", 0)}


def build(out: Path | str = DIST) -> Path:
    out = Path(out)
    bili = json.loads((HOME / "bili.json").read_text(encoding="utf-8"))
    content = json.loads((HOME / "content.json").read_text(encoding="utf-8"))
    content["stickers"] = list(content.get("stickers", [])) + mbti_stickers()
    css = (HOME / "style.css").read_text(encoding="utf-8")
    js = (HOME / "app.js").read_text(encoding="utf-8")
    tpl = (HOME / "template.html").read_text(encoding="utf-8")
    html = tpl.replace("__CSS__", css).replace("__JS__", js)
    html = html.replace("__SPACE__", bili.get("space") or f"https://space.bilibili.com/{bili['uid']}")
    left = [k for k in ("__CSS__", "__JS__", "__SPACE__") if k in html]
    assert not left, f"主页模板仍有未替换的占位符：{left}"

    out.mkdir(parents=True, exist_ok=True)
    titles = dict(re.findall(r'data-route="([^"]*)" data-title="([^"]*)"', tpl))
    home_title = titles.get("/", "鲸鱼娘在运营")
    (out / "index.html").write_text(html.replace("__TITLE__", home_title), encoding="utf-8")
    for r in ROUTES:
        d = out / r
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html.replace("__TITLE__", titles.get("/" + r, home_title)), encoding="utf-8")

    hist_path = HOME / "history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    payload = {"content": content, "bili": bili, "history": history, "amnesty": amnesty_counts()}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    (out / "home-data.js").write_text("window.__HOME__=" + text + ";", encoding="utf-8")

    assets = out / "home-assets"
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True)
    write_assets(assets)
    write_sticker_zip(assets, content)
    write_font(assets / "hand.woff", tpl + js + json.dumps(content, ensure_ascii=False) + json.dumps(bili, ensure_ascii=False))
    return out


def write_font(dest: Path, text: str) -> None:
    """手写体只保留页面真正用到的字，避免“半截手写半截黑体”。"""
    chars = set(text) | {chr(c) for c in range(0x20, 0x7F)} | set("，。！？、：；“”‘’（）《》「」…—～·")
    chars = {c for c in chars if c.isprintable()}
    try:
        from fontTools import subset
    except ImportError:
        if FONT.exists():
            shutil.copy2(FONT, dest)  # 没装 fonttools：直接用整套字体（体积大但字全）
        else:
            shutil.copy2(OLD_FONT, dest)
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


STICKER_ZIP = "whale-stickers.zip"
STICKER_NOTE = """DeepSeek鲸鱼娘在运营 · 表情包

可以：个人使用、聊天、做头像、粉丝同人二创（请注明出处）。
请勿：商用售卖、做成周边出售、冒充官方账号、用于误导性内容。

本账号「DeepSeek鲸鱼娘在运营」非深度求索（DeepSeek）官方账号；
鲸鱼娘形象及表情包由 AI 生成，仅为粉丝自制二创福利。
文件夹说明：根目录是 webp（网页用），PNG/ 里是 240×240 透明底 png，导入微信 / B 站请用 PNG。

形象鸣谢：鲸鱼娘基于「溟月：上善无形」及 ZipZipPipe 两位老师的 DeepSeek 女仆鲸鱼娘设计二次创作。
  溟月：上善无形 https://space.bilibili.com/4456176
  ZipZipPipe https://space.bilibili.com/4168597
GPT 龙娘、Gemini 娘等配角均为非官方拟人二创形象。

B站：DeepSeek鲸鱼娘在运营
"""


def write_sticker_zip(dest: Path, content: dict) -> None:
    """把表情包打成一个压缩包，给番外页的「打包下载」用；每次打包重新生成，不入库。

    时间戳固定，表情包不变时压缩包逐字节相同，CI 提交 dist/ 时不会每轮多出一份 zip。
    """
    bad = str.maketrans({c: "_" for c in '\\/:*?"<>|'})

    def entry(name: str) -> zipfile.ZipInfo:
        return zipfile.ZipInfo("鲸鱼娘表情包/" + name, date_time=(2026, 1, 1, 0, 0, 0))

    with zipfile.ZipFile(dest / STICKER_ZIP, "w", zipfile.ZIP_STORED) as z:
        z.writestr(entry("使用说明.txt"), STICKER_NOTE)
        for i, s in enumerate(content.get("stickers", []), 1):
            s = {"img": s, "name": ""} if isinstance(s, str) else s
            name = (s.get("name") or s["img"]).translate(bad)
            z.writestr(entry(f"{i:02d}_{name}.webp"), (dest / f"{s['img']}.webp").read_bytes())
            png = HOME / "sticker-png" / f"{s['img']}.png"  # 微信 / B 站不一定收 webp，另附 png（home/make_sticker_png.py 生成）
            if png.exists():
                z.writestr(entry(f"PNG/{i:02d}_{name}.png"), png.read_bytes())


def write_assets(dest: Path) -> None:
    local = HOME / "assets"
    if local.is_dir():
        for f in local.iterdir():
            if f.is_file():
                shutil.copy2(f, dest / f.name)
    if PACK.exists():
        for name, b64 in json.loads(PACK.read_text(encoding="utf-8")).items():
            if not (dest / name).exists():
                (dest / name).write_bytes(base64.b64decode(b64))
    for name, src in SHARED.items():
        if not (dest / name).exists() and src.exists():
            shutil.copy2(src, dest / name)
    for s in mbti_stickers():
        shutil.copy2(MBTI / "assets" / "types-cut" / f"{s['img'][5:]}.webp", dest / f"{s['img']}.webp")
    content = json.loads((HOME / "content.json").read_text(encoding="utf-8"))
    refs = set(re.findall(r"[\w-]+\.(?:webp|jpg|png)", json.dumps(content) + (HOME / "template.html").read_text(encoding="utf-8") + (HOME / "app.js").read_text(encoding="utf-8")))
    refs = {r for r in refs if not r[0].isdigit()}  # 排除 B 站封面尺寸后缀（@480w_270h_1c.webp）
    need = sorted(refs | set(SHARED) | {"og.jpg"})
    missing = [n for n in need if not (dest / n).exists()]
    assert not missing, f"主页素材缺失：{missing}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打包鲸鱼娘主页")
    parser.add_argument("--out", type=Path, default=DIST)
    parser.add_argument("--fetch", action="store_true", help="先抓取 B 站公开数据更新 bili.json")
    args = parser.parse_args(argv)
    if args.fetch:
        import importlib.util

        spec = importlib.util.spec_from_file_location("home_fetch_bili", HOME / "fetch_bili.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()
    out = build(args.out)
    print(f"Homepage -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
