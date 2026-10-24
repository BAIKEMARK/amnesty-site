# 人类特赦名单 · 数据与站点

从 B 站账号「DeepSeek鲸鱼娘在运营」的**公开评论与私信**里，找出「申请赦免 / 申请加入名单」的人，合并成名册并生成静态站点。

本站不审核资格，也不判定谁「配得上」；只做两件事：把公开留言里明确在申请的人找出来，按 UID 合并、去重、标好来源。

## 站点

产物是 `amnesty-site/site/dist`，由 GitHub Actions 重新生成后提交进仓库，托管平台只需发布这个目录、**不需要构建命令**。

```
dist/
├── 404.html            自定义 404
├── _headers            Cloudflare Pages 的缓存与安全头
├── _redirects          根路径 301 → /amnesty/
└── amnesty/            赦免名单
    ├── index.html      首页
    ├── archive.html    完整名册
    ├── data.js         名册数据（约 6 MB，独立文件，强制回源验证）
    └── status.json     上一次抓取的结果、耗时、被平台分页截断的内容
```

**根路径不放页面**，直接 301 进 `/amnesty/`（`_redirects` 里两行）。想加回门户时，删掉那两行、把 `index.html` 放回 `dist/` 即可，子站路径不用动。

### 部署

主站在 **Cloudflare Pages**，用 Direct Upload 直传 `dist`，不经过 Cloudflare 的构建环境。产物本来就由 Actions 生成好并提交进仓库，再让 CF 拉一遍代码、跑一遍空构建是多余的；直传把部署压到 10 秒左右，失败也不影响线上那一版。

| 项 | 值 |
|---|---|
| 项目名 | `whalegirl` → `whalegirl.pages.dev` |
| 部署触发 | `update-amnesty-site.yml` 最后一个步骤跑 `wrangler pages deploy` |
| 自定义域名 | `whaleychan.com` 与 `www.whaleychan.com`，CNAME 指向 `whalegirl.pages.dev` |

免费额度：带宽与请求**不限**，只有「每月 500 次部署 + 500 次构建」的限制。现在每 2 小时一轮约 360 次/月，余量够用；如果以后改成 1 小时一轮就会超。

没配 `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` 时，工作流照常抓取和提交，只是跳过部署（不会报红）。

`vercel.json` 保留着，Vercel 那边仍可作为备份站；两边的缓存规则各自生效，互不影响。

## 数据怎么来的

```
B 站公开评论 / 私信
   ↓ crawl        bilibili.py        逐内容翻页，增量靠 crawl-state.json 的水位
   ↓ judge        amnesty-site/judge.py
        ① strong   命中「赦免 / 特赦 / 免死 / 铁券」等，或模板请愿句式 → 直接收录
        ② veto     命中 token / 邀请码 / 账号 等 → 整条丢弃（申请的是别的东西）
        ③ intent   命中「申请 / 我也要 / 算我一个 / 我我我」+ 第一人称 → 进灰区
        ④ scope    该内容下不足 3 条明确申请 → 不认定为名单帖
        ⑤ Jev      灰区交 TypeSafe Jev 批量判定，noul ≥ 0.55 收录
   ↓ merge        amnesty-site/site/import_comments.py   按 UID 合并，编号稳定
   ↓ avatars      amnesty-site/fetch_avatars.py              只取 B 站 CDN 外链，不下载图片
   ↓ build        amnesty-site/site/build.py             打包 dist
```

口径全部写在 `amnesty-site/keywords.json`，改判定规则不用动代码。

## 自动更新

`.github/workflows/update-amnesty-site.yml`：

| 触发 | 行为 |
|---|---|
| 每 2 小时（`23 */2 * * *`） | 增量：每个内容翻到上次水位就停，只判新评论 |
| 每周日 03:17 UTC | 全量对账，补增量可能漏掉的角落 |
| 手动 `workflow_dispatch` | 可勾选「强制全量」 |

每次跑完自动提交 `data.json` / `dist` / `status.json` / `avatars.json` / `crawl-state.json`，托管平台随之重新部署。抓取失败时不会覆盖上一次的数据，只把 `status.json` 的 `result` 写成 `failed`。

需要的 Secrets：

| 名称 | 必需 | 用途 |
|---|---|---|
| `BILI_AGENT_BILI_SESSDATA` | 是 | 私信必须登录态；头像批量接口也要求登录 |
| `BILI_AGENT_BILI_JCT` | 否 | 只用于写操作，本仓库的读取流程不需要 |
| `BILI_AGENT_BILI_USER_ID` | 是 | 确定抓哪个账号的投稿与动态 |
| `TYPESAFE_API_KEYS` | 建议 | Jev 钥匙，多个用逗号或换行分隔；不配则灰区全收 |
| `CLOUDFLARE_API_TOKEN` | 部署用 | 权限只需 `Cloudflare Pages:Edit`；不配则不部署 |
| `CLOUDFLARE_ACCOUNT_ID` | 部署用 | 账户 ID，Cloudflare 仪表盘 URL 里那串 32 位十六进制 |

## 本地跑

```bash
python amnesty-site/refresh.py --fetch                 # 增量
python amnesty-site/refresh.py --fetch --full          # 全量（约 70 分钟）
python amnesty-site/refresh.py --fetch --dry-run       # 只报会新增多少人
python amnesty-site/refresh.py --source 某个评论.csv    # 离线导入已有 CSV
```

常用参数：`--judge jev|llm|rules|words`、`--no-private`、`--no-avatars`、`--thread-window-hours`、`--private-window-minutes`。

## 已知限制

- **楼中楼深分页**：B 站 `/x/v2/reply/reply` 在 `pn≈250` 之后返回 `-400 max offset exceeded`，单栋热楼约 5000 条回复封顶。根评论没有这个限制（实测可翻 13,817 条）。撞上限时不会失败，只记进 `status.json` 的 `truncatedContents`。
- **头像**：只存 B 站 CDN 外链，不下载。批量接口 `account/v1/user/cards` 一次最多 50 个 UID，且必须带 SESSDATA。
- **判定**：规则层是「宁可多收」的口径，模板请愿句式、同音错字（特摄→特赦）都会直接放行，会有少量无关内容混入。
- 被 Jev 拒掉的条目落盘在 `amnesty-site/site/rejected.json`，调判据时读这个文件重判即可，不必重抓。
