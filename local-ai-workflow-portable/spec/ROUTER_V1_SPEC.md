# AI Router V1 技术规格

> 适用目录：`local-ai-workflow-portable/`
>
> 目标：在现有 n8n + Python Executor 基础上，增加“统一任务入口 → Router → n8n → Provider/Tool → Verifier → 人工干预”的第一版多 AI 调度能力。
>
> 本规格优先级高于 PROJECT_SPEC.md 中与“当前仅第19节/暂不增加 AI 接入”冲突的旧范围描述；未冲突部分继续有效。

## 1. V1 目标

V1 不追求一次接入所有 AI，而是先跑通一个稳定闭环：

```text
用户提交任务
  ↓
Router 分类：任务类型 / 复杂度 / 风险 / 所需工具
  ↓
给出推荐执行者
  ↓
用户可人工改派
  ↓
n8n 编排
  ↓
Provider / Python / Codex 执行
  ↓
Verifier 自动验证
  ↓
必要时重试 / 升级 / 人工确认
  ↓
DONE / FAILED / CANCELLED
```

V1 首批执行者：

- Python：确定性任务
- DeepSeek：低成本文本、分类、摘要、结构化、普通推理
- MiMo：长上下文、多步骤、Agent 型任务
- Codex：代码仓库、修改代码、测试、工程任务
- GPT：复杂规划、冲突裁决、L3/L4 升级、最终复核

说明：这里的 `GPT` 是统一 Provider/监督角色。程序化调用需通过合法可用的 OpenAI API/Provider；不得假定 ChatGPT App 本身自动暴露可编程接口。

## 2. V1 明确不做

第一版不做：

- Claude / Gemini 正式接入
- 浏览器网页代理正式接入
- 多用户
- 云端部署
- 本地大模型
- 自动付款或自动购买额度
- 完全无人值守
- 自动执行不可逆高风险操作

但 Provider 接口必须允许未来增加：

```text
ClaudeProvider
GeminiProvider
ChatGPTWebProvider
DeepSeekWebProvider
BrowserProvider
```

## 3. 总体架构

```text
统一聊天 / 任务入口
        ↓
      Router
        ↓
   RoutingDecision
        ↓
   人工改派（可选）
        ↓
       n8n
        ↓
 ┌──────┼─────────────┐
 ↓      ↓             ↓
AI   Codex          Python
 ↓      ↓             ↓
 └──────┴──────┬──────┘
               ↓
            Verifier
               ↓
      Retry / Escalation
               ↓
      Human Confirmation
               ↓
        DONE / FAILED
```

职责边界：

- Router：决定“谁做、为什么、风险是什么”，不负责真正执行。
- n8n：负责流程编排、分支、等待、人工确认、调用执行器。
- Provider：统一封装不同模型/API。
- Python Executor：确定性执行。
- Codex Adapter：代码工程任务。
- Verifier：验证客观结果。
- 人工：只在关键节点介入。

## 4. 复杂度分级

### L1 简单

特征：

- 单一步骤
- 不需要多个工具
- 低风险
- 输出格式明确
- 不需要复杂权衡

示例：翻译、摘要、简单分类、格式转换。

默认：DeepSeek / Python。

### L2 普通

特征：

- 2～5 个步骤
- 可能需要 1～2 个工具
- 需要自动验证
- 风险低到中等

示例：批量 Excel 处理、结构化提取、普通代码检查。

默认：Python / DeepSeek / MiMo / Codex，按任务类型决定。

### L3 复杂

任一条件满足即可升级：

- 需要多个工具或多个 Provider
- 跨多个文件/仓库模块
- 需要方案权衡
- 输入信息存在明显不确定性
- 需要长上下文
- 单模型结果不足以可靠验收
- 失败代价明显

默认：MiMo / Codex + GPT 参与规划或验收。

### L4 高风险 / 高不确定

任一条件满足即可：

- 删除、覆盖、批量修改重要数据
- 修改生产数据库/生产配置
- 修改密钥/凭据
- force push / 重写 Git 历史
- 对外发送消息、邮件、发布内容
- 金钱/购买/账户权限动作
- Router 无法可靠理解目标
- 多模型结果严重冲突且无法自动裁决

默认：GPT/总控分析 + 人工确认。不得自动直接执行高风险动作。

## 5. Router 判断顺序

Router 必须遵循“规则优先、AI 兜底”。

### 第一层：硬规则

优先判断：

1. 能否确定性完成？
   - 是 → Python
2. 是否主要是代码仓库任务？
   - 是 → Codex
3. 是否为大量、重复、低风险文本任务？
   - 是 → DeepSeek
4. 是否明显需要长上下文、多步骤 Agent？
   - 是 → MiMo
5. 是否 L3/L4、需要综合判断、存在冲突？
   - 是 → GPT/总控升级
6. 无法判断？
   - 进入轻量分类器

### 第二层：轻量 AI 分类器

分类器只负责输出结构化路由建议，不执行任务。

必须输出：

```json
{
  "task_type": "software_debugging",
  "complexity": "L3",
  "risk": "medium",
  "recommended_executor": "codex",
  "fallback_executor": "gpt",
  "tools": ["github", "python"],
  "requires_verification": true,
  "requires_human_confirmation": false,
  "reason_codes": ["CODE_REPO", "MULTI_STEP"]
}
```

禁止分类器直接返回自由文本作为唯一决策依据。

## 6. 人工干预点

V1 只保留三个主要人工干预点。

### 6.1 改派执行者

任务进入执行前，界面显示：

```text
推荐：MiMo
复杂度：L2
风险：低
原因：长上下文 + 多步骤
```

用户可选择：

- 按推荐执行
- 改为 DeepSeek
- 改为 MiMo
- 改为 Codex
- 改为 GPT
- 改为 Python

用户手动选择具有最高优先级，但仍受安全策略约束。

### 6.2 高风险动作确认

高风险动作必须进入 `WAITING_USER`。

确认内容必须包含：

- 将执行什么
- 会修改什么
- 是否可恢复
- 影响范围
- 推荐备份/回滚方式

用户确认后才允许继续。

### 6.3 失败后接管

失败后提供：

- 停止
- 同模型重试
- 换备用模型
- 转 GPT
- 改派其他执行者
- 人工完成/关闭任务

## 7. 统一任务对象

任务事实来源仍为 SQLite；JSON 为可重建交接副本。

建议 V1 任务对象：

```json
{
  "task_id": "TASK-0001",
  "goal": "",
  "task_type": "",
  "complexity": "L1",
  "risk": "low",
  "inputs": [],
  "constraints": [],
  "expected_outputs": [],
  "recommended_executor": "",
  "selected_executor": "",
  "fallback_executor": "",
  "tools": [],
  "status": "NEW",
  "attempt": 0,
  "max_attempts": 2,
  "requires_verification": true,
  "requires_human_confirmation": false,
  "result": null,
  "verification": null,
  "created_at": "",
  "updated_at": ""
}
```

## 8. 状态机

主路径：

```text
NEW
↓
ROUTED
↓
RUNNING
↓
VERIFYING
↓
DONE
```

辅助状态：

- WAITING_USER
- RETRYING
- FAILED
- CANCELLED

允许转换：

```text
NEW → ROUTED
ROUTED → RUNNING
ROUTED → WAITING_USER
RUNNING → VERIFYING
RUNNING → RETRYING
RUNNING → WAITING_USER
RUNNING → FAILED
RUNNING → CANCELLED
RETRYING → RUNNING
VERIFYING → DONE
VERIFYING → RETRYING
VERIFYING → WAITING_USER
VERIFYING → FAILED
WAITING_USER → RUNNING
WAITING_USER → CANCELLED
```

禁止执行器直接从 RUNNING 置为 DONE。

## 9. Provider 统一接口

每个模型 Provider 至少实现：

```text
name
capabilities
cost_tier
availability
execute(request)
healthcheck()
normalize_response()
classify_error()
```

统一请求：

```json
{
  "task_id": "TASK-0001",
  "goal": "",
  "context": [],
  "inputs": [],
  "constraints": [],
  "output_schema": {},
  "tools_allowed": [],
  "timeout_seconds": 120
}
```

统一响应：

```json
{
  "provider": "deepseek",
  "model": "",
  "success": true,
  "content": null,
  "structured_output": {},
  "usage": {},
  "error": null,
  "latency_ms": 0
}
```

Provider 不允许直接修改全局任务状态；只能返回执行结果，由 Orchestrator 统一更新状态。

## 10. Provider Registry

Router 不应写死模型名。

使用 Registry：

```text
python
deepseek
mimo
codex
gpt
```

每个 Provider 注册能力标签，例如：

```json
{
  "name": "mimo",
  "capabilities": [
    "long_context",
    "agentic",
    "text_reasoning"
  ],
  "cost_tier": "low",
  "enabled": true
}
```

未来新增 Claude/Gemini/Web Provider 时，不修改 Router 主流程，只新增 Provider 配置和能力标签。

## 11. 重试与降级

沿用全局“最多自动重试两轮”原则。

### 第一次失败

优先：

- 判断错误是否可重试
- 可重试：同 Provider 再执行一次
- 参数/格式错误：先自动修正输入，再执行一次

### 第二次失败

允许：

- 切换 `fallback_executor`
- 或升级 GPT/总控重新规划

### 再次失败

必须：

```text
FAILED
```

并记录：

- 失败位置
- 原始错误
- 已尝试方案
- 每次执行者
- 建议下一步

以下错误不得自动反复重试：

- 权限不足
- 缺少密钥
- 用户明确取消
- 高风险动作未批准
- 输入文件不存在
- 明确的额度/付款问题
- 认证失败

## 12. Verifier

不同任务使用不同验证器。

### Python / 文件

检查：

- 输出文件存在
- 文件可读取/可打开
- 原始文件未被破坏
- 目标路径正确
- 关键字段/数量符合要求

### Excel

检查：

- 工作簿可打开
- 工作表存在
- 关键列/公式/格式
- 源数据对应关系
- 行数/数量

### 代码 / Codex

检查：

- Git diff
- 测试通过
- 程序可运行
- 无明显回归
- 未修改禁止区域

### AI 文本

检查：

- JSON/Schema 可解析
- 必填字段完整
- 格式符合要求
- 未明显偏离输入
- 对关键事实任务，不能仅靠同一模型自评

L3/L4 默认需要 GPT/总控或人工复核。

## 13. n8n 职责

n8n 负责：

- 接收任务
- 调 Router
- 显示推荐执行者
- 等待人工改派/确认
- 调用 Provider/Executor
- 根据状态分支
- 调 Verifier
- 执行 Retry/Fallback
- 展示结果

n8n 不负责：

- 写死各厂商完整 API 逻辑
- 保存明文 API Key 到工作流 JSON
- 承担复杂业务判断
- 直接绕过 Router 调模型

## 14. 安全策略

继续遵守 GLOBAL_RULES.md。

额外规定：

- API Key 不进入 Git、任务 JSON、日志。
- 日志默认对 Authorization、Cookie、Token、Key 脱敏。
- Browser/Web Provider 未来接入时，必须单独定义允许域名与允许动作。
- 不自动删除用户原始文件。
- 不自动 force push。
- 不自动发送邮件/消息/发布内容。
- 不自动进行购买/付款。
- 不自动更改账号安全设置。

## 15. V1 最小 UI

任务卡至少显示：

```text
任务：……
类型：software_debugging
复杂度：L3
风险：中
推荐：Codex
备用：GPT
状态：ROUTED

[按推荐执行]
[改派 ▼]
[取消]
```

运行后显示：

```text
当前执行者：Codex
尝试：1/2
状态：VERIFYING
验证：7/8 PASS
```

失败时显示：

```text
[停止]
[重试]
[换备用模型]
[转 GPT]
[人工接管]
```

## 16. 成本控制

V1 只实现基础成本策略：

- Python：优先级最高、视为本地低成本。
- DeepSeek：低成本文本首选。
- MiMo：长上下文/Agent 首选。
- Codex：代码任务。
- GPT：复杂升级/复核，不作为所有任务默认入口。

Provider 必须预留：

```text
cost_tier
usage
budget_exceeded
```

V1 可以先记录 usage，不要求实现精确跨厂商计费。

## 17. 第一阶段实现范围

Codex 第一阶段只实现“路由骨架”，不得一次性把所有真实 API 都接满。

必须完成：

1. Router 数据结构
2. L1/L2/L3/L4 判断框架
3. 硬规则路由
4. Provider Registry
5. Python Provider/Executor 适配
6. DeepSeek/MiMo/Codex/GPT 的 Stub Provider
7. 状态机
8. 人工改派接口
9. 高风险进入 WAITING_USER
10. Retry/Fallback 框架
11. Verifier 接口
12. 单元测试

第一阶段不得：

- 写真实密钥
- 强行接所有外部 API
- 引入浏览器自动化
- 改动现有已验证数字统计流程的核心行为
- 删除现有 spec/phase1-python-only 历史实现

## 18. 第二阶段实现范围

第一阶段通过后：

- 接 DeepSeek 正式 Provider
- 接 MiMo 正式 Provider
- 完成真实 API healthcheck
- 完成统一错误分类
- 验证结构化响应
- 加 usage 记录

## 19. 第三阶段实现范围

- Codex Repository Adapter
- Git diff
- 测试执行
- 自动 verifier
- 高风险 Git 操作拦截

## 20. 第四阶段候选

第一至三阶段稳定后再评估：

- Claude
- Gemini
- OpenAI/GPT Provider 扩展
- Browser Provider
- DeepSeek/ChatGPT/Claude/Gemini 官方网页代理
- Open WebUI/自定义统一聊天入口
- 定时任务
- 手机端

## 21. 验收标准

第一阶段必须满足：

- Router 对测试用例输出稳定结构
- Python 任务能正确路由到 Python
- 代码任务能路由到 Codex Stub
- 批量低风险文本能路由到 DeepSeek Stub
- 长上下文多步骤任务能路由到 MiMo Stub
- L3/L4 能触发 GPT/总控升级策略
- 用户能够覆盖推荐执行者
- 高风险动作无法绕过 WAITING_USER
- 执行器无法直接置 DONE
- 可重试错误最多自动两轮
- 不可重试错误立即停止或等待用户
- 所有新增测试通过
- 现有 executor 测试保持通过

## 22. Codex 每轮输出

每轮开发必须汇报：

```text
本轮完成
修改文件
测试结果
未完成内容
发现的问题
下一步建议
```

若发现本规格与现有实现冲突：

1. 不擅自重构全部项目。
2. 优先保留已经验证可工作的现有行为。
3. 把冲突列出来。
4. 采用最小兼容修改。
5. 高风险或需要改变用户规则时停止并等待拍板。

## 23. 核心原则

V1 的目标不是“让 AI 数量最多”，而是：

**让任务能可靠地被分类、分配、执行、验证，并且用户在关键位置始终能够接管。**

优先级：

```text
稳定性
>
可验证
>
人工可控
>
成本
>
模型数量
>
界面美观
```
