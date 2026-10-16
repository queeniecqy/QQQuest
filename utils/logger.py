"""
日誌工具
"""
import os
import sys
from pathlib import Path
from loguru import logger
from config.settings import LOGS_DIR

# 移除預設 handler
logger.remove()

# 控制台輸出（不佔磁碟）— 一律保留
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 檔案輸出：預設「關閉」，避免塞爆磁碟（之前 log 長到數 GB 把碟撐爆）。
# 需要留檔除錯時，啟動前設環境變數 QQQUEST_FILE_LOG=1 即可，且已加大小/數量硬上限。
if os.getenv("QQQUEST_FILE_LOG") == "1":
    logger.add(
        LOGS_DIR / "qqquest_{time:YYYY-MM-DD}.log",
        rotation="10 MB",       # 單檔到 10MB 就輪替
        retention=5,            # 最多保留 5 個（硬上限，最多約 50MB）
        compression="zip",
        encoding="utf-8",
        level="INFO",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )


def get_logger(name: str):
    """取得指定名稱的 logger"""
    return logger.bind(name=name)


# 匯出
__all__ = ['logger', 'get_logger']




