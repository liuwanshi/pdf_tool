# PDF/图片处理工具网页应用 - 详细设计方案

## 1. 项目概述
构建一个自用的PDF及图片处理网页应用，支持单文件的高精度OCR、压缩、拆分提取，以及批量合并与批量OCR。因处理耗时，需后台任务列表实时查看进度与结果。项目无需用户认证，追求快速开发上线、模块逐步迭代。

## 2. 技术选型

### 2.1 整体框架：Flask（前后端一体）
- **后端**：Python Flask + Jinja2 模板引擎，无需前后端分离。
- **前端**：Bootstrap 5 简单美化，原生 JavaScript 轮询任务状态。
- **任务调度**：Python `concurrent.futures.ThreadPoolExecutor` 后台线程池，配合 SQLite 记录任务进度。
- **文件存储**：临时目录存放原始文件和处理结果，任务完成后提供下载，定期清理。

### 2.2 核心依赖库
| 功能模块     | 库                              | 说明                                              |
| ------------ | ------------------------------- | ------------------------------------------------- |
| PDF基础操作  | `pypdf`                         | 合并、拆分、元数据读取、内容流压缩                |
| PDF转图片    | `pdf2image`                     | 依赖系统 `poppler`，将PDF页面渲染为图片供OCR处理  |
| 图片处理     | `Pillow`                        | 图片格式验证、分辨率调整、图片转PDF               |
| OCR引擎      | `PaddleOCR` + `PaddlePaddle`    | 高精度中英文OCR，输出文字及坐标，无需额外系统依赖 |
| 图像/PDF输出 | `img2pdf`（可选）或 `Pillow`    | 将图片流合成PDF                                   |
| Web框架      | `Flask`                         | 路由、模板、文件上传                              |
| 任务持久化   | `sqlite3`（内置）               | 记录任务状态、进度、文件路径                      |
| 文件压缩     | `zipfile`（内置）               | 打包多个结果文件供下载                            |
| 系统工具     | `poppler-utils`（需要单独安装） | 为 `pdf2image` 提供 PDF 渲染能力                  |

### 2.3 环境依赖
- Python 3.8+（已具备），根目录已经安装好了python 虚拟环境.venv，后续开发都在此虚拟环境使用python 
- Poppler：Windows 需下载并配置 PATH（已具备）；
- PaddleOCR 及模型（已具备）
- Node.js 非必需，无需使用

## 3. 编码规范
- 严格遵循 **PEP 8** 代码风格，使用4空格缩进。
- 所有文件使用 UTF-8 编码。
- 函数遵循单一职责原则，核心处理逻辑放在 `utils/` 包中，与 Flask 路由分离。
- 使用 `try...except` 捕获异常，并向用户返回明确的错误原因。
- 临时文件使用 `tempfile` 模块创建，任务完成后或定期清理。
- 数据库操作使用上下文管理器，确保连接安全释放。
- 所有路由和功能均添加充分的注释与类型提示。

## 4. 项目结构
```
pdf_tool/
├── app.py                    # Flask 应用入口，注册蓝图，初始化数据库
├── config.py                 # 配置文件（上传限制、临时目录等）
├── models.py                 # SQLite 任务模型操作函数
├── tasks.py                  # 后台任务执行器（线程池 + 具体任务实现）
├── utils/
│   ├── __init__.py
│   ├── ocr_utils.py          # OCR 处理（PaddleOCR 封装）
│   ├── pdf_utils.py          # PDF 操作（合并、拆分、压缩、图片转PDF）
│   ├── file_utils.py         # 文件验证、清理等
│   └── zip_utils.py          # 打包工具
├── templates/
│   ├── base.html             # 基础模板（导航、样式）
│   ├── index.html            # 首页/单文件处理表单
│   ├── batch.html            # 批量处理表单
│   └── tasks.html            # 任务列表页面
├── static/
│   ├── css/
│   │   └── style.css         # 自定义样式
│   └── js/
│       └── main.js           # 轮询、表单交互逻辑
├── uploads/                  # 原始文件临时存储（可配置）
├── results/                  # 处理结果存储
├── requirements.txt
└── README.md
```

## 5. 功能模块详细设计

### 5.1 通用功能
- **文件上传验证**：
  - 单文件限制 ≤ 1GB，格式仅允许 `.pdf`, `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`。
  - 批量上传每个文件同样验证，数量限制 ≤ 10 个。
- **任务创建与返回**：每次提交生成唯一任务ID，立即返回前端，后台线程开始处理。
- **进度更新**：后台任务定期将进度百分比写入 SQLite，前端通过 AJAX 轮询 `/api/tasks/<id>` 获取状态。

### 5.2 单文件处理
#### 功能1：OCR 生成可搜索 PDF
- **输入**：1个 PDF 或图片文件。
- **处理流程**：
  1. 如果是图片，先使用 Pillow 将其转为单页 PDF（保持原图大小，或等比缩放至标准分辨率）。
  2. 使用 `pdf2image` 将 PDF 所有页面转为图片（可配置 DPI=200）。
  3. 初始化 PaddleOCR（参数：`use_angle_cls=True, lang='ch'`）。
  4. 对每张图片进行 OCR，获得文字内容和边界框。
  5. 使用 `pypdf` 创建新 PDF，将原页面图片作为背景，并在对应位置添加透明文字层（利用 PDF 文本注释功能，将字体设为透明，但可被搜索）。
  6. 合并所有页面，输出带透明文字层的可搜索 PDF。
- **输出**：一个 PDF 文件，支持文本搜索、复制。

#### 功能2：PDF 压缩（可调节目标大小）
- **输入**：1个 PDF 或图片文件（图片先转为 PDF 再进行压缩）。
- **处理流程**：
  1. 计算原始文件大小（KB）。
  2. 提供滑块或输入框设定目标大小（单位 KB）。若未设置或高于原大小，则返回原文件。
  3. 采用迭代压缩策略：
     - 主要方法：调整页面内图片质量（使用 `pypdf` 提取图片、Pillow 压缩后重新嵌入）。
     - 辅助方法：移除元数据、压缩内容流、降低图片分辨率。
     - 循环尝试不同压缩参数，直至结果接近目标大小（误差 ±5%）。
  4. 若始终无法达到目标，返回最接近的结果，并给出提示。
- **输出**：压缩后的 PDF 文件。

#### 功能3：PDF 拆分提取（含压缩选项）
- **输入**：1个 PDF。
- **拆分方式**：
  - 奇偶页提取：选择只提取奇数页或偶数页。
  - 自定义页码范围：输入如 `1-3,5,7-9`。
- **压缩选项**：每个拆分出的 PDF 可手动设置目标大小（同功能2），单位为 KB。
- **处理流程**：
  1. 按选择提取页面，生成若干子 PDF。
  2. 若设置了压缩目标，对每个子 PDF 执行压缩。
  3. 将所有结果文件打包为 ZIP。
- **输出**：一个 ZIP 压缩包。

### 5.3 批量处理
#### 功能1：合并（可压缩）
- **输入**：最多10个 PDF 或图片文件，用户可拖拽排序。
- **处理流程**：
  1. 将非 PDF 文件（图片）先转为单页 PDF。
  2. 使用 `pypdf.PdfMerger` 按顺序合并所有 PDF。
  3. 若用户指定了目标大小（KB），对合并后的 PDF 执行压缩。
- **输出**：合并后的 PDF 文件。

#### 功能2：批量 OCR
- **输入**：最多10个 PDF 或图片文件。
- **处理流程**：
  1. 对每个文件依次调用单文件 OCR 功能。
  2. 收集所有结果 PDF，打包为 ZIP。
- **输出**：ZIP 压缩包。

### 5.4 任务列表
- **数据存储**：SQLite 表 `tasks`，字段：
  - `id` TEXT PRIMARY KEY (UUID)
  - `original_filename` TEXT
  - `task_type` TEXT (ocr/compress/split/merge/batch_ocr)
  - `progress` INTEGER DEFAULT 0
  - `status` TEXT DEFAULT 'processing' (processing/completed/failed)
  - `error_message` TEXT
  - `result_path` TEXT (下载文件路径)
  - `created_at` TIMESTAMP
- **前端页面**：
  - 表格展示所有任务，自动刷新（每2秒轮询）。
  - 状态列显示“处理中”、“已完成”、“任务失败”。
  - 已完成提供下载按钮；失败显示错误详情。
- **接口**：
  - `POST /api/task/create` 创建任务，返回任务ID。
  - `GET /api/task/<id>` 获取单个任务状态。
  - `GET /api/tasks` 获取所有任务（用于列表刷新）。
  - `GET /download/<id>` 下载结果文件。

## 6. 开发步骤（分模块可验证）

### 步骤1：项目骨架与基础配置
1. 创建项目目录，初始化虚拟环境，安装依赖：
   ```bash
   pip install flask pypdf pdf2image Pillow paddlepaddle paddleocr
   ```
2. 创建 `app.py`，使用 Flask 启动简单服务，访问首页返回 “Hello”。
3. 编写 `config.py`，定义上传文件夹、最大体积、允许扩展名等。
4. 创建基础模板 `base.html` 和 `index.html`，引入 Bootstrap CDN。
5. 运行 `python app.py`，验证页面可访问。

### 步骤2：文件上传与验证
1. 实现文件上传路由 `/upload/single` 和 `/upload/batch`。
2. 在 `utils/file_utils.py` 中编写 `validate_file(file, single=True)`，检查大小与格式。
3. 上传成功返回文件保存路径，前端显示文件信息。
4. 测试上传各种格式，确认限制生效。

### 步骤3：任务系统（SQLite + 后台线程）
1. 创建 `models.py`，编写 `init_db()`、`create_task()`、`update_task()`、`get_task()`、`get_all_tasks()`。
2. 创建 `tasks.py`，初始化 `ThreadPoolExecutor`，定义通用任务包装器 `run_task(task_id, func)`，内更新进度。
3. 创建任务路由：创建任务后提交线程池，返回ID。
4. 前端 `tasks.html` 实现轮询，展示静态模拟数据。
5. 验证任务创建、状态更新、下载链接。

### 步骤4：OCR 功能实现（单文件）
1. 在 `utils/ocr_utils.py` 封装 PaddleOCR 初始化与识别函数。
2. 在 `utils/pdf_utils.py` 实现 `add_searchable_text_layer(images, ocr_results)` 生成可搜索PDF。
3. 在 `tasks.py` 实现 `ocr_task(task_id, input_path, output_path)`，更新进度。
4. 前端表单提交创建 OCR 任务。
5. 测试：上传含中文的图片PDF，下载结果，用浏览器搜索文字验证。

### 步骤5：PDF 压缩功能（单文件）
1. 在 `utils/pdf_utils.py` 实现 `compress_pdf(input_path, target_kb, output_path)`。
   - 初步实现图片质量压缩循环。
2. 注册任务并测试，分别尝试设定不同目标大小，验证结果文件大小接近目标。

### 步骤6：PDF 拆分提取（含压缩）
1. 实现 `split_pdf(input_path, mode, page_range, output_dir)` 返回拆分后文件列表。
2. 支持奇偶页和页码范围解析。
3. 若提供压缩参数，对每个子文件调用 `compress_pdf`。
4. 使用 `zip_utils.py` 打包下载。
5. 测试各种拆分模式及压缩组合。

### 步骤7：批量合并与批量 OCR
1. 实现 `merge_pdfs(file_list, output_path, target_kb=None)`。
2. 批量 OCR 复用已有任务函数，循环处理并打包。
3. 前端批量上传页面，排序交互（可使用可拖拽列表）。
4. 测试合并与批量 OCR，确认结果正确。

### 步骤8：任务列表完善与错误处理
1. 完善前端任务列表样式与交互，显示错误信息。
2. 为每个任务函数添加完善的异常捕获，失败时更新数据库状态与错误原因。
3. 添加临时文件清理策略：在 `config.py` 设定结果保留时长，定期清理。
4. 全面测试，确保各类失败场景提示友好。

## 7. 测试策略
- **单元测试**：可选，但建议对核心工具函数编写测试（如页码范围解析、OCR 结果转换）。
- **手动功能测试**：每个步骤完成后使用典型文件测试：
  - 纯图片 PDF、文字 PDF、扫描件。
  - 大文件（接近1G）压测。
  - 批量10个文件边界。
- **错误模拟**：上传非PDF/图片文件、超大文件、并发提交多个任务，验证错误处理。

## 8. 部署方式
- 开发环境：`python app.py`，浏览器访问 `http://127.0.0.1:5000`。
- 生产环境（可选）：
  ```bash
  pip install waitress
  waitress-serve --port=5000 app:app
  ```
- 内网访问：绑定 `0.0.0.0`，其他设备通过局域网 IP 访问。

## 9. 注意事项
- utils\ocr_pdf_common.py 脚本实现单个PDF转换 为生成可搜索PDF，可以参考或直接使用。
- 压缩目标大小功能因 PDF 内容差异可能无法精确达到，需向前端说明为“尽力接近”。
- 并发任务数量建议通过线程池大小控制，避免内存溢出。
