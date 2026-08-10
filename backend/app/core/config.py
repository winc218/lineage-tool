"""应用配置 - 从环境变量读取"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 数据库
    DB_MODE: str = "sqlite"  # sqlite / sqlserver / goldendb
    DB_CONN: str = ""  # 非 sqlite 时使用

    # JWT
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # 管理员
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # 数据目录
    DATA_DIR: str = "/app/data"

    # 日志目录
    LOG_DIR: str = "/app/logs"

    # Git 可执行文件路径（离线部署时指定内置 git）
    GIT_EXECUTABLE: str = ""

    # 配置加密密钥（用于加密工作空间数据库连接串）
    CONFIG_ENCRYPT_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env")

    def model_post_init(self, __context):
        """初始化后设置 git 路径到环境变量"""
        if self.GIT_EXECUTABLE:
            # 支持相对路径，基于 .env 所在目录解析
            if not os.path.isabs(self.GIT_EXECUTABLE):
                self.GIT_EXECUTABLE = os.path.abspath(self.GIT_EXECUTABLE)
            os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = self.GIT_EXECUTABLE


settings = Settings()


def get_db_url() -> str:
    """根据 DB_MODE 返回 SQLAlchemy 连接串"""
    mode = settings.DB_MODE.lower()
    if mode == "sqlite":
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        return f"sqlite:///{settings.DATA_DIR}/lineage.db"
    if mode == "sqlserver":
        return settings.DB_CONN or "mssql+pymssql://sa:sa@localhost:1433/master"
    if mode == "goldendb":
        return settings.DB_CONN or "mysql+pymysql://root:root@localhost:3306/test"
    raise ValueError(f"不支持的 DB_MODE: {mode}")
