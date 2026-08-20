"""FastAPI 应用入口 — 单体后端

启动方式: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ai_processor import process_unprocessed_articles
from .collector import collect_all, start_scheduler, stop_scheduler
from .config import get_config
from .database import init_db
from .router import router
from .rule_engine import cleanup_old_articles, score_articles
from .verification import cluster_recent_articles

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("osint-console")


# ---- 定时 AI 处理任务 ----
_ai_job_id = "ai_processing"
_ai_lock = asyncio.Lock()


async def _scheduled_ai_process():
    """定时处理未处理的新闻（采集后自动触发）。"""
    async with _ai_lock:
        try:
            config = get_config().ai
            processed = await process_unprocessed_articles(batch_size=config.batch_size)
            clustered = cluster_recent_articles()
            scored = score_articles(force=True)
            if processed > 0 or clustered["articles"] > 0:
                logger.info(
                    "AI 处理 %s 条，事件 %s 个，重算评分 %s 条",
                    processed,
                    clustered["events"],
                    scored,
                )
        except Exception as e:  # noqa: BLE001 - 定时任务失败不能终止服务
            logger.error(f"定时 AI 处理异常: {e}")


async def _initial_pipeline():
    """后台执行首次采集，避免 Ollama 推理阻塞 Web 服务启动。"""
    try:
        logger.info("后台执行首次 RSS 采集...")
        await collect_all()
        logger.info("后台执行首次 AI 处理、事件聚类和评分...")
        await _scheduled_ai_process()
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - 后台初始化失败不能终止服务
        logger.error("首次采集流程异常: %s", e)


async def _scheduled_cleanup():
    """定时清理过期数据。"""
    try:
        deleted = cleanup_old_articles()
        if deleted > 0:
            logger.info(f"每日清理：{deleted} 条")
    except Exception as e:  # noqa: BLE001 - 定时任务失败不能终止服务
        logger.error(f"定时清理异常: {e}")


async def _scheduled_daily():
    """每日凌晨预生成昨日 HTML 报纸。"""
    try:
        from .daily_report import generate_yesterday_html

        html = generate_yesterday_html()
        if html:
            logger.info("每日 HTML 报纸已生成")
    except Exception as e:  # noqa: BLE001 - 定时任务失败不能终止服务
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
    from .collector import _scheduler as collector_scheduler

    if collector_scheduler:
        collector_scheduler.add_job(
            _scheduled_ai_process,
            "interval",
            minutes=get_config().ai.interval_minutes,
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
        logger.info(
            f"定时任务已注册: AI处理 + 清理({cleanup_hour}:00) + 报纸({cleanup_hour}:30)"
        )

    # 首次采集与日报放入后台，Web 服务可立即响应健康检查和页面请求。
    initial_task = asyncio.create_task(_initial_pipeline())
    daily_task = asyncio.create_task(_scheduled_daily())

    logger.info("=" * 50)
    logger.info("启动完成！API 文档: http://localhost:8000/docs")
    logger.info("=" * 50)

    yield  # 应用运行中...

    # 关闭
    logger.info("应用关闭中...")
    stop_scheduler()
    for task in (initial_task, daily_task):
        if not task.done():
            task.cancel()
    await asyncio.gather(initial_task, daily_task, return_exceptions=True)
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
    allow_origins=config.server.cors_origins,
    allow_credentials=False,
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
