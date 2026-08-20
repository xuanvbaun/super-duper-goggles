"""SQLite 数据库连接与初始化"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
    """创建表，并为旧版 SQLite 数据库执行轻量兼容迁移。"""
    from . import models  # noqa: F401 — 确保模型注册到 Base.metadata

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    migrations = {
        "source_official": "BOOLEAN NOT NULL DEFAULT 0",
        "event_id": "VARCHAR(32)",
        "corroboration_count": "INTEGER NOT NULL DEFAULT 1",
        "corroborating_sources": "TEXT",
        "verification_status": "VARCHAR(32) NOT NULL DEFAULT 'single_source'",
        "official_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(news_articles)"
            ).fetchall()
        }
        for name, ddl in migrations.items():
            if name not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE news_articles ADD COLUMN {name} {ddl}"
                )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_news_articles_event_id ON news_articles (event_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_news_articles_verification_status "
            "ON news_articles (verification_status)"
        )
