# 本地 AI 工作流 · Windows 便携版

自带运行环境、通过浏览器操作的单机工作流工具。n8n 负责表单与流程编排，Python 执行器负责确定性计算、检查、状态和人工验收。

**当前目标系统：Windows 10/11 x64。** 不需要预装 Python、Node、Docker 或申请 n8n 云账号。macOS/Linux 尚未打包。当前不是完整 AI 自动总控。

本文件夹同时是运行目录、源码目录和安装器来源，全部内容集中在这一层，不再需要其他位置的副本。

## 目录结构

| 路径 | 用途 | 是否进 Git |
|---|---|---|
| `start.cmd` / `start.ps1` | 便携启动（首次运行会初始化数据库并导入示例流程） | 是 |
| `stop.cmd` / `stop.ps1` | 停止本程序的两个服务 | 是 |
| `open.cmd` | 打开数字统计表单 | 是 |
| `sync-workflows.cmd` / `.ps1` | 把 `workflows` 里的流程重新导入并发布到现有数据库 | 是 |
| `env.ps1` | n8n 与执行器的环境变量（监听地址、端口、节点白名单、执行记录保留策略） | 是 |
| `executor/app` | Python 执行器（FastAPI 服务，端口 8765） | 是 |
| `executor/tests` | 执行器单元测试 | 是 |
| `workflows` | 无凭据的示例流程（n8n 导入格式） | 是 |
| `installer` | 安装入口、`app-overlay`、打包载荷 | 仅脚本，载荷除外 |
| `tools` | 依赖审计与 SQLite 原生库安装脚本 | 是 |
| `docs` | 截图 | 是 |
| `spec` | 原始需求规格与第一代纯 Python 实现（历史资料） | 是 |
| `runtime` | 自带的 Node 24.15.0 与 Python 3.12.14 | 否，约 1 GiB |
| `n8n/node_modules` | 锁定版本的 n8n 依赖 | 否，约 1 GiB |
| `data` | 运行数据：n8n 数据库、加密配置、任务记录、进程号 | 否 |

仓库只保存源码和配置。`runtime` 与 `n8n/node_modules` 随打包载荷分发，克隆仓库本身不含运行环境。

## 下载使用

把 `installer` 目录（含 `payload.tar.xz`）整体交给使用者，或用本仓库 Releases 里的 `AI-Workflow-Windows-x64-setup-*.zip`。先解压到普通文件夹，不要在压缩包内直接运行。

1. 双击 `setup.cmd`，选择安装父目录。有 E 盘时默认 `E:\AI-Apps`，程序放在其下的 `AI-Workflow-Portable` 文件夹内。建议选择较短的可写路径；已有同名目录不会被覆盖。
2. 安装完成后自动启动，首次初始化可能需要几分钟。以后运行安装目录里的 `start.cmd`。
3. 输入 `10, 20, 30`，查看总和 60、平均值 20，填写验收说明后选择通过或拒绝。
4. 使用 `open.cmd` 再次打开表单；任务完成后用 `stop.cmd` 停止服务。

程序文件解压后约 2.06 GiB，建议预留至少 4 GiB 可用空间。安装使用 Windows 自带 tar（脚本显式调用 `%SystemRoot%\System32\tar.exe`），不需要另外安装压缩软件，也不会受 PATH 里其他 tar 影响。

`installer/app-overlay` 保存当前的应用代码。安装时脚本先把载荷解压出运行时，再用 overlay 覆盖应用文件，所以应用代码或流程更新后不必重新打包 2 GiB 的载荷。

| 入口 | 地址 |
|---|---|
| 数字统计与人工验收 | http://127.0.0.1:5678/form/workflow-python-trial |
| 本机任务历史 | http://127.0.0.1:8765 |
| n8n 流程管理 | http://127.0.0.1:5678 |

管理页面首次进入时由你创建本地管理员账号。程序只监听本机，端口 5678、5679、8765 必须空闲，一台电脑同时只运行一份。

## 数据与迁移

发布压缩包不包含运行数据库、日志、账号或密钥。第一次启动会在 `data` 内创建独立数据库和加密配置。

迁移自己的记录时，先停止程序，再复制整个文件夹（包括 `data`）。不要单独移动运行中的数据库，也不要丢失 n8n 的加密配置。请在任务结束后停止服务；不承诺正在执行的任务可以无缝恢复。

## 更新已有安装

`start.ps1` 只在第一次运行时导入示例流程，所以只替换文件不会更新数据库里已有的流程。改动 `workflows` 后要执行：

```
sync-workflows.cmd
```

它会停止前检查端口、重新导入两条示例流程并发布 `trialPython01`，执行前会提示确认。**你在 n8n 界面里对这两条示例流程做过的修改（包括选的凭据）会被文件内容覆盖**，请自行保留需要的改动。

## AI 状态

默认数字统计无需 AI。另有 DeepSeek 摘要流程，默认未启用、未配置凭据，尚未完成真实 API 调用验证。ChatGPT、Codex 等尚未接入。

需要使用 DeepSeek 时，在第二条流程的“DeepSeek 生成摘要”节点创建 Header Auth：Name=`Authorization`，Value=`Bearer ` 加自己的 API Key。只在本地界面填写，不要放入代码、工作流文件或 Issue。保存并发布后可使用；API 调用可能产生服务商费用。Python 只验证摘要输出的 JSON 格式，事实准确性仍需人工检查。

该节点的请求体使用 `model: "deepseek-flash"` 和 `thinking` 参数，尚未核对是否符合 DeepSeek 官方 API 的当前要求；首次真实调用前请对照官方文档确认模型名和参数。

## 已知行为

- **n8n 里的执行记录会一直显示为“等待中”。** 流程以 Form 节点的 `completion` 作为结尾，而 n8n 的 Form 节点在 `execute()` 里无论哪种 operation 都会调用 `putExecutionToWait`，因此执行被登记为无限期等待（数据库里 `finished=0`、`waitTill=3000-01-01`），不会转成成功状态。用户可见的完成页和任务状态都是正确的，这属于 n8n 自身的实现方式。副作用是：n8n 编辑器里这些执行一直显示等待中，每次重启 n8n 会打印 `Found unfinished executions` 和“可能是崩溃”的提示（实际不是崩溃）。
- 为限制累积，`env.ps1` 显式固定了执行记录保留策略：`EXECUTIONS_DATA_PRUNE=true`、`EXECUTIONS_DATA_MAX_AGE=336`（14 天）、`EXECUTIONS_DATA_PRUNE_MAX_COUNT=2000`。这是 n8n 2.39 的默认值，显式写出是为了不受后续版本改动默认值的影响。
- 验收结论依赖下拉标签的精确字符串比对（`$json["验收决定"] === "验收通过"`）。工作流文件必须保持 UTF-8 编码；若被以 GBK 等编码保存，比对会失效并把「验收通过」静默记成「拒绝」。
- 验收表单的「验收通过」不会被动态隐藏。任务未通过自动检查时仍可选它，此时执行器会拒绝（HTTP 409），流程给出「验收未生效」页并提示改用 `http://127.0.0.1:8765` 的“拒绝并停止”关闭任务。

## 2026-09-18 修复记录

- **失败任务选「验收通过」不再让流程报错、不再卡死。** 之前该操作让「保存验收结论」节点收到 409 并判定执行失败，用户看到 `Problem loading form`，同一个验收页无法再次提交，任务只能绕到 8765 界面关闭。现在该节点设置了 `options.response.response.neverError` 与 `fullResponse`，失败时流程照常走完，结尾页显示「验收未生效」并说明原因和关闭方式；验收页在存在错误时首行提示不能选“验收通过”。
- **安装脚本不再依赖 PATH 里的 tar。** 之前用裸 `tar.exe`，在 Git for Windows 勾选了“把 Unix 工具加入 PATH”的机器上会解析到 GNU tar，把 `E:\...` 当成远程主机并报 `Cannot connect to E: resolve failed`，安装直接失败。现在显式调用 `%SystemRoot%\System32\tar.exe`，缺失时给出明确报错。
- **应用代码与 2 GiB 载荷解耦。** 新增 `installer/app-overlay`，安装后覆盖应用文件，避免修复代码必须重新打包载荷才能生效。
- **`stop.ps1` 加固。** 停止后删除 `data/processes.json`（避免残留过期进程号），读取失败时给出警告而不是中断，单个进程号不属于本程序时跳过继续停止其余服务（之前会整体抛出，导致另一个服务停不掉）。
- **`start.ps1` 日志校验加固。** 初始化与发布检查改为按 BOM 解码后匹配，不再依赖 `Select-String` 对 UTF-16LE 日志的隐含处理。
- **新增 `sync-workflows.cmd`。** 补上此前缺失的流程更新路径。

## 检查与限制

- 已验证自带 Node/Python 启动、数字计算、人工通过、人工拒绝、结果落盘、停止进程和数据库完整性。已从压缩包解压到同一台机器的全新含空格目录，验证首次初始化和完整流程；尚未在第二台实体电脑验证。
- 2026-09-18 复核：全新目录首次初始化与完整流程通过；正常路径（10, 20, 30 → 验收通过 → DONE）通过；失败路径（非法输入后选“验收通过”）按修复后的预期给出「验收未生效」提示，执行不再进入 error 状态；执行器单元测试 8/8 通过。
- Windows Defender 在 2026-09-17 对打包源目录完成自定义扫描，匹配威胁记录为 0。这不保证不存在未知威胁。
- 2026-09-15 的 n8n 锁定依赖审计报告 152 个受影响依赖条目：critical 7、high 36、moderate 107、low 2，尚未修复；不是病毒数量。
- 已禁用社区包，仅开放表单和 HTTP 请求节点；这些限制不是操作系统沙箱，不应据此视为生产安全审计通过。
- n8n 仍可能尝试访问许可和功能目录服务。没有关闭杀毒、防火墙或设置扫描排除项。

## 开发

`executor/app` 是 Python 执行器，`executor/tests` 是单元测试，`workflows` 是无凭据的示例流程，`n8n/package-lock.json` 锁定 n8n 依赖，根目录脚本负责便携启动与停止，`installer` 是带校验和防覆盖检查的解压安装入口。`spec` 保留原始需求规格与第一代纯 Python 实现，仅供追溯。

开发 Python 部分时，在 `executor` 目录创建虚拟环境，安装 `requirements-lock.txt`，运行 `python -m unittest discover -s tests -v`。也可以直接用自带的解释器，注意要在 `executor` 目录下执行（`executor/tests` 不是包，从仓库根目录用 `-s executor/tests` 会报 `Start directory is not importable`）：

```
cd executor
..\runtime\python\python.exe -m unittest discover -s tests -v
```

不要把虚拟环境或任务数据提交到 Git。`.ps1` 含非 ASCII 字符时必须保存为带 BOM 的 UTF-8：Windows PowerShell 5.1 会把无 BOM 的脚本按系统 ANSI 代码页解码，中文路径或文件名会失效。当前仓库内的脚本全部保持纯 ASCII。

运行环境版本：Node 24.15.0、Python 3.12.14、n8n 2.39.5。依赖安装使用 `--ignore-scripts`；SQLite 原生库单独从官方发行包获取并检查。第三方许可随分发文件保留，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
