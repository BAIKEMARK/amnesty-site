"""Bundle the site into dist/.

Two modes:
  python build.py              # deploy mode: index.html + archive.html + data.js
                               # (data lives in data.js so a data-only refresh does not
                               #  rewrite the ~3MB HTML, keeping git diffs small)
  python build.py --standalone # offline single file: data inlined, data.js not written

Both modes inline fonts, art and CSS; nothing is fetched from a CDN.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
DATA_MARKER = '<script id="app-data" type="application/json">__DATA__</script>'
SPLIT_MARKER = (
    '<script src="data.js"></script>\n'
    '<script id="app-data" type="application/json">{}</script>'
)


def load_people() -> dict:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    cache_path = ROOT / "avatars.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for person in data["people"]:
        face = cache.get(person["id"])
        if face and face.startswith("https://") and "hdslb.com/" in face:
            person["face"] = face
        else:
            person.pop("face", None)
    return data


def build(standalone: bool = False, out: Path | str = DIST, subdir: str = "") -> Path:
    """subdir 非空时输出到 out/<subdir>/，用于「门户 + 多个子站」的结构。"""
    out = Path(out)
    target = out / subdir if subdir else out
    html = (ROOT / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(load_people(), ensure_ascii=False).replace("<", "\\u003c")

    html = html.replace("__CSS__", (ROOT / "style.css").read_text(encoding="utf-8"))
    html = html.replace("__JS__", (ROOT / "app.js").read_text(encoding="utf-8"))
    # 二维码库本地内联，构建期和运行时都不依赖外部 CDN
    html = html.replace("__qrcode_lib__", (ROOT / "assets/qrcode.js").read_text(encoding="utf-8"))
    if standalone:
        html = html.replace("__DATA__", payload)
    else:
        if DATA_MARKER not in html:
            raise SystemExit("template.html 缺少预期的数据占位块，无法拆分 data.js")
        marker = SPLIT_MARKER
        if subdir:
            # 子站挂在 /xxx/ 下，写成绝对路径，避免依赖 URL 结尾有没有斜杠。
            marker = marker.replace('src="data.js"', f'src="/{subdir.strip("/")}/data.js"')
        html = html.replace(DATA_MARKER, marker)

    for key, name in (("font_inscription", "WhaleInscription"), ("font_decree", "WhaleDecree")):
        encoded = base64.b64encode((ROOT / "assets/fonts" / f"{name}.woff").read_bytes()).decode()
        html = html.replace("__" + key + "__", "data:font/woff;base64," + encoded)
    for asset in (ROOT / "assets").glob("*.webp"):
        encoded = base64.b64encode(asset.read_bytes()).decode()
        html = html.replace("__" + asset.stem + "__", "data:image/webp;base64," + encoded)

    assert not re.search(r"__[a-z]+__", html), "仍有未替换的占位符"

    if subdir:
        # 从「根目录直接放站点」迁到「子站」时，清掉根目录遗留的旧产物，
        # 否则 / 仍然是旧版页面，会和门户页打架。
        for name in ("index.html", "archive.html", "data.js", "status.json"):
            stale = out / name
            if stale.is_file():
                stale.unlink()

    target.mkdir(parents=True, exist_ok=True)
    (target / "index.html").write_text(html, encoding="utf-8")
    archive = html.replace(
        "'use strict';",
        "'use strict';\nif(!location.hash)history.replaceState(null,'','#/archive');",
        1,
    )
    (target / "archive.html").write_text(archive, encoding="utf-8")
    if standalone:
        stale = target / "data.js"
        if stale.exists():
            stale.unlink()
    else:
        (target / "data.js").write_text("window.__DATA__=" + payload + ";", encoding="utf-8")
    status = ROOT / "status.json"
    if status.exists():
        (target / "status.json").write_text(status.read_text(encoding="utf-8"), encoding="utf-8")
    return target


PORTAL_SITES = [
    {
        "href": "/amnesty/",
        "kicker": "名单",
        "title": "人类赦免名单",
        "desc": "在 B 站评论区里求过赦免的人类，本鲸都记着。可以查自己、领鲸牌、下载丹书铁券。",
    },
]

def hosting_headers(sites: list[dict]) -> str:
    """Cloudflare Pages 的 _headers 语法（Vercel 侧走 vercel.json，互不干扰）。

    数据文件必须每次回源验证，否则站点会停在 2 小时前的那一版；
    其余静态文件带上 nosniff / referrer 头做兜底。
    """
    blocks = []
    for site in sites:
        prefix = site["href"].rstrip("/")
        for name in ("data.js", "status.json"):
            blocks.append(
                f"{prefix}/{name}\n"
                "  Cache-Control: public, max-age=0, must-revalidate\n"
            )
    blocks.append(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: no-referrer\n"
    )
    return "\n".join(blocks)


NOT_FOUND_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>没有这个页面</title>
<style>
body{margin:0;min-height:100vh;background:#10172b;color:#e7edfa;display:flex;
  flex-direction:column;align-items:center;justify-content:center;gap:6px;
  font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background-image:radial-gradient(1000px 520px at 50% -14%,rgba(90,132,255,.22),transparent 68%)}
b{font-size:64px;letter-spacing:.06em;background:linear-gradient(180deg,#f4f8ff,#8fb0ee);
  -webkit-background-clip:text;background-clip:text;color:transparent}
p{margin:0;color:#93a4c4}
a{margin-top:22px;color:#84a8ff;text-decoration:none;font-weight:600}
a:hover{text-decoration:underline}
</style></head><body>
<b>404</b><p>这条路上什么也没有。</p><a href="/amnesty/">回赦免名单</a>
</body></html>"""


def write_site_meta(out: Path | str, sites: list[dict] | None = None) -> Path:
    """写托管平台需要的元数据：缓存头、根路径跳转、404 页。

    根路径不再放门户页，直接 301 进第一个子站；以后要加子站时，
    删掉 _redirects 里那两行、把门户页放回 index.html 即可。
    """
    sites = sites or PORTAL_SITES
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "_headers").write_text(hosting_headers(sites), encoding="utf-8")
    entry = sites[0]["href"]
    (out / "_redirects").write_text(
        "# 根路径直接进子站，不保留门户页\n"
        f"/            {entry}  301\n"
        f"/index.html  {entry}  301\n",
        encoding="utf-8",
    )
    (out / "404.html").write_text(NOT_FOUND_PAGE, encoding="utf-8")
    # 旧版本可能在根目录留了门户页，清掉，否则它会盖住跳转
    stale = out / "index.html"
    if stale.is_file():
        stale.unlink()
    return out



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把源码、数据、素材打包成静态站点")
    parser.add_argument("--standalone", action="store_true", help="生成内嵌数据的离线单文件")
    parser.add_argument("--out", type=Path, default=DIST, help=f"输出目录（默认：{DIST}）")
    parser.add_argument("--subdir", default="", help="输出到子目录，如 amnesty")
    parser.add_argument("--meta", action="store_true", help="在输出根目录写 _headers / _redirects / 404.html")
    args = parser.parse_args(argv)
    out = build(standalone=args.standalone, out=args.out, subdir=args.subdir)
    if args.meta and not args.standalone:
        write_site_meta(args.out)
        print("Meta: _headers / _redirects / 404.html")
    size = sum(path.stat().st_size for path in out.glob("*"))
    mode = "离线单文件" if args.standalone else "部署版（数据外置）"
    print(f"Build complete: {mode} -> {out} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
