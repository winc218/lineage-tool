"""日志配置"""
import logging
import os
import sys
import traceback
from logging.handlers import TimedRotatingFileHandler


def setup_logging():
    """配置日志：stdout + rolling 文件（7 天）"""
    log_dir = os.environ.get("LOG_DIR", "./logs")
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler（按天滚动，保留 7 天）
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "lineage.log"),
        when="midnight", backupCount=7, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    # stdout handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # 抑制第三方库的过多日志
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def log_exception(logger: logging.Logger, e: Exception, context: str = ""):
    """统一异常日志格式，包含完整堆栈"""
    tb = traceback.format_exc()
    if context:
        logger.error(f"[{context}] {type(e).__name__}: {e}\n{tb}")
    else:
        logger.error(f"{type(e).__name__}: {e}\n{tb}")
