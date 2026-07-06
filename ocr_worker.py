"""OCR Worker — 独立进程执行 OCR 任务，避免 GIL 阻塞 Flask 主进程

由 tasks.py 通过 subprocess 调用，参数通过命令行传入。
进度和结果通过 SQLite 数据库同步。
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import fitz
import numpy as np
from paddleocr import PaddleOCR

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import RESULT_FOLDER, DATABASE
from models import update_task
from utils.pdf_utils import image_to_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ocr_worker: %(message)s",
)
logger = logging.getLogger("ocr_worker")


def do_ocr(task_id: str, input_path: str, original_filename: str) -> bool:
    """执行 OCR，返回 True 表示成功"""
    base_name = Path(original_filename).stem
    output_path = os.path.join(RESULT_FOLDER, task_id, f"{base_name}_searchable.pdf")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 图片先转 PDF
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in (".pdf",):
        pdf_path = os.path.join(RESULT_FOLDER, task_id, f"{base_name}.pdf")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        image_to_pdf(input_path, pdf_path)
        input_path = pdf_path
        update_task(task_id, progress=10)

    # 初始化 PaddleOCR
    update_task(task_id, progress=12)
    ocr = PaddleOCR(
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    logger.info("PaddleOCR 初始化完成")

    # 渲染 PDF 为图片
    update_task(task_id, progress=15)
    doc = fitz.open(input_path)
    zoom = 2.0
    total = doc.page_count
    logger.info(f"开始 OCR: {total} 页, {input_path}")

    images = []
    for page in doc:
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        images.append(img)

    # 逐页 OCR + 添加文字层
    for page_idx in range(total):
        page = doc[page_idx]
        img = images[page_idx]

        # OCR 识别
        result = ocr.predict(img)
        page_result = result[0]

        items = []
        if page_result is not None:
            rec_texts = page_result.get("rec_texts", [])
            rec_boxes = page_result.get("rec_boxes", [])
            for text, box in zip(rec_texts, rec_boxes):
                if text and text.strip():
                    items.append({"text": text, "bbox": tuple(box)})

        logger.debug(f"  第 {page_idx + 1}/{total} 页: {len(items)} 行文字")

        # 添加隐形文字层
        for item in items:
            text = item["text"]
            x0, y0, x1, y1 = item["bbox"]
            x0, y0 = x0 / zoom, y0 / zoom
            x1, y1 = x1 / zoom, y1 / zoom
            box_w = x1 - x0
            box_h = y1 - y0
            if box_w <= 0 or box_h <= 0:
                continue
            fontsize = box_h * 0.85
            text_width = fitz.get_text_length(text, fontname="china-s", fontsize=fontsize)
            if text_width > box_w:
                fontsize = fontsize * box_w / text_width
            page.insert_text(
                fitz.Point(x0, y1 - box_h * 0.15),
                text,
                fontname="china-s",
                fontsize=fontsize,
                render_mode=3,
            )

        # 更新进度 15% → 70%
        progress = 15 + int((page_idx + 1) / total * 55)
        update_task(task_id, progress=progress)

    # 保存结果
    update_task(task_id, progress=75)
    doc.save(output_path, incremental=False, encryption=0)
    doc.close()

    update_task(
        task_id, progress=100, status="completed",
        result_path=output_path,
        result_filename=f"{base_name}_searchable.pdf",
        error_message="",
    )
    logger.info(f"OCR 完成: {output_path}")
    return True


def do_batch_ocr(task_id: str, input_paths: list[str], file_names: list[str]) -> bool:
    """批量 OCR"""
    import zipfile

    work_dir = os.path.join(RESULT_FOLDER, task_id)
    os.makedirs(work_dir, exist_ok=True)

    ocr = PaddleOCR(
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    logger.info(f"批量 OCR: {len(input_paths)} 个文件")

    ocr_results = []
    total = len(input_paths)
    zoom = 2.0

    for i, (fp, fname) in enumerate(zip(input_paths, file_names)):
        base_name = Path(fname).stem

        ext = os.path.splitext(fp)[1].lower()
        if ext not in (".pdf",):
            pdf_path = os.path.join(work_dir, f"_batch_{i}.pdf")
            image_to_pdf(fp, pdf_path)
            fp = pdf_path

        doc = fitz.open(fp)
        images = []
        for page in doc:
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            images.append(img)

        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            result = ocr.predict(images[page_idx])
            page_result = result[0]
            if page_result is not None:
                rec_texts = page_result.get("rec_texts", [])
                rec_boxes = page_result.get("rec_boxes", [])
                for text, box in zip(rec_texts, rec_boxes):
                    if not text or not text.strip():
                        continue
                    x0, y0, x1, y1 = box
                    x0, y0 = x0 / zoom, y0 / zoom
                    x1, y1 = x1 / zoom, y1 / zoom
                    box_w, box_h = x1 - x0, y1 - y0
                    if box_w <= 0 or box_h <= 0:
                        continue
                    fontsize = box_h * 0.85
                    text_width = fitz.get_text_length(text, fontname="china-s", fontsize=fontsize)
                    if text_width > box_w:
                        fontsize = fontsize * box_w / text_width
                    page.insert_text(
                        fitz.Point(x0, y1 - box_h * 0.15),
                        text, fontname="china-s", fontsize=fontsize, render_mode=3,
                    )

        out_path = os.path.join(work_dir, f"{base_name}_searchable.pdf")
        doc.save(out_path, incremental=False, encryption=0)
        doc.close()
        ocr_results.append(out_path)

        progress = 10 + int((i + 1) / total * 70)
        update_task(task_id, progress=progress)

    # ZIP 打包
    zip_path = os.path.join(work_dir, "batch_ocr_results.zip")
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in ocr_results:
            if os.path.isfile(fp):
                zf.write(fp, arcname=os.path.basename(fp))

    update_task(
        task_id, progress=100, status="completed",
        result_path=zip_path,
        result_filename="batch_ocr_results.zip",
        error_message="",
    )
    logger.info(f"批量 OCR 完成: {zip_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="OCR Worker")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mode", choices=["ocr", "batch_ocr"], required=True)
    parser.add_argument("--input", required=True, help="输入文件路径（逗号分隔批量）")
    parser.add_argument("--filename", default="input", help="原始文件名（逗号分隔批量）")
    args = parser.parse_args()

    try:
        if args.mode == "ocr":
            ok = do_ocr(args.task_id, args.input, args.filename)
        else:
            filepaths = args.input.split(",")
            filenames = args.filename.split(",") if args.filename else [""] * len(filepaths)
            ok = do_batch_ocr(args.task_id, filepaths, filenames)

        if not ok:
            update_task(args.task_id, status="failed", error_message="OCR 处理未知错误")
            sys.exit(1)
    except Exception as e:
        logger.exception("OCR worker 异常退出")
        update_task(args.task_id, status="failed", error_message=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
