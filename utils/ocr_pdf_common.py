"""通用 OCR PDF → 可搜索 PDF（隐形文字层）

Usage:
    python ocr_pdf_common.py <input.pdf> [output.pdf] [--zoom ZOOM]

Examples:
    python ocr_pdf_common.py 1.pdf                          # -> 1_searchable.pdf
    python ocr_pdf_common.py 2.pdf out.pdf                  # -> out.pdf
    python ocr_pdf_common.py scan.pdf --zoom 2.5            # 自定义渲染精度
"""

import argparse
import sys
from pathlib import Path

import fitz
import numpy as np
from paddleocr import PaddleOCR

# 渲染缩放倍数：2.0 倍兼顾 OCR 识别准确率与处理速度
# 较低 → 速度快但文字识别率下降；较高 → 识别更准但内存和耗时增加
DEFAULT_ZOOM = 2.0


def ocr_page(pix: fitz.Pixmap, ocr: PaddleOCR) -> list[dict]:
    """对单页图像 OCR，返回 [{text, bbox(x0,y0,x1,y1)}, ...]

    参数:
        pix: PyMuPDF Pixmap 对象（PDF 页面渲染后的位图）
        ocr: 已初始化的 PaddleOCR 实例

    返回: 每条记录包含 text（识别文本）和 bbox（边界框四角坐标）
    """
    # 将 Pixmap 原始字节转为 numpy 数组（H, W, C）
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    result = ocr.predict(img)
    page_result = result[0]
    # page_result 为 None 表示该页无任何可识别文字
    if page_result is None:
        return []

    items = []
    rec_texts = page_result.get("rec_texts", [])
    rec_boxes = page_result.get("rec_boxes", [])

    for text, box in zip(rec_texts, rec_boxes):
        # 跳过纯空白字符串（OCR 可能识别出空白）
        if not text.strip():
            continue
        items.append({"text": text, "bbox": box})
    return items


def add_text_layer(page: fitz.Page, items: list[dict], zoom: float):
    """在 PDF 页面上添加隐形可搜索文字层

    原理：对每个 OCR 识别到的文字区域，以 render_mode=3（不可见渲染）
    插入对应文本，使 PDF 阅读器可搜索/选中，但视觉上完全透明。

    参数:
        page: 目标 PDF 页面（fitz.Page）
        items: OCR 识别结果 [{"text": str, "bbox": (x0,y0,x1,y1)}, ...]
        zoom: 渲染缩放倍数，用于将图片坐标转回 PDF 坐标
    """
    for item in items:
        text = item["text"]
        x0, y0, x1, y1 = item["bbox"]

        # 图片坐标 → PDF 页面坐标（除以缩放倍数）
        x0, y0 = x0 / zoom, y0 / zoom
        x1, y1 = x1 / zoom, y1 / zoom

        box_w = x1 - x0
        box_h = y1 - y0
        # 跳过无效边界框（宽/高为 0 或负值）
        if box_w <= 0 or box_h <= 0:
            continue

        # 计算适配字体大小：取框高度的 85% 作为字号
        fontsize = box_h * 0.85
        # 若文字宽度超过框宽，等比缩小字号到刚好放入框内
        text_width = fitz.get_text_length(text, fontname="china-s", fontsize=fontsize)
        if text_width > box_w:
            fontsize = fontsize * box_w / text_width

        # render_mode=3: 不可见但可搜索/选中（PyMuPDF 特有力）
        # 0=可见, 1=描边, 2=填充, 3=不可见
        page.insert_text(
            fitz.Point(x0, y1 - box_h * 0.15),
            text,
            fontname="china-s",
            fontsize=fontsize,
            render_mode=3,
        )


def main():
    """CLI 入口：对单个 PDF 文件执行 OCR 并生成可搜索版本

    命令行参数:
        input           输入 PDF 路径（必填）
        output          输出 PDF 路径（可选，默认为 <输入文件名>_searchable.pdf）
        --zoom ZOOM     渲染精度倍数（可选，默认 2.0，越大越清晰但越慢）

    退出码: 0=成功, 1=文件不存在
    """
    parser = argparse.ArgumentParser(
        description="OCR a scanned PDF and add invisible searchable text layer"
    )
    parser.add_argument("input", type=str, help="Input PDF path")
    parser.add_argument("output", type=str, nargs="?", default=None,
                        help="Output PDF path (default: <input>_searchable.pdf)")
    parser.add_argument("--zoom", type=float, default=DEFAULT_ZOOM,
                        help=f"Render zoom factor for OCR accuracy (default: {DEFAULT_ZOOM})")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + "_searchable")

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Zoom:   {args.zoom}x")

    ocr = PaddleOCR(
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    doc = fitz.open(str(input_path))
    total = doc.page_count
    print(f"Pages:  {total}")

    for page_idx in range(total):
        page = doc[page_idx]
        print(f"  Page {page_idx + 1}/{total}...", end=" ", flush=True)

        # 第1步：将 PDF 页面渲染为指定精度的位图
        mat = fitz.Matrix(args.zoom, args.zoom)
        pix = page.get_pixmap(matrix=mat)

        # 第2步：对位图运行 OCR 识别文字
        items = ocr_page(pix, ocr)
        print(f"{len(items)} text blocks")

        # 第3步：将识别到的文字以隐形层方式写回 PDF 页面
        add_text_layer(page, items, args.zoom)

    # 保存结果：incremental=False 完整重写（体积更小），encryption=0 不加密
    doc.save(str(output_path), incremental=False, encryption=0)
    doc.close()
    print(f"Done -> {output_path}")


if __name__ == "__main__":
    main()
