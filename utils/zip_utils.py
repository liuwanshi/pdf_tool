"""打包工具函数"""

import os
import zipfile
from typing import Sequence


def create_zip(file_paths: Sequence[str], output_path: str) -> str:
    """将多个文件打包为 ZIP，返回 ZIP 文件路径"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            if os.path.isfile(fp):
                zf.write(fp, arcname=os.path.basename(fp))
    return output_path
