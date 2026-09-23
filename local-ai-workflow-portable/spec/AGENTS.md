# Codex 执行入口

先阅读：
1. PROJECT_SPEC.md
2. ROUTER_V1_SPEC.md
3. GLOBAL_RULES.md
4. ../README.md

当前用户已明确批准进入“多 AI Router V1”设计/开发阶段。与旧范围冲突时，以 ROUTER_V1_SPEC.md 为本阶段范围依据；PROJECT_SPEC.md 未冲突内容继续有效。

当前第一阶段只实现 ROUTER_V1_SPEC.md 第17节“路由骨架”：
- Router 数据结构与复杂度分级
- 硬规则路由
- Provider Registry
- Python 适配
- DeepSeek/MiMo/Codex/GPT Stub Provider
- 状态机
- 人工改派
- 高风险 WAITING_USER
- Retry/Fallback 框架
- Verifier 接口
- 单元测试

不要一次性接满真实外部 API，不引入浏览器自动化，不写入任何密钥，不改坏现有已验证数字统计流程。

修改前查看现有实现与 Git diff。每阶段运行：
`python -m unittest discover -s tests -v`
并运行所有与 Router 新增功能相关的测试。

不得删除用户数据或提交 .env、data、tasks、.venv。

输出本轮：
- 完成内容
- 修改文件
- 测试结果
- 未完成内容
- 发现的问题
- 下一步建议

执行完成，等待验收。
