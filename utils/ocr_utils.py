"""PaddleOCR 封装工具

参照 utils/ocr_pdf_common.py 的实现方式，使用 PaddleOCR 3.x API。
通过单例模式复用 OCR 引擎实例，避免每次调用时重新加载模型（初始化耗时约 5-10 秒）。
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# 全局 OCR 实例（模块内部使用，外部应通过 get_ocr() 获取）
_ocr_instance = None


def get_ocr():
    """获取 PaddleOCR 实例（单例模式，首次调用时初始化）

    设计说明：
    - 单例：PaddleOCR 模型加载耗时长（5-10s），全局复用避免重复初始化
    - 延迟初始化：不在 import 时加载，而是首次调用时才加载，加速模块导入

    参数说明（PaddleOCR 3.x API）：
    - enable_mkldnn=False    关闭 Intel MKL-DNN 加速（避免 Windows 兼容问题）
    - use_doc_orientation_classify=False  关闭文档方向分类（PDF 已摆正，无需）
    - use_doc_unwarping=False            关闭文档展平（扫描件可能弯曲，但质量开销大）
    - use_textline_orientation=False     关闭文字行方向检测（中文默认横排）
    """
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
