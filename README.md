# PDF 处理工具

自用的 PDF 及图片处理网页应用，支持 OCR、压缩、拆分、合并等常见操作。纯 Python 后端 + Bootstrap 前端，开箱即用。

## 功能概览

### 单文件处理

| 功能 | 说明 |
|------|------|
| 🔍 **OCR 可搜索 PDF** | 扫描件/图片 → 可搜索、可复制文字的双层 PDF（PaddleOCR + PyMuPDF 透明文字层） |
| 📦 **PDF 压缩** | 6 轮迭代压缩（质量降级 + 分辨率降级），尽力接近目标大小（±5%） |
| ✂️ **PDF 拆分提取** | 奇偶页 / 自定义页码范围，可选压缩，结果打包 ZIP |

### 批量处理

| 功能 | 说明 |
|------|------|
| 📎 **合并（可压缩）** | 最多 10 个文件，图片自动转 PDF，支持拖拽排序，可选压缩 |
| 🔍 **批量 OCR** | 最多 10 个文件依次 OCR，结果打包 ZIP |

### 任务系统

- SQLite 持久化任务状态（UUID、类型、进度、状态、结果路径）
- 前端每 3 秒轮询任务状态，实时显示进度
- 支持任务重试、删除（含关联文件清理）
- 轻量任务使用 `ThreadPoolExecutor`，OCR 任务通过 `subprocess` 独立进程执行（避免 GIL 阻塞 Flask）

## 技术栈

| 层面 | 技术 |
|------|------|
| **后端框架** | Python Flask + Jinja2（前后端一体） |
| **前端** | Bootstrap 5 + 原生 JavaScript |
| **PDF 渲染** | PyMuPDF (fitz) |
| **PDF 操作** | pypdf 6.x |
| **OCR 引擎** | PaddleOCR 3.x + PaddlePaddle 3.x |
| **图片处理** | Pillow |
| **任务调度** | `concurrent.futures.ThreadPoolExecutor` + subprocess |
| **数据库** | SQLite（WAL 模式） |
| **系统依赖** | poppler-utils（已安装配置） |

## 快速开始

### 环境要求

- Python 3.8+
- poppler-utils（Windows 需下载并配置 `POPPLER_PATH` 环境变量）
- Windows / Linux / macOS

### 安装

```bash
# 克隆仓库
git clone https://github.com/liuwanshi/pdf_tool.git
cd pdf_tool

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境 (Windows)
.venv\Scripts\activate
# 激活虚拟环境 (Linux/macOS)
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置

通过环境变量覆盖默认配置（均为可选）：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SECRET_KEY` | `pdf-tool-dev-key-...` | Flask 密钥 |
| `POPPLER_PATH` | 空 | poppler bin 目录路径（Windows 需设置） |
| `LOG_LEVEL` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `MAX_WORKERS` | `3` | 并发处理线程数 |

其他配置项（上传限制、允许格式、OCR DPI 等）见 [config.py](config.py)。

### 启动

```bash
# 确保在虚拟环境中
.venv\Scripts\python app.py
```

访问 `http://127.0.0.1:5000`。

## 项目结构

```text
pdf_tool/
├── app.py                   # Flask 入口，创建应用、初始化数据库
├── config.py                # 配置文件
├── models.py                # SQLite 任务模型（CRUD + 迁移 + 中断恢复）
├── routes.py                # Flask 路由注册（页面 + API + 上传 + 下载）
├── tasks.py                 # 后台任务（线程池 + subprocess worker 监控）
├── ocr_worker.py            # OCR 独立进程入口
├── utils/
│   ├── ocr_utils.py         # PaddleOCR 单例封装
│   ├── pdf_utils.py         # PDF 操作（OCR文字层、合并、拆分、压缩、图片转PDF）
│   ├── file_utils.py        # 文件验证、安全化、保存、清理
│   └── zip_utils.py         # ZIP 打包工具
├── templates/
│   ├── base.html            # 基础布局
│   ├── index.html           # 单文件处理页
│   ├── batch.html           # 批量处理页
│   └── tasks.html           # 任务列表页
├── static/
│   ├── css/style.css
│   └── js/main.js           # 前端交互（表单提交、轮询、拖拽排序）
├── uploads/                 # 原始文件临时存储
├── results/                 # 处理结果存储
└── requirements.txt
```

## 关键约束

- 单文件限制 ≤ 1GB，允许格式：`.pdf` `.png` `.jpg` `.jpeg` `.bmp` `.tiff`
- 批量处理每次最多 10 个文件
- 并发任务数受 `MAX_WORKERS` 控制（默认 3），避免内存溢出
- 压缩为"尽力接近"目标大小，非精确保证
- 结果文件保留 24 小时后自动清理
- 服务重启时自动标记未完成任务为"中断"状态，支持重试
