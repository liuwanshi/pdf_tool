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

DEFAULT_ZOOM = 2.0


def ocr_page(pix: fitz.Pixmap, ocr: PaddleOCR) -> list[dict]:
    """对单页图像 OCR，返回 [{text, bbox(x0,y0,x1,y1)}, ...]"""
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    result = ocr.predict(img)
    page_result = result[0]
    if page_result is None:
        return []

    items = []
    rec_texts = page_result.get("rec_texts", [])
    rec_boxes = page_result.get("rec_boxes", [])

    for text, box in zip(rec_texts, rec_boxes):
        if not text.strip():
            continue
        items.append({"text": text, "bbox": box})
    return items


def add_text_layer(page: fitz.Page, items: list[dict], zoom: float):
    """在 PDF 页面上添加隐形文字层"""
    for item in items:
        text = item["text"]
        x0, y0, x1, y1 = item["bbox"]

        # 图片坐标 → PDF 页面坐标
        x0, y0 = x0 / zoom, y0 / zoom
        x1, y1 = x1 / zoom, y1 / zoom

        box_w = x1 - x0
        box_h = y1 - y0
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


def main():
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

        mat = fitz.Matrix(args.zoom, args.zoom)
        pix = page.get_pixmap(matrix=mat)

        items = ocr_page(pix, ocr)
        print(f"{len(items)} text blocks")

        add_text_layer(page, items, args.zoom)

    doc.save(str(output_path), incremental=False, encryption=0)
    doc.close()
    print(f"Done -> {output_path}")


if __name__ == "__main__":
    main()
