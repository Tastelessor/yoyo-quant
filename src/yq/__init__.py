"""yq：yoyo-quant 命令行工具。

子命令组：
- ``yq factor list|run|evaluate``：因子注册表查询、计算、IC/IR 评估
- ``yq cache info|clear``：因子磁盘缓存统计与清理
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yoyo-quant")
except PackageNotFoundError:  # 未安装（直接跑源码）时回退
    __version__ = "0.1.0"
