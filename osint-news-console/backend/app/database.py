"""SQLite 数据库连接与初始化"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import get_config

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def get_engine():
    """获取 SQLAlchemy 引擎单例."""
    global _engine
    if _engine is None:
        config = get_config()
        db_path = config.database.get("path", "data/news.db")

        # 确保数据库文件所在目录存在
        db_file = Path(db_path)
        if not db_file.is_absolute():
            # 相对于 backend/ 目录
            backend_dir = Path(__file__).resolve().parent.parent
            db_file = backend_dir / db_path
        db_file.parent.mkdir(parents=True, exist_ok=True)

        db_url = f"sqlite+aiosqlite:///{db_file}"
        sync_url = f"sqlite:///{db_file}"

        _engine = create_engine(
            sync_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            echo=False,
        )

        # 开启 WAL 模式，提升并发性能
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return _engine


def get_session():
    """获取一个新的数据库会话。"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return _SessionLocal()


def init_db():
    """创建所有表（启动时调用）。"""
    from . import models  # noqa: F401 — 确保模型注册到 Base.metadata
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
