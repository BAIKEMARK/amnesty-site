// whaleychan.com/api/bili —— 主页的实时数据（Cloudflare Pages Function）
//
// 浏览器不能跨域直连 B 站接口，这里在边缘节点代抓公开数据，按 home/fetch_bili.py
// 同样的格式返回。边缘缓存 5 分钟；B 站限流时返回最近一次成功的数据（最多 1 天前），
// 再不行就 502，前端继续用 CI 每 2 小时打包进页面的那份。
// 可选：在 Pages 项目里配 BILI_SESSDATA，登录态更不容易被风控。

const UID = "3747573030456892";
const TTL = 300; // 正常缓存
const STALE_TTL = 86400; // 抓不到时兜底
const FRESH_MIN = 60; // ?fresh=1 最多每分钟真回源一次
const DAY_RE = /【\s*Day\s*(\d+)\s*】/i;
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const cache = caches.default;
  const key = new Request(`${url.origin}/api/bili?_c=live`);
  const staleKey = new Request(`${url.origin}/api/bili?_c=stale`);
  const wantFresh = url.searchParams.has("fresh");

  const hit = await cache.match(key);
  if (hit) {
    const age = Date.now() / 1000 - Number(hit.headers.get("X-Whale-Fetched") || 0);
    if (!wantFresh || age < FRESH_MIN) return tag(hit, "HIT");
  }

  try {
    const data = await fetchBili(env);
    const body = JSON.stringify(data);
    context.waitUntil(cache.put(key, json(body, TTL)));
    context.waitUntil(cache.put(staleKey, json(body, STALE_TTL)));
    return tag(json(body, 0), "MISS");
  } catch (err) {
    const stale = (await cache.match(staleKey)) || hit;
    if (stale) return tag(stale, "STALE");
    return new Response(JSON.stringify({ error: String(err && err.message || err) }), {
      status: 502,
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
}

function json(body, ttl) {
  return new Response(body, {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": ttl ? `public, max-age=${ttl}` : "no-store",
      "X-Whale-Fetched": String(Math.floor(Date.now() / 1000)),
    },
  });
}

function tag(resp, state) {
  const r = new Response(resp.body, resp);
  r.headers.set("Cache-Control", "no-store"); // 浏览器别缓存，边缘缓存由上面管
  r.headers.set("X-Whale-Cache", state);
  return r;
}

async function get(path, params, env) {
  const qs = new URLSearchParams(params).toString();
  const cookie = [`buvid3=${crypto.randomUUID().toUpperCase()}infoc`];
  if (env.BILI_SESSDATA) cookie.push(`SESSDATA=${env.BILI_SESSDATA}`);
  let last = "";
  for (let i = 0; i < 2; i++) {
    const res = await fetch(`https://api.bilibili.com${path}?${qs}`, {
      headers: { "User-Agent": UA, Referer: `https://space.bilibili.com/${UID}`, Cookie: cookie.join("; ") },
      cf: { cacheTtl: 0 },
    });
    try {
      const body = await res.json();
      if (body.code === 0) return body.data;
      last = `${body.code} ${body.message}`;
    } catch {
      last = `HTTP ${res.status}`;
    }
  }
  throw new Error(`${path} -> ${last}`);
}

async function fetchBili(env) {
  const uid = env.BILI_UID || UID;
  const [follow, ...pages] = await Promise.all([
    get("/x/relation/stat", { vmid: uid }, env),
    get("/x/space/arc/list", { mid: uid, pn: 1, ps: 50 }, env),
  ]);
  let archives = pages[0].archives || [];
  const total = (pages[0].page || {}).count || archives.length;
  for (let pn = 2; archives.length < total && pn <= 4; pn++) {
    const more = await get("/x/space/arc/list", { mid: uid, pn, ps: 50 }, env);
    if (!more.archives || !more.archives.length) break;
    archives = archives.concat(more.archives);
  }
  if (!archives.length) throw new Error("0 个视频");
  const videos = archives
    .slice()
    .sort((a, b) => a.pubdate - b.pubdate)
    .map((v) => {
      const s = v.stat || {};
      const m = DAY_RE.exec(v.title || "");
      return {
        bvid: v.bvid,
        title: v.title || "",
        day: m ? Number(m[1]) : null,
        kind: m ? "day" : (v.title || "").includes("加更") ? "extra" : "other",
        pubdate: v.pubdate,
        duration: v.duration || 0,
        pic: (v.pic || "").replace("http://", "https://"),
        view: s.view || 0,
        like: s.like || 0,
        reply: s.reply || 0,
        favorite: s.favorite || 0,
        danmaku: s.danmaku || 0,
        share: s.share || 0,
      };
    });
  return {
    uid,
    space: `https://space.bilibili.com/${uid}`,
    follower: follow.follower || 0,
    videos,
    source: "live",
    updatedAt: new Date().toISOString(),
  };
}
