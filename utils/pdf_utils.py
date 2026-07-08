"""PDF 操作工具：OCR文字层、合并、拆分、压缩、图片转PDF

OCR 流程使用 PyMuPDF (fitz)，参照 utils/ocr_pdf_common.py 的实现。
合并、拆分、压缩使用 pypdf。
"""

import io
import os
import logging
from typing import Sequence

import fitz
import numpy as np
from PIL import Image
import pypdf

from config import OCR_DPI

logger = logging.getLogger(__name__)


# ==================== OCR 相关（PyMuPDF） ====================

def pdf_to_images_fitz(pdf_path: str, zoom: float = 2.0) -> tuple[list[np.ndarray], fitz.Document, float]:
    """
    使用 PyMuPDF 将 PDF 所有页面渲染为 numpy 数组列表。

    返回: (images, doc, zoom)
        images: 每页的 numpy array (H, W, C)
        doc: fitz.Document 对象（调用方负责关闭）
        zoom: 实际使用的缩放倍数
    """
    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        images.append(img)
    return images, doc, zoom


def add_text_layer_fitz(
    page: fitz.Page,
    items: list[dict],
    zoom: float,
) -> None:
    """
    在 PDF 页面上添加隐形可搜索文字层（render_mode=3）。

    参数:
        page: fitz.Page 对象
        items: OCR 结果列表 [{"text": str, "bbox": (x0,y0,x1,y1)}, ...]
        zoom: 渲染时的缩放倍数
    """
    for item in items:
        text = item["text"]
        x0, y0, x1, y1 = item["bbox"]

        # 图片坐标 → PDF 页面坐标
        x0, y0 = x0 / zoom, y0 / zoom
        x1, y1 = x1 / zoom, y1 / zoom

        box_w = x1 - x0
        box_h = y1 - y0
        # 跳过无效边界框（宽度或高度为 0 或负值，通常由 OCR 定位错误产生）
        if box_w <= 0 or box_h <= 0:
            continue

        # 计算适配字体大小
        fontsize = box_h * 0.85
        text_width = fitz.get_text_length(text, fontname="china-s", fontsize=fontsize)
        if text_width > box_w:
            fontsize = fontsize * box_w / text_width

        # render_mode=3 = 隐形但可搜索/选中
        page.insert_text(
            fitz.Point(x0, y1 - box_h * 0.15),
            text,
            fontname="china-s",
            fontsize=fontsize,
            render_mode=3,
        )


# ==================== 基础转换 ====================

def image_to_pdf(image_path: str, output_path: str) -> str:
    """将单张图片转为单页 PDF"""
    img = Image.open(image_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(output_path, "PDF")
    return output_path


# ==================== 合并 ====================

def merge_pdfs(file_paths: Sequence[str], output_path: str) -> str:
    """按顺序合并多个 PDF 文件（pypdf 6.x API）"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    writer = pypdf.PdfWriter()
    for fp in file_paths:
        writer.append(fp)
    with open(output_path, "wb") as f:
        writer.write(f)
    writer.close()
    return output_path


# ==================== 拆分 ====================

def split_pdf_by_mode(
    input_path: str,
    mode: str,
    page_range: str | None,
    output_dir: str,
) -> list[str]:
    """
    拆分 PDF。
    mode: "odd" 仅奇数页, "even" 仅偶数页, "range" 自定义范围
    page_range: mode="range" 时的页码范围，如 "1-3,5,7-9"
    """
    os.makedirs(output_dir, exist_ok=True)
    reader = pypdf.PdfReader(input_path)
    total_pages = len(reader.pages)

    if mode == "odd":
        target_pages = list(range(1, total_pages + 1, 2))
    elif mode == "even":
        target_pages = list(range(2, total_pages + 1, 2))
    elif mode == "range":
        target_pages = _parse_page_range(page_range or "", total_pages)
    else:
        raise ValueError(f"未知拆分模式: {mode}")

    output_files = []
    for page_num in target_pages:
        writer = pypdf.PdfWriter()
        writer.add_page(reader.pages[page_num - 1])
        out_path = os.path.join(output_dir, f"page_{page_num}.pdf")
        with open(out_path, "wb") as f:
            writer.write(f)
        output_files.append(out_path)

    return output_files


def _parse_page_range(range_str: str, max_page: int) -> list[int]:
    """解析页码范围字符串，如 '1-3,5,7-9'，返回 1-indexed 页码列表"""
    pages = set()
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a.strip()), int(b.strip())
            pages.update(range(max(1, start), min(max_page, end) + 1))
        else:
            p = int(part)
            pages.add(p)
    return sorted(p for p in pages if 1 <= p <= max_page)


# ==================== 压缩 ====================

def compress_pdf(
    input_path: str,
    target_kb: float | None,
    output_path: str,
    tolerance: float = 0.05,
    max_iterations: int = 6,
) -> tuple[str, float]:
    """
    压缩 PDF 至接近目标大小（尽力接近）。

    策略：逐轮降低图片质量 + 降分辨率，每轮检查结果大小。
    返回 (output_path, actual_kb).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    original_kb = os.path.getsize(input_path) / 1024

    if target_kb is None or target_kb >= original_kb:
        with open(input_path, "rb") as src, open(output_path, "wb") as dst:
            dst.write(src.read())
        return output_path, original_kb

    reader = pypdf.PdfReader(input_path)

    # 压缩策略：6 轮逐步降级，每轮降低图片质量和分辨率上限
    # 质量 60/45/30/20/15/10 → 从"肉眼无损"到"勉强可读"
    # 分辨率 1920/1440/1080/720 → 从"全高清"到"标清"
    # 后两轮保持 720 不变（再降文字将难以辨认），仅降低质量
    quality_levels = [60, 45, 30, 20, 15, 10]
    resolution_levels = [1920, 1440, 1080, 720, 720, 720]
    best_path = None
    best_kb = original_kb

    for iteration in range(min(max_iterations, len(quality_levels))):
        quality = quality_levels[iteration]
        max_res = resolution_levels[iteration]

        writer = pypdf.PdfWriter()
        writer.add_metadata({})  # 清空元数据，减少体积
        for page in reader.pages:
            # 三步压缩流水线：加入 writer → 压缩内容流 → 压缩页面内图片
            writer.add_page(page)
            added_page = writer.pages[-1]
            added_page.compress_content_streams()  # 压缩 PDF 内容流（文本、矢量图形）
            _compress_page_images(added_page, quality, max_res)  # 压缩内嵌图片

        with open(output_path, "wb") as f:
            writer.write(f)
        current_kb = os.path.getsize(output_path) / 1024

        # 追踪最佳结果
        if current_kb < best_kb:
            best_kb = current_kb
            best_path = output_path

        if current_kb <= target_kb * (1 + tolerance):
            break

    return best_path or output_path, best_kb


def _compress_page_images(page: pypdf.PageObject, quality: int, max_resolution: int = 1920) -> None:
    """
    压缩页面内嵌图片：
    1. 大尺寸图片等比缩放到 max_resolution 以内
    2. RGBA/P → RGB 转换
    3. PNG/GIF/无损 → JPEG（仅当压缩后体积更小时才替换）
    4. 原始数据不变（避免越压越大）
    """
    try:
        for img_file in page.images:
            try:
                img_data = img_file.data
                original_size = len(img_data)
                pil_img = Image.open(io.BytesIO(img_data))

                # ---- 步骤1：降分辨率 ----
                w, h = pil_img.size
                if max(w, h) > max_resolution:
                    scale = max_resolution / max(w, h)
                    new_size = (int(w * scale), int(h * scale))
                    # LANCZOS：高质量重采样滤镜，缩放后边缘清晰，适合文档/文字类图片
                    pil_img = pil_img.resize(new_size, Image.LANCZOS)

                # ---- 步骤2：模式转换 ----
                if pil_img.mode in ("RGBA", "P", "LA", "PA"):
                    pil_img = pil_img.convert("RGB")

                # ---- 步骤3：JPEG 压缩 + 替换 ----
                # pypdf 6.x: img_file.replace() 需要 PIL Image 对象
                # 用临时 buffer 预判压缩后大小
                preview_buf = io.BytesIO()
                pil_img.save(preview_buf, format="JPEG", quality=quality, optimize=True)
                new_size = preview_buf.tell()

                # ---- 步骤4：只在更小时替换 ----
                if new_size < original_size:
                    # 重新从 buffer 加载为 PIL Image 传给 replace
                    preview_buf.seek(0)
                    compressed_img = Image.open(preview_buf)
                    img_file.replace(compressed_img)
                # 否则保留原始图片（PNG 可能已是最优）

            except Exception:
                pass  # 单张图片失败不影响整体
    except Exception:
        pass  # 页面无图片或图片提取失败
