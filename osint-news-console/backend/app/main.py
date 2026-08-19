"""FastAPI 应用入口 — 单体后端

启动方式: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_config
from .database import init_db
from .collector import start_scheduler, stop_scheduler, collect_all
from .ai_processor import process_unprocessed_articles
from .rule_engine import score_all_unscored, cleanup_old_articles
from .router import router

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("osint-console")


# ---- 定时 AI 处理任务 ----
_ai_job_id = "ai_processing"


async def _scheduled_ai_process():
    """定时处理未处理的新闻（采集后自动触发）。"""
    try:
        processed = await process_unprocessed_articles(batch_size=10)
        if processed > 0:
            scored = score_all_unscored()
            logger.info(f"AI 处理 {processed} 条，评分 {scored} 条")
    except Exception as e:
        logger.error(f"定时 AI 处理异常: {e}")


async def _scheduled_cleanup():
    """定时清理过期数据。"""
    try:
        deleted = cleanup_old_articles()
        if deleted > 0:
            logger.info(f"每日清理：{deleted} 条")
    except Exception as e:
        logger.error(f"定时清理异常: {e}")


async def _scheduled_daily():
    """每日凌晨预生成昨日 HTML 报纸。"""
    try:
        from .daily_report import generate_yesterday_html
        html = generate_yesterday_html()
        if html:
            logger.info("每日 HTML 报纸已生成")
    except Exception as e:
        logger.error(f"每日报纸生成异常: {e}")


# ---- 应用生命周期 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的操作。"""
    logger.info("=" * 50)
    logger.info("OSINT 新闻控制台 v1.0 MVP 启动中...")
    logger.info("=" * 50)

    # 初始化数据库
    init_db()
    logger.info("数据库初始化完成")

    # 启动 RSS 采集调度器
    start_scheduler()

    # 添加 AI 处理定时任务（每 10 分钟检查一次）
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from .collector import _scheduler as collector_scheduler

    if collector_scheduler:
        collector_scheduler.add_job(
            _scheduled_ai_process,
            "interval",
            minutes=5,
            id=_ai_job_id,
            name="AI 定时处理",
        )
        # 每日凌晨清理任务
        cleanup_hour = get_config().cleanup.schedule_hour
        collector_scheduler.add_job(
            _scheduled_cleanup,
            "cron",
            hour=cleanup_hour,
            minute=0,
            id="cleanup_job",
            name="7天数据清理",
        )
        # 每日 HTML 报纸预生成（清理后 30 分钟）
        collector_scheduler.add_job(
            _scheduled_daily,
            "cron",
            hour=cleanup_hour,
            minute=30,
            id="daily_job",
            name="每日HTML报纸",
        )
        logger.info(f"定时任务已注册: AI处理 + 清理({cleanup_hour}:00) + 报纸({cleanup_hour}:30)")

    # 启动时立即执行一次采集
    logger.info("执行首次 RSS 采集...")
    await collect_all()
    logger.info("执行首次 AI 处理...")
    await _scheduled_ai_process()

    # 启动时预生成昨日 HTML 报纸（异步，不阻塞启动）
    logger.info("预生成昨日 HTML 报纸...")
    import asyncio
    asyncio.create_task(_scheduled_daily())

    logger.info("=" * 50)
    logger.info("启动完成！API 文档: http://localhost:8000/docs")
    logger.info("=" * 50)

    yield  # 应用运行中...

    # 关闭
    logger.info("应用关闭中...")
    stop_scheduler()
    logger.info("再见！")


# ---- 创建应用 ----
config = get_config()

app = FastAPI(
    title="OSINT 新闻控制台",
    version="1.0.0",
    description="个人轻量 OSINT 新闻聚合控制台 — MVP",
    lifespan=lifespan,
)

# CORS — 开发阶段允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ---- 根路径 ----
@app.get("/")
def root():
    return {
        "name": "OSINT 新闻控制台",
        "version": "1.0.0",
        "docs": "/docs",
    }
