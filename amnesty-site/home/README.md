# 鲸鱼娘主页（whaleychan.com/）

根路径的个人主页，和 `/amnesty/`（人类保留计划）、`/amnesty/games.html`（小游戏）共用同一个 dist。

- `template.html` / `style.css` / `app.js`：页面本体，打包时 CSS/JS 内联进 `dist/index.html`。前端路由切换 8 个页面：`/` 营业厅、`/whale` 档案、`/day` 一天、`/log` 日志、`/memes` 梗百科、`/songs` 点歌池、`/stats` 数据、`/extra` 番外；手机底部 Tab，电脑顶部导航。打包时给每个子路由复制一份 `dist/<路由>/index.html`，直接打开或刷新子页面不会 404
- `content.json`：**所有角色设定和文案**（口头禅、心声、表情、基本资料、性格、嘴硬翻译器、雷达、问答、同事录、作息表、每期标签/心情/当事鲸、梗百科、名台词、表情包）。改设定只改这个文件，不用碰代码。生日、身高、作息时间等部分是二创补充设定，可随时改
- `song_requests.json`：评论区点歌池，记录歌名、整理到的点单人数/赞数、翻唱状态和来源视频。只保留歌名与聚合数，不展示评论者；本页数据为人工整理的静态快照，新增点单后需更新此文件再构建
- `fonts/MaShanZheng-Regular.ttf`：手写标题字体（马善政体，OFL 授权，见 `fonts/OFL.txt`）。打包时用 fonttools 按页面实际用到的字子集化成 `home-assets/hand.woff`，所以新加的文案也不会出现「半截手写半截黑体」；正文统一用系统黑体
- `fetch_bili.py`：抓 B 站公开接口（粉丝、投稿、播放/点赞/收藏/评论/弹幕），写 `bili.json`；抓不到就保留上一版
- `bili.json`：CI 每 2 小时抓一次并提交，打包进页面当首屏数据
- `history.json`：每次抓取记一个点（粉丝/总播放/总点赞），画「涨势」曲线；7 天内全保留，更早的每天留一个
- `../../functions/api/bili.js`：Cloudflare Pages Function。页面打开后请求 `/api/bili` 拿实时数字（边缘缓存 5 分钟，「刷新数据」按钮最多每分钟真回源一次）；B 站限流时返回最近一次成功的数据，再不行页面就用 `bili.json`。可在 Pages 项目里配 `BILI_SESSDATA` 降低风控概率
- `assets/`：主页专属插画（表情 `ex-*`、作息 `day-*`、梗图 `meme-*`、同事 `mate-*` 等；logo、印章、嫌疑人图直接复用名单站和小游戏的素材）
- `build_home.py`：打包到 `site/dist/`（`index.html` + 子路由副本、`home-data.js`、`home-assets/`）。需要 `pip install fonttools`；没装时退回整套字体（体积大但字全）

`refresh.py` 在名单站打包完之后会自动调用；本地预览：

```bash
python amnesty-site/home/build_home.py --out /tmp/whale-home
```
