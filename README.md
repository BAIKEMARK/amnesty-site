# Day 3 人类特赦名单

在线页面：<https://baikemark.github.io/amnesty-list/>

页面由 `generate_amnesty_list.py` 根据账号可见的 B 站投稿和动态评论生成，不读取私信。GitHub Actions 每两小时抓取一次并直接部署到 GitHub Pages，不需要自有服务器。

## 配置

在仓库的 **Settings → Secrets and variables → Actions** 添加：

- `BILI_SESSDATA`
- `BILI_JCT`
- `BILI_USER_ID`

Cookie 仅存放在 Actions Secrets，不要提交到仓库。登录凭据没有固定有效期；B 站可能因退出登录、安全验证或风控提前使它失效。失效后更新 Secrets，再从 Actions 手动运行工作流。抓取失败时不会覆盖上次成功发布的页面。

工作流按 UTC 的偶数小时第 17 分启动，GitHub 定时任务可能延迟。每轮重新扫描当前接口可见的评论，耗时随评论量变化。

## 自助领取

访客可以输入昵称生成丹书铁券，并下载 PNG 或打印成 PDF。昵称和签发号只在该访客浏览器中生成，不会上传，也不构成公共领取记录。
