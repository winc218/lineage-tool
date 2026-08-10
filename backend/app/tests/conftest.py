"""pytest 配置"""
import os
import sys

# 使用测试专用 SQLite
os.environ["DB_MODE"] = "sqlite"
os.environ["DATA_DIR"] = "./test_data"
os.environ["JWT_SECRET"] = "test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
