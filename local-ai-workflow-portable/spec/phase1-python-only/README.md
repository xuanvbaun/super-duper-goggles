# 个人 AI 工作流调度平台 · 第一阶段

安装位置：E:\AI-Workflow。双击 start.cmd 启动，然后访问 http://127.0.0.1:8765 。
关闭服务窗口或按 Ctrl+C 停止。仅绑定本机，单用户、单进程运行。

## 使用

1. 输入目标，例如“数字统计”，数据输入“10, 20, 30”，点击创建并执行。
2. 查看 REVIEW 状态、结果、自动检查和日志。
3. 填写验收说明后点击验收通过，任务才进入 DONE。
4. 输入错误时最多尝试两次，之后由你调整输入并重规划一次，再点击执行当前方案。再次失败后停止。

支持目标：数字统计 / 求和 / 平均值；JSON校验 / JSON格式化；文本统计 / 字数。
分类仅为透明的关键词规则，不宣称完整理解自然语言。请把待处理内容放入输入数据框。
代码、翻译等请求会分流到对应执行器并进入 REVIEW，明确提示尚未接入。
文本统计是 Unicode 字符数、非空白字符数和行数，不是中文分词计数。

## 范围与规格冲突处理

- 遵循原规格结尾和第19节，先交付第一阶段。第25节要求的真实 AI 调用尚未满足，不代表完整 V1。
- 第20节直接 DONE 与第6、14节验收层级冲突：选择先 REVIEW，人工代行总控，再 DONE。
- 第二次失败进入 REVIEW，允许人工重规划一次；重规划后只有一次尝试。没有自动 AI 重规划。
- Codex / DeepSeek / ChatGPT 当前只有任务分流，无 API 调用、浏览器自动化或订阅会话集成。
- 第一阶段没有用户文件写入、删除或任意代码执行；高风险操作不能通过页面批准后执行。

## 数据与追踪

SQLite：data/app.db。交接：tasks/<task_id>/task.json、result.json、logs/events.json。
SQLite 是事实来源。文件副本采用临时文件替换；数据库和文件不是跨介质事务。
任务事件保留状态变化与失败原因。输入数据会保存在本机任务记录，请勿输入密钥。
程序重启时 RUNNING / VERIFYING 转 REVIEW，避免重复执行。
本地接口有 Host、Origin 和客户端标识校验；不是对抗同机恶意程序的认证系统。
应用仅支持一个服务进程，勿用多个 worker 或同时启动多个实例。

## 开发与测试

Python 环境在 .venv，基础解释器来自这台电脑的 Codex Python 运行时；迁移电脑需要重新建立虚拟环境。
依赖见 requirements.txt。测试：双击 test.cmd，或 `.venv\Scripts\python.exe -m unittest discover -s tests -v`。
API 文档：运行后访问 /docs；POST 请求需头部 X-Workflow-Client: local-ui。
根目录保留原始 PROJECT_SPEC.md，AGENTS.md 是后续 Codex 执行入口。

下一阶段：在明确授权且配置 DeepSeek API Key 后，实现真实文本执行器及响应验证；随后接入代码仓库执行器。
