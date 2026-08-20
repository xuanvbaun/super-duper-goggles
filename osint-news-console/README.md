# OSINT 新闻控制台

个人新闻聚合控制台：RSS 采集、中文 AI 摘要、事件聚类、多来源标记、官方来源优先、7 天自动清理和手机 PWA。

> “多来源”只表示多家独立来源报道了相似事件，不代表系统已经判定事实真伪。重要新闻仍需打开原文核对。

## 当前能力

- 按来源设置采集频率：军事源 5 分钟，普通源 30 分钟
- 并发采集 RSS，按 URL 去重
- Mock / Ollama / DeepSeek 三种处理模式
- 中文摘要不超过 250 字；真实 AI 模式会把外文简讯整理为中文
- 相似标题事件聚类，显示独立来源数量和来源名称
- 官方来源标记与优先展示
- 可解释评分：来源、交叉报道、时效、内容完整度
- 首页、详情、来源状态、近 7 天统计和 HTML 日报
- SQLite 数据保留 7 天，旧数据库自动补充新版字段
- 管理接口令牌保护，RSS 内容生成日报前进行 HTML 转义

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
- \`sources.yaml\`：新闻源、分类、可信度、是否官方、采集频率

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
