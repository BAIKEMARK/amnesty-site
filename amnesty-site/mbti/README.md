# 鲸鱼娘的 MBTI 小测验（whaleychan.com/mbti/，待上线）

Day 15 的配套页面。鲸鱼娘自编的 20 道二选一（非官方题库），两个入口：**我来测**（逐题点，当场出结果）和**测我的大肥鱼**（复制提示词发给自己的 AI，让它只回 20 个 A/B 字母，再贴回页面算结果）。

- 纯静态：题库、计分都在浏览器里，不请求任何接口，不上传答案，没有后台、没有 API Key、没有费用。
- `questions.json`：20 题（每个维度 5 题，选 A 偏前一个字母，3 票及以上取它）和 16 种结果的称号与一句话点评。改题或改文案只改这个文件，题目要和 `whale-video-kit/project/experiments/mbti/quiz.py` 保持一致（视频里她的实测结果用的就是这 20 题）。
- `core.js`：计分、粘贴答案解析、给大肥鱼的提示词、显示名清洗。解析只认 A/B 和常见分隔符（支持连写、空格、逗号、`1.A 2.B` 带题号），其它字符一律拒绝；显示名去掉控制字符和尖括号、最多 12 字，页面只用 `textContent` 显示。测试：`tests/test_mbti_quiz.py`（需要 Node）。
- `template.html` / `style.css` / `app.js`：页面本体，风格和主页（`../home/`）一致：同一套配色、顶栏（番外高亮）、手机底部 tab、页脚。`style.css` 复制主页的设计变量，改主页配色时要同步。
- `build_mbti.py` 把 html/css/js/题库内联成一个约 34 KB 的 `index.html`，另外输出：`hand.woff`（主页同款马善政手写体，按本页用字子集化，约 235 KB，需要 fonttools）、`img/ui-*.webp`（头像和两张表情，取自 `../home/assets/`，不内联以免重复）、`img/<类型>.webp`。手写体里的拉丁字母（E/I）长得像数字，所以标题里的 E/I 用 `.lat` 改回系统字体。
- `assets/types-cut/<类型>.webp`：同一批图去掉米色底、描白边的透明版（`cutout.py` 生成，换图时重跑）。番外页「表情包免费领」（`home/build_home.py` 的 `mbti_stickers()`）和下面的 zip 用的都是它。
- `whale-mbti-16.zip`：打包时把 16 张透明底表情打成一个包放在 `/mbti/`，首页「打包下载」用；首页展示全部 16 张（带类型和称号）。
- `assets/types/<类型>.webp`：16 张鲸鱼娘 Q 版 MBTI 角色图（主人 2026-11-03 提供的 `whale_mbti_chibi_16.zip`，1024 缩成 480 的 webp，共约 500 KB）。打包时复制到 `<out>/mbti/img/`，页面出结果时才按类型加载那一张，路径写死为 `/mbti/img/<类型>.webp`，所以必须挂在站点的 `/mbti/` 下。16 种称号已按画面改过（INFJ 绿袍贤者、ENFJ 守护骑士、ISFJ 小护士鲸等）。

```bash
python amnesty-site/mbti/build_mbti.py                 # 输出到 amnesty-site/mbti/dist/mbti/index.html（已被 .gitignore）
python amnesty-site/mbti/build_mbti.py --out <目录>     # 输出到 <目录>/mbti/index.html，挂在站点的 /mbti/ 下
```

本地预览：`.claude/launch.json` 里的 `mbti-page`（端口 3017，访问 `/mbti/`）。

**打包已接入、部署未做**：`refresh.py` 在主页之后会调用 `build_mbti.py`，输出到 `amnesty-site/dist/mbti/`。网站仓库（公开的 `site` remote）还没有推送，需主人看过预览同意后，按主页上线时的做法用独立 worktree 只放网站文件。
