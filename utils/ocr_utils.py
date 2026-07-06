"""PaddleOCR 封装工具

参照 utils/ocr_pdf_common.py 的实现方式，使用 PaddleOCR 3.x API。
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# 全局单例
_ocr_instance = None


def get_ocr():
    """获取 PaddleOCR 实例（单例，延迟初始化）"""
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR

        _ocr_instance = PaddleOCR(
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        logger.info("PaddleOCR 初始化完成")
    return _ocr_instance


def ocr_image(img: np.ndarray) -> list[dict]:
    """
    对单张图片（numpy array）执行 OCR。

    参数:
        img: numpy array，形状 (H, W, C)，dtype=uint8

    返回: [{"text": str, "bbox": (x0,y0,x1,y1)}, ...]
    """
    ocr = get_ocr()
    result = ocr.predict(img)
    page_result = result[0]

    if page_result is None:
        return []

    items = []
    rec_texts = page_result.get("rec_texts", [])
    rec_boxes = page_result.get("rec_boxes", [])

    for text, box in zip(rec_texts, rec_boxes):
        if not text or not text.strip():
            continue
        # box 格式: (x0, y0, x1, y1) 或 [x0, y0, x1, y1]
        items.append({"text": text, "bbox": tuple(box)})
    return items
