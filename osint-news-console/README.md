# OSINT 新闻控制台

个人新闻聚合控制台：RSS 采集、原文保守压缩、可选翻译、事件聚类、多来源标记、官方来源优先、7 天自动清理和手机 PWA。

> “多来源”只表示多家独立来源报道了相似事件，不代表系统已经判定事实真伪。重要新闻仍需打开原文核对。

## 当前能力

- 按来源设置采集频率：军事 5 分钟、重点政治/财经 10—15 分钟、其他 15—30 分钟
- 并发采集 RSS，按 URL 去重，并使用 ETag / Last-Modified 避免重复下载
- 来源新鲜度检测：HTTP 200 但长期没有新条目时标记为“已过时”
- Google News 聚合条目保留原始媒体名；官方域名索引与媒体报道分开标记
- 默认本地规则模式不调用 AI：保留标题中的人物/地点/动作，并按完整句压缩到 250 字以内
- 外文默认保留原文且不伪装成翻译；需要自动翻译时可选本地 Ollama 或 DeepSeek
- 相似标题事件聚类，显示独立来源数量和来源名称
- 官方来源标记与优先展示
- 可解释评分：来源、交叉报道、时效、内容完整度
- 首页每 60 秒静默刷新，并显示发布时间、采集时间与采集延迟
- 首页、详情、来源状态、近 7 天统计和 HTML 日报统一按北京时间展示
- 深色控制台布局；首页市场卡片支持吸顶、双页滑动和整卡进入独立市场页面
- 市场页面提供交互式分时曲线、事件节点、成交量、板块排行和热力图
- SQLite 数据保留 7 天，旧数据库自动补充新版字段
- 管理接口令牌保护，RSS 内容生成日报前进行 HTML 转义
- Windows 公网试跑使用 8 位设备码：未授权设备无法读取页面或 API

> 市场页面当前使用前端内置演示数据，并在界面中标记“演示数据 · 非实时”。行情采集接口尚未接入，不能把示例数值用于投资判断。

## 本地运行

后端（Python 3.12+）：

\`\`\`bash
cd osint-news-console
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --port 8000
\`\`\`

前端：

\`\`\`bash
cd osint-news-console/frontend
npm ci
npm run dev
\`\`\`

浏览器打开 \`http://localhost:5173\`。前端开发代理固定连接后端 \`8000\` 端口。

Windows 试跑包通过 \`start-local.bat\` 启动时会在命令窗口显示本次 8 位设备码。公网设备第一次访问需要输入设备名称和设备码；本机 \`127.0.0.1\` 免验证。授权令牌只保存 SHA-256 哈希，连续输错 5 次会按公网 IP 限制 24 小时。

本机打开 \`http://127.0.0.1:5173/device-admin\` 可以把已配对设备改为永久授权、改回30天、单独撤销、全部撤销或解除登录限制。永久授权不会由服务端自动过期，但清除浏览器 Cookie、更换浏览器或手动撤销后仍需重新配对。

由于免费 Quick Tunnel 每次启动都会更换公网域名，新地址通常需要重新输入设备码。设备码是浏览器配对机制，不是不可伪造的硬件序列号；正式长期公网运行仍建议叠加 Cloudflare Access。

### 固定公网网址（可选）

Cloudflare Tunnel 本身可以使用免费方案。程序最初使用的也是免费 Quick Tunnel，但它生成的是随机 `*.trycloudflare.com` 临时地址，每次重启都会变化。下面的 Named Tunnel 同样不必单独购买 Tunnel 服务，不过需要一个已接入 Cloudflare、由你控制的域名；如果没有域名，域名注册通常仍会产生费用。

1. 在 Cloudflare 控制台创建 remotely-managed Tunnel。
2. 为 Tunnel 添加 Public Hostname，例如 \`news.example.com\`，服务地址填写 \`http://127.0.0.1:5173\`。
3. 在 Cloudflare 的“Add a replica”中复制 \`eyJ...\` Tunnel Token。
4. 运行 \`configure-fixed-url.bat\`，输入固定 HTTPS 网址并粘贴 Token。
5. 重新启动 \`start-local.bat\`。

程序使用 \`cloudflared tunnel run --token-file\`，Token 不出现在进程命令行中，并保存在已被 Git 忽略的 \`backend/data\`。任何拿到 Tunnel Token 的人都能运行该隧道，因此不要上传、截图或分享 Token；需要取消固定网址时再次运行配置脚本并把网址输入为 \`REMOVE\`。

## Docker 部署

1. 在项目目录创建 \`.env\`，设置一个随机管理令牌：

\`\`\`dotenv
ADMIN_TOKEN=请替换为至少32位随机字符串
\`\`\`

2. 启动服务并拉取 Ollama 模型：

\`\`\`bash
docker compose up ollama -d
docker exec -it osint-ollama ollama pull qwen2.5:7b
docker compose up -d
\`\`\`

3. 打开 \`http://localhost:8080\`。

如果机器没有适合运行本地模型的内存或 GPU，可在 \`docker-compose.yml\` 中把 \`AI_MODE\` 改成 \`deepseek\`，并通过环境变量提供 \`DEEPSEEK_API_KEY\`。不要把真实密钥提交到仓库。

## 配置

主要配置位于：

- \`config.yaml\`：时区、AI、采集、清理、评分、聚类阈值
- \`sources.yaml\`：新闻源、分类、可信度、是否官方、采集频率、新鲜度阈值

来源状态不是“事实核验”结论：\`新鲜\` 只表示 RSS 最近仍有更新；\`已过时\` 表示最新条目超过该源配置的 \`stale_after_hours\`。Google News 仅作为无稳定 RSS 网站的发现/索引层，重要内容仍应打开原始链接核对。

同类开源项目与后续取舍见 [GitHub 同类项目调研](docs/SIMILAR_PROJECTS.md)。

环境变量优先于 YAML。常用变量：

| 变量 | 作用 |
|---|---|
| \`APP_TIMEZONE\` | 业务时区，默认 \`Asia/Shanghai\` |
| \`AI_MODE\` | \`mock\` / \`ollama\` / \`deepseek\` |
| \`OLLAMA_HOST\` | Ollama 服务地址 |
| \`DEEPSEEK_API_KEY\` | DeepSeek 密钥 |
| \`DATABASE_PATH\` | SQLite 文件路径 |
| \`ADMIN_TOKEN\` | 管理接口令牌 |
| \`CORS_ORIGINS\` | 逗号分隔的允许来源 |

## 管理接口

以下写操作需要请求头 \`X-Admin-Token\`。未设置 \`ADMIN_TOKEN\` 时接口默认关闭：

- \`POST /api/admin/collect\`
- \`POST /api/admin/process-ai\`
- \`POST /api/admin/score\`

示例：

\`\`\`bash
curl -X POST http://localhost:8000/api/admin/collect \
  -H "X-Admin-Token: 你的令牌"
\`\`\`

## 验证

\`\`\`bash
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend pytest -q backend/tests
cd frontend && npm ci && npm run build
\`\`\`

API 文档：\`http://localhost:8000/docs\`
