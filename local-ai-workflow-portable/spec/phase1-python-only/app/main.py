import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core import Store

ROOT = Path(__file__).resolve().parent.parent
store = Store(os.environ.get('AI_WORKFLOW_DATA', str(ROOT)))
app = FastAPI(title='个人 AI 工作流 · 第一阶段')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])


@app.middleware('http')
async def local_only(request: Request, call_next):
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            return JSONResponse({'detail': '拒绝跨站操作'}, status_code=403)
        if request.headers.get('x-workflow-client') != 'local-ui':
            return JSONResponse({'detail': '缺少本地客户端标识'}, status_code=403)
        if int(request.headers.get('content-length', '0')) > 150000:
            return JSONResponse({'detail': '请求内容过大'}, status_code=413)
    return await call_next(request)


class TaskInput(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    source: str = Field(default='', max_length=100000)


class ReviewInput(BaseModel):
    decision: str
    note: str = Field(min_length=1, max_length=4000)
    source: str | None = Field(default=None, max_length=100000)


@app.exception_handler(KeyError)
async def missing(request, error):
    return JSONResponse({'detail': '任务不存在'}, status_code=404)


@app.exception_handler(ValueError)
async def invalid(request, error):
    return JSONResponse({'detail': str(error)}, status_code=409)


@app.get('/')
def index():
    return FileResponse(ROOT / 'app/index.html')


@app.get('/api/tasks')
def tasks():
    return store.list()


@app.post('/api/tasks', status_code=201)
def create(data: TaskInput):
    if not data.goal.strip():
        raise HTTPException(422, '任务目标不能为空')
    return store.create(data.goal, data.source)


@app.get('/api/tasks/{task_id}')
def detail(task_id: str):
    return store.get(task_id)


@app.post('/api/tasks/{task_id}/run')
def run(task_id: str):
    return store.run(task_id)


@app.post('/api/tasks/{task_id}/review')
def review(task_id: str, data: ReviewInput):
    return store.review(task_id, data.decision, data.note, data.source)
