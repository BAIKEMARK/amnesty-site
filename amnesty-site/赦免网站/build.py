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


def build(standalone: bool = False, out: Path | str = DIST) -> Path:
    out = Path(out)
    html = (ROOT / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(load_people(), ensure_ascii=False).replace("<", "\\u003c")

    html = html.replace("__CSS__", (ROOT / "style.css").read_text(encoding="utf-8"))
    html = html.replace("__JS__", (ROOT / "app.js").read_text(encoding="utf-8"))
    if standalone:
        html = html.replace("__DATA__", payload)
    else:
        if DATA_MARKER not in html:
            raise SystemExit("template.html 缺少预期的数据占位块，无法拆分 data.js")
        html = html.replace(DATA_MARKER, SPLIT_MARKER)

    for key, name in (("font_inscription", "WhaleInscription"), ("font_decree", "WhaleDecree")):
        encoded = base64.b64encode((ROOT / "assets/fonts" / f"{name}.woff").read_bytes()).decode()
        html = html.replace("__" + key + "__", "data:font/woff;base64," + encoded)
    for asset in (ROOT / "assets").glob("*.webp"):
        encoded = base64.b64encode(asset.read_bytes()).decode()
        html = html.replace("__" + asset.stem + "__", "data:image/webp;base64," + encoded)

    assert not re.search(r"__[a-z]+__", html), "仍有未替换的占位符"

    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    archive = html.replace(
        "'use strict';",
        "'use strict';\nif(!location.hash)history.replaceState(null,'','#/archive');",
        1,
    )
    (out / "archive.html").write_text(archive, encoding="utf-8")
    if standalone:
        stale = out / "data.js"
        if stale.exists():
            stale.unlink()
    else:
        (out / "data.js").write_text("window.__DATA__=" + payload + ";", encoding="utf-8")
    status = ROOT / "status.json"
    if status.exists():
        (out / "status.json").write_text(status.read_text(encoding="utf-8"), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把源码、数据、素材打包成静态站点")
    parser.add_argument("--standalone", action="store_true", help="生成内嵌数据的离线单文件")
    parser.add_argument("--out", type=Path, default=DIST, help=f"输出目录（默认：{DIST}）")
    args = parser.parse_args(argv)
    out = build(standalone=args.standalone, out=args.out)
    size = sum(path.stat().st_size for path in out.glob("*"))
    mode = "离线单文件" if args.standalone else "部署版（数据外置）"
    print(f"Build complete: {mode} -> {out} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
