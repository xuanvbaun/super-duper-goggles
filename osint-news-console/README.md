# 📰 OSINT 新闻控制台

个人轻量开源情报新闻聚合控制台 — 手机优先 · AI 辅助 · 零成本运行

## 核心原则

- **RSS 优先**：不使用爬虫，仅通过 RSS + 官方 API 采集
- **AI 仅辅助**：摘要、分类、标签提取。禁止推测、评论、立场输出
- **数据 7 天自动清理**：不堆积数据
- **单体架构**：不引入微服务、Kubernetes
- **手机优先**：PWA 添加到主屏幕，离线可用
- **低成本**：Oracle Cloud Free Tier 永久免费，月成本 0~10 元

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | Vue 3 + Vite + VitePWA | 报纸风格 UI，响应式 |
| 后端 | Python FastAPI | 异步、单体、自动 API 文档 |
| AI | Ollama + Qwen2.5 | 本地推理，7B 量化模型 |
| 数据库 | SQLite（可迁 PostgreSQL） | WAL 模式，单文件 |
| 采集 | feedparser + APScheduler | RSS 定时采集 |
| 部署 | Docker Compose + Caddy | 一键部署 |

## 快速开始

### 本地开发（不需要 Docker）

```bash
# 终端 1：后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 终端 2：前端
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`

前端开发环境需要 Node.js 18 或更高版本。后端测试可在 `backend` 目录运行：

```bash
python -m unittest discover -s tests -v
```

### Docker 部署（生产环境）

```bash
# 1. 拉取 AI 模型（仅首次）
docker compose up ollama -d
docker exec -it osint-ollama ollama pull qwen2.5:7b

# 2. 启动全部服务
docker compose up -d

# 3. 访问
# http://localhost:8080
```

## 项目结构

```
├── docker-compose.yml      # 容器编排
├── Caddyfile               # 反向代理 + HTTPS
├── config.yaml             # 主配置（AI模式/采集间隔/清理策略）
├── sources.yaml            # RSS 源列表（可信度分档）
├── backend/                # FastAPI 后端
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py         # 入口 + 生命周期
│       ├── collector.py    # RSS 采集 + 调度
│       ├── ai_processor.py # AI 摘要（Mock/Ollama/DeepSeek）
│       ├── rule_engine.py  # 可信度评分 + 7天清理
│       └── ...
├── frontend/               # Vue 3 前端
│   ├── Dockerfile
│   └── src/
│       ├── views/          # Home / Detail / Stats
│       └── style.css       # 报纸主题
└── data/                   # SQLite 数据库（git ignore）
```

## 配置说明

### AI 模式切换

编辑 `config.yaml` 的 `ai.mode`：

| 值 | 用途 | 需要 |
|----|------|------|
| `mock` | 开发调试 | 无依赖 |
| `ollama` | 本地推理 | `ollama pull qwen2.5:7b` |
| `deepseek` | 云端备用 | DeepSeek API Key |

环境变量优先于 `config.yaml`。常用变量包括 `AI_MODE`、`OLLAMA_HOST`、`OLLAMA_TIMEOUT`、`DEEPSEEK_API_KEY`、`SERVER_PORT` 和 `DATABASE_PATH`。

### 添加 RSS 源

编辑 `sources.yaml`：

```yaml
- name: "示例源"
  url: "https://example.com/rss"
  category: "科技"
  credibility: 4      # 1-5
  enabled: true
```

## 许可证

个人项目，自用为主。
