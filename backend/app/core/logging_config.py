"""日志配置"""
import logging
import os
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

    # stdout handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
