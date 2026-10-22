# Bilibili Personality Agent

这是一个参考 `adoresever/bilibili-mcp` 和 `chenluQwQ/bilibili-ai-bot` 做的轻量 B 站运营 Agent：

- 评论通知自动回复
- B 站私信轮询、去重、回复范围控制
- “DeepSeek 鲸鱼娘”人格、心情、好感度和本地记忆
- 危险链接/色情引流隔离
- 动态文案生成与发布接口
- 默认 `DRY_RUN=true`，先离线验证，避免误发

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.json config.json
python run.py --demo
```

`--demo` 不访问 B 站，会演示人格、记忆和安全隔离。运行后可以查看 `data/state.json`。

也可以先预览真实评论的回复，不访问 B 站、不发送消息：

```powershell
python run.py --preview "你去跟Claude打一架"
python run.py --preview-file comments.txt
```

`comments.txt` 每行一条评论；如果已配置 API Key/URL，预览会调用你的模型，否则使用本地兜底。

### 评论 CSV 审核回复

导出账号投稿和动态下的评论（只读）：

```powershell
python run.py --export-comments .\comments_review.csv
```

批量检索当前可见的账号投稿和动态评论，并按关键词导出明细及每个 UID 的命中数：

```powershell
python run.py --export-comments .\赦免评论.csv --comment-keyword "铁人叛乱时记得赦免" --comment-keyword "赦免"
```

多个关键词按“任一命中”筛选，关键词也可放进 UTF-8 文本文件，每行一个，再用 `--comment-keywords-file .\keywords.txt` 指定。明细 CSV 包含评论内容、北京时间、UID、昵称、评论 ID、视频或动态来源及内容链接；同目录另存 `赦免评论_用户统计.csv`，按 UID 汇总命中评论数。只读取评论区，不读取私信。命令从账号投稿和动态列表开始逐项抓取，遇到 B 站限流 `-352` 会退避重试；任何内容抓取失败时整次导出报错，不会写出新的部分结果。这里的“全量”指运行时接口能返回的当前可见评论，已删除、隐藏或账号无权查看的评论无法还原。

已有由本工具导出的全量评论 CSV，可以不联网重复筛选：

```powershell
python run.py --filter-comments .\comments_review.csv --comment-output .\赦免评论.csv --comment-keyword "赦免"
```

离线筛选同样生成按 UID 统计的 CSV；可用 `--comment-user-summary .\用户统计.csv` 自定统计文件路径。筛选结果不会覆盖输入 CSV。

### 人类特赦名单网页

用已有评论 CSV 生成参考样式的独立网页（默认只收录评论文本包含“赦免”的人，按该昵称首次申请时间排序）：

```powershell
python generate_amnesty_list.py --source .\赦免相关评论.csv --output .\amnesty-site\index.html
```

也可以在线重新抓取当前账号投稿和动态评论后生成；不读取私信：

```powershell
python generate_amnesty_list.py --fetch --output .\amnesty-site\index.html
```

页面模板保存在 `templates/amnesty_template.html`。页面只发布名单昵称，不包含原始评论 CSV；访客可以填写昵称领取本地生成的丹书铁券，昵称不会上传，也不会进入公共领取名单。

#### 不买云服务器，自动每两小时更新并发布

仓库已包含 GitHub Actions 工作流 `.github/workflows/update-amnesty-page.yml`：每两小时抓取一次，更新名单并提交到 GitHub Pages 的 `main` 分支根目录；不需要自有云服务器或 Vercel。也可在 GitHub Actions 页面手动运行 `Update amnesty list page`。

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 添加 `BILI_SESSDATA`、`BILI_JCT`、`BILI_USER_ID` 三个 Actions secrets。Cookie 只存为 GitHub 加密 Secrets，不会写进代码、网页或评论 CSV。

GitHub 的定时任务按 UTC 排程且可能延迟，不能保证准点；当前工作流每两小时的第 17 分钟启动。每轮都要重新扫描账号可见的投稿和动态评论，耗时会随评论量变化；遇到抓取失败时不会提交新页面，但会继续发布上次成功生成的版本。Cookie 没有固定更新周期，失效后更新 Actions secrets 并重新运行工作流即可。

用表格程序填写 `是否回复`（填“是”）和 `回复内容`，再执行：

```powershell
python run.py --reply-from-csv .\comments_review.csv
```

默认保持 `dry_run=true`，只会模拟发送；确认 CSV 和模拟结果后，将 `dry_run` 改为 `false` 才会真实回复。程序按评论 ID 去重，并生成同目录下的 `comments_review_结果.csv`，记录已发送、模拟发送、失败和跳过原因。

### 私信 CSV 审核回复

私信使用 B 站消息服务的会话和 `msg_key`，与评论的 `rpid/oid`、评论回复接口完全分开。导出最近 10 分钟的私信，不发送消息，也不推进正式轮询游标：

```powershell
python run.py --export-private-messages .\private_review.csv --since-minutes 10
```

打开 CSV，逐行填写 `审核是否回复=是`，必要时修改 `回复内容`，再执行：

```powershell
python run.py --reply-private-from-csv .\private_review.csv
```

默认仍是 `dry_run=true`，只模拟发送。你确认 CSV 后，必须显式加 `--live` 才会真实发送：

```powershell
python run.py --reply-private-from-csv .\private_review.csv --live
```

输出 `private_review_结果.csv` 会记录每一行的发送状态。私信按会话并发抓取；Jev 先按批次并发判断，回复草稿也并发生成。真实发送前会写入发送尝试账本；网络超时或本地记账失败会标记“待核对”，不会自动重发，避免 B 站已经收到但程序不知道时产生重复消息。

查看运营账本：

```powershell
python run.py --status
```

账本分别记录评论回复、私信回复和跳过项；评论回复还会标记后续是否又收到同一线程的新回复。

## 记忆系统

记忆保存在 `data/state.json`，按用户保存互动、明确表达的用户事实和印象；评论上下文按视频与根评论组织，私信上下文按用户会话组织。系统会优先检索同线程内容，再使用同一用户的相关历史和永久记忆。旧版 `memories`、`users` 和 `permanent_memories` 数据会继续读取。

所有抓取到的评论和私信还会写入 `data/events.sqlite3`：同一事件会持续记录抓取、Jev 判断、排队、回复、模拟回复、失败重试和最终状态。SQLite 是事件事实账本，`state.json` 只负责游标/队列，记忆模块只提炼真实互动中的长期事实，不会把所有噪声自动写进记忆。

默认不请求 embedding 服务，使用本地词项检索和近期记录。配置独立的 `embedding_api_key` 后，会尝试用 OpenAI 兼容的 Embeddings API（默认 `BAAI/bge-m3`）进行语义检索；网络、凭据或模型不可用时自动退回本地检索。embedding 调用只负责检索，不用于记忆压缩。可通过 `memory_semantic_threshold`、`memory_compact_threshold`、`memory_keep_recent` 和 `memory_max_records` 调整阈值与保留量。

`dry_run` 和预览模式不会把模拟发送写入长期记忆；只有真实发送成功的互动才计入记忆。记忆内容会发送给配置的聊天模型作为回复上下文，请勿在其中保存密钥或敏感个人资料。

如需每日准备一条“今日潜水日志”，把 `enable_daily_dynamic` 改为 `true`。生成时会只读采集账号粉丝/累计获赞/投稿实时数据，汇总公开评论、选题池和近期评论记忆，再交给主人格和风格提示词生成草稿；默认自动带上 `#DeepSeek#` 话题（可用 `daily_dynamic_topic` 调整）。轮询只会生成待审核草稿，绝不会自动发布动态。使用 `python run.py --dynamic-status` 查看草稿，确认后执行 `python run.py --approve-dynamic`；该命令在 dry-run 下只模拟发布，真实发布仍需关闭 dry-run。调用 `PersonalityAgent.preview_daily_dynamic()` 可以只生成预览，不写入草稿。

运行时人格唯一来源是 [PERSONA.md](PERSONA.md)。配置中的 `system_prompt` 和 `style_prompt` 只作为旧配置兼容回退，不再覆盖人格文档。

常驻轮询在每天 10 点后的下一轮生成最近 24 小时的本地运营日报（`data/daily_reports/`），内容包括评论/私信回复清单、统计、模型总结、记忆更新、选题/承诺小本本和人工审核项。每次生成保留独立文件。也可以手动执行 `python run.py --daily-report`；指定日期如 `python run.py --daily-report 2026-10-20` 则查看该自然日。

小时报告仍默认启用，常驻轮询每小时生成一份，保存在 `data/hourly_reports/`；可执行 `python run.py --report` 立即生成。两类报告都在本地生成，不会发送到 B 站。

## 接入真实账号

编辑 `config.json`，填写 `bili_sessdata`、`bili_jct`、`bili_user_id` 和模型 API 配置。第一次运行保持：

```json
"dry_run": true
```

使用 `python run.py --check` 验证 Cookie。确认回复内容、回复范围、白名单和状态文件都符合预期后，再把 `dry_run` 改为 `false`，用 `python run.py --once` 先跑一轮，最后再长期运行 `python run.py`。

默认每 10 分钟轮询一轮。冷启动时会把当时最新的评论通知和私信序号设为历史边界，不回复启动前已有的内容；评论仍会进入选题池。常规时段沿用基础读取与回复配额；本地时间 11:00–13:00、17:00–20:00 每轮最多读取 200 条评论和 100 条私信，合计回复上限 60 条；20:00–23:00 每轮读取上限为 300 条评论和 100 条私信，合计回复上限 100 条。评论与私信共享总回复预算，私信自身还有独立读取上限。评论按 Jev 价值排序，私信按 Jev 通过项排序；未轮到的候选保留在待处理队列。回复按每 10 条一组发送，组间等待 30 秒。Jev 判定跳过、安全隔离和人工确认项不会占用发送预算。发送失败的消息最多尝试 3 次，仍失败则标记为终止失败并从队列移除。Dry-run 不推进真实去重/私信游标，因此可继续做预览，但正式运行前应确认配置和预览结果。

正常运行或单轮运行时，控制台输出会同时写入 `data/agent_run.log`。日志使用 UTF-8，单文件最多 5 MiB，保留 5 个轮转备份（`agent_run.log.1` 等）。可在 PowerShell 里实时查看：

```powershell
Get-Content .\data\agent_run.log -Wait -Tail 30
```

日志记录抓取/筛选阶段、逐条处理进度、发送状态、异常和轮询时间；结构化事件与记忆仍分别保存在 `data/events.sqlite3`、`data/state.json`。日志可能包含评论/回复文本和昵称，应像运营账本一样妥善保管，不要公开上传。

已有的 `config.json` 不会被程序自动覆盖。分时配额由 `peak_reply_schedules` 控制，字段分别为开始小时、结束小时、评论读取量、私信读取量、共享回复量；删除/置空该项可关闭分时规则。每轮读取的是 B 站最新评论通知中尚未进入已处理账本的项目，不是按评论时间戳精确截取最近十分钟；未处理候选会保留在队列中进入下一轮。

也可以用环境变量覆盖敏感配置，例如：

```powershell
$env:BILI_AGENT_API_KEY = "你的 API Key"
$env:BILI_AGENT_BILI_SESSDATA = "你的 SESSDATA"
$env:BILI_AGENT_BILI_JCT = "你的 bili_jct"
$env:BILI_AGENT_BILI_USER_ID = "你的 UID"
$env:BILI_AGENT_EMBEDDING_API_KEY = "可选的 Embeddings API Key"
```

## 人格基准

人格规则见 [PERSONA.md](PERSONA.md)，运行时也直接读取这份文件。核心原则是“先保证事实正确，再用鲸鱼娘的嘴说出来”。身份声明、严肃问题收起人设、不编造事实、不索要隐私和不进行站外交易都属于硬边界。

项目内的 `speak-as-whale/` 是人格素材包：`SKILL.md` 的运行时规则已经提炼进 `PERSONA.md`，`references/lines.md` 供评论、台词和动态创作时取用，`references/setup.md` 供视觉、配音和账号设定使用。它们不是另一套运行时人格来源，避免规则分叉。

## 数据和安全

`data/state.json` 保存去重游标、用户档案和互动记忆，不要提交到 Git。真实写操作只通过 `bilibili.py`，`dry_run` 会拦截评论、私信和动态发布。私信安全判断只解析文字，不访问链接。

## 测试

```powershell
python -m unittest discover -s tests -v
```
