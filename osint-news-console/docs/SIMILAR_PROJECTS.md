# GitHub 同类项目调研

调研时间：2026-08-19。当前项目定位是“小型、Windows 可直接运行的个人新闻控制台”，不建议整套替换为大型阅读器；更合适的做法是吸收成熟项目的机制。

| 项目 | 值得借鉴的能力 | 对当前项目的处理 |
|---|---|---|
| [FreshRSS](https://github.com/FreshRSS/FreshRSS) | 成熟的自托管订阅管理、WebSub、网页抓取和用户认证 | 后续需要账号体系或网页抓取时参考 |
| [Miniflux](https://github.com/miniflux/v2) | ETag / Last-Modified 条件请求、抓取规则、全文提取、REST API | 已加入条件请求；全文提取可作为下一阶段 |
| [RSSHub](https://github.com/DIYgod/RSSHub) | 把没有 RSS 的网站转换成标准订阅源，路由覆盖面大 | 保留私有 RSSHub 接入口；不依赖不稳定的公共实例 |
| [NewsNow](https://github.com/ourongxing/newsnow) | 热点聚合、按来源更新速度调整缓存/抓取频率 | 已按军事、重点政治财经、普通来源分层轮询 |
| [Folo](https://github.com/RSSNext/Folo) | AI 翻译、摘要、多平台阅读体验 | 真实 AI 模式继续负责外文转中文和摘要 |
| [GPT Newspaper](https://github.com/rotemweiss57/gpt-newspaper) | 搜索、编辑、审校、排版的多代理新闻生产流程 | 适合作为实验思路，不适合当前轻量本地版本直接引入 |

## 本轮已经吸收

1. 来源按 5 / 10 / 15 / 30 分钟分层轮询。
2. 支持 ETag 和 Last-Modified，来源未变化时避免重复下载。
3. 增加 RSS 内容新鲜度判断：HTTP 200 但最新条目超期时显示“已过时”。
4. 聚合源保留条目中的原始媒体名称。
5. 首页每 60 秒静默刷新，并显示发布时间、采集时间和采集延迟。

## 下一阶段建议

1. 部署私有 RSSHub，替换 Google News 索引层中最重要的官方站点。
2. 将来源健康状态持久化，增加 24 小时成功率和连续失败告警。
3. 增加全文抓取与正文哈希去重，减少“同稿不同链接”。
4. 公网长期使用前增加 Cloudflare Access 或应用登录，不再依赖无密码的临时隧道。
