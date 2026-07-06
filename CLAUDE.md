
<!-- superpowers-zh:begin (do not edit between these markers) -->
# Superpowers-ZH 中文增强版

本项目已安装 superpowers-zh 技能框架（20 个 skills）。

## 核心规则

1. **收到任务时，先检查是否有匹配的 skill** — 哪怕只有 1% 的可能性也要检查
2. **设计先于编码** — 收到功能需求时，先用 brainstorming skill 做需求分析
3. **测试先于实现** — 写代码前先写测试（TDD）
4. **验证先于完成** — 声称完成前必须运行验证命令

## 可用 Skills

Skills 位于 `.claude/skills/` 目录，每个 skill 有独立的 `SKILL.md` 文件。

- **brainstorming**: 在任何创造性工作之前必须使用此技能——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。
- **chinese-code-review**: 中文 review 沟通参考——话术模板、分级标注（必须修复/建议修改/仅供参考）、国内团队常见反模式应对。仅在用户显式 /chinese-code-review 时调用，不要根据上下文自动触发。
- **chinese-commit-conventions**: 中文 commit 与 changelog 配置参考——Conventional Commits 中文适配、commitlint/husky/commitizen 中文模板、conventional-changelog 中文配置。仅在用户显式 /chinese-commit-conventions 时调用，不要根据上下文自动触发。
- **chinese-documentation**: 中文文档排版参考——中英文空格、全半角标点、术语保留、链接格式、中文文案排版指北约定。仅在用户显式 /chinese-documentation 时调用，不要根据上下文自动触发。
- **chinese-git-workflow**: 国内 Git 平台配置参考——Gitee、Coding.net、极狐 GitLab、CNB 的 SSH/HTTPS/凭据/CI 接入差异与镜像同步配置。仅在用户显式 /chinese-git-workflow 时调用，不要根据上下文自动触发。
- **dispatching-parallel-agents**: 当面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用
- **executing-plans**: 当你有一份书面实现计划需要在单独的会话中执行，并设有审查检查点时使用
- **finishing-a-development-branch**: 当实现完成、所有测试通过、需要决定如何集成工作时使用——通过提供合并、PR 或清理等结构化选项来引导开发工作的收尾
- **mcp-builder**: MCP 服务器构建方法论 — 系统化构建生产级 MCP 工具，让 AI 助手连接外部能力
- **receiving-code-review**: 收到代码审查反馈后、实施建议之前使用，尤其当反馈不明确或技术上有疑问时——需要技术严谨性和验证，而非敷衍附和或盲目执行
- **requesting-code-review**: 完成任务、实现重要功能或合并前使用，用于验证工作成果是否符合要求
- **subagent-driven-development**: 当在当前会话中执行包含独立任务的实现计划时使用
- **systematic-debugging**: 遇到任何 bug、测试失败或异常行为时使用，在提出修复方案之前执行
- **test-driven-development**: 在实现任何功能或修复 bug 时使用，在编写实现代码之前
- **using-git-worktrees**: 当需要开始与当前工作区隔离的功能开发，或在执行实现计划之前使用——通过原生工具或 git worktree 回退机制确保隔离工作区存在
- **using-superpowers**: 在开始任何对话时使用——确立如何查找和使用技能，要求在任何响应（包括澄清性问题）之前调用 Skill 工具
- **verification-before-completion**: 在宣称工作完成、已修复或测试通过之前使用，在提交或创建 PR 之前——必须运行验证命令并确认输出后才能声称成功；始终用证据支撑断言
- **workflow-runner**: 在 Claude Code / OpenClaw / Cursor 中直接运行 agency-orchestrator YAML 工作流——无需 API key，使用当前会话的 LLM 作为执行引擎。当用户提供 .yaml 工作流文件或要求多角色协作完成任务时触发。
- **writing-plans**: 当你有规格说明或需求用于多步骤任务时使用，在动手写代码之前
- **writing-skills**: 当创建新技能、编辑现有技能或在部署前验证技能是否有效时使用

## 如何使用

当任务匹配某个 skill 时，使用 `Skill` 工具加载对应 skill 并严格遵循其流程。绝不要用 Read 工具读取 SKILL.md 文件。

如果你认为哪怕只有 1% 的可能性某个 skill 适用于你正在做的事情，你必须调用该 skill 检查。
<!-- superpowers-zh:end -->

---

## PDF/图片处理工具网页应用

> **Python 环境**：所有 Python 命令必须在 `.venv` 虚拟环境中执行。
>
> - Windows: `.venv\Scripts\python` 或 `.venv\Scripts\pip`
> - 验证环境：`.venv\Scripts\python --version`

## 项目概述

自用的 PDF 及图片处理网页应用，支持单文件的高精度 OCR、压缩、拆分提取，以及批量合并与批量 OCR。无需用户认证，追求快速开发上线、模块逐步迭代。

详细设计方案见 [PDF图片处理工具网页应用详细设计方案.md](PDF图片处理工具网页应用详细设计方案.md)。

## 技术栈

- **后端**：Python Flask + Jinja2 模板引擎（前后端一体，不分离）
- **前端**：Bootstrap 5 + 原生 JavaScript（轮询任务状态）
- **任务调度**：`concurrent.futures.ThreadPoolExecutor` + SQLite 记录进度
- **核心依赖**：`pypdf`、`pdf2image`、`Pillow`、`PaddleOCR`、`PaddlePaddle`
- **系统依赖**：poppler-utils（已安装配置）、Python 3.8+ 虚拟环境 `.venv`
- **无 Node.js 依赖**

## 项目结构

```text
pdf_tool/
├── app.py                    # Flask 入口，注册蓝图，初始化数据库
├── config.py                 # 配置文件
├── models.py                 # SQLite 任务模型
├── tasks.py                  # 后台任务执行器（线程池 + 具体任务）
├── utils/
│   ├── __init__.py
│   ├── ocr_utils.py          # PaddleOCR 封装
│   ├── pdf_utils.py          # PDF 操作（合并、拆分、压缩、图片转PDF）
│   ├── file_utils.py         # 文件验证、清理
│   └── zip_utils.py          # 打包工具
├── templates/
│   ├── base.html
│   ├── index.html            # 单文件处理
│   ├── batch.html            # 批量处理
│   └── tasks.html            # 任务列表
├── static/
│   ├── css/style.css
│   └── js/main.js            # 轮询、表单交互
├── uploads/                  # 原始文件临时存储
├── results/                  # 处理结果存储
├── requirements.txt
└── .venv/                    # Python 虚拟环境
```

## 功能模块

### 单文件处理

1. **OCR 生成可搜索 PDF**：pdf2image 渲染 → PaddleOCR 识别 → pypdf 嵌入透明文字层
2. **PDF 压缩**：迭代调整图片质量/分辨率，尽力接近目标大小（±5%）
3. **PDF 拆分提取**：奇偶页/自定义页码范围，可选压缩，结果打包 ZIP

### 批量处理

1. **合并（可压缩）**：最多 10 个文件，图片自动转 PDF，支持拖拽排序
2. **批量 OCR**：最多 10 个文件依次 OCR，结果打包 ZIP

### 任务系统

- SQLite 持久化任务状态（UUID、类型、进度、状态、结果路径）
- 前端每 2 秒轮询任务状态
- API：`POST /api/task/create`、`GET /api/task/<id>`、`GET /api/tasks`、`GET /download/<id>`

## 编码规范

- 严格遵循 **PEP 8**，4 空格缩进，UTF-8 编码
- 核心逻辑放 `utils/` 包中，与 Flask 路由分离，函数单一职责
- 使用 `try...except` 捕获异常，返回明确错误信息
- 临时文件用 `tempfile` 模块创建，任务完成后或定期清理
- 数据库操作用上下文管理器，确保连接安全释放
- 所有路由和功能添加充分的注释与类型提示
- 使用 `.venv` 虚拟环境运行所有 Python 命令

## 关键约束

- 单文件限制 ≤ 1GB，格式仅允许 `.pdf`, `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`
- 批量上传每个文件 ≤ 10 个
- 并发任务数受线程池大小控制，避免内存溢出
- 压缩目标大小为"尽力接近"，非精确保证
- 启动命令：`python app.py`，访问 `http://127.0.0.1:5000`
- `utils/ocr_pdf_common.py` 已有单文件 OCR 实现，可直接参考复用

## 开发流程

1. 收到功能需求时，先用 brainstorming skill 分析
2. 写代码前先写测试（TDD）
3. 声称完成前必须运行验证命令
4. 不自动 `git commit` 或 `git push`，除非明确要求
