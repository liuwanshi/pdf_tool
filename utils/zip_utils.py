"""打包工具函数

提供将多个文件压缩为 ZIP 包的功能。
"""

import os
import zipfile
from typing import Sequence


def create_zip(file_paths: Sequence[str], output_path: str) -> str:
    """将多个文件打包为 ZIP，返回 ZIP 文件路径

    参数说明：
    - file_paths: 待打包文件的绝对路径列表
    - output_path: 输出 ZIP 文件的完整路径（目录不存在会自动创建）

    实现细节：
    - 使用 ZIP_DEFLATED 压缩算法（标准 deflate，兼容所有解压工具）
    - arcname 设为文件原名（去除路径前缀），解压后所有文件在同一目录
    """
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # ZIP_DEFLATED: 标准 deflate 压缩，兼容性好
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            if os.path.isfile(fp):
                # arcname 用 basename 去除路径前缀，解压后文件集中在同一目录
                zf.write(fp, arcname=os.path.basename(fp))
    return output_path
