"""Phase-one scheduler. SQLite is authoritative; JSON files are recoverable mirrors."""
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
from contextlib import contextmanager


def now():
    return datetime.now(timezone.utc).isoformat()


def classify(goal):
    text = goal.lower()
    if any(x in text for x in ('删除', '覆盖', '密钥', 'force push', '重写历史')):
        return 'controller', None, '涉及高风险操作，仅交接，不执行'
    if any(x in text for x in ('代码', '仓库', 'bug', '重构')):
        return 'codex', None, '代码执行器将在第三阶段接入'
    if 'json' in text and any(x in text for x in ('校验', '验证', '格式化')):
        return 'python', 'json', '使用确定性 JSON 解析器'
    if any(x in text for x in ('求和', '数字统计', '平均值')):
        return 'python', 'numbers', '使用十进制数字统计'
    if any(x in text for x in ('字数', '字符统计', '文本统计')):
        return 'python', 'text', '使用确定性文本计数'
    if any(x in text for x in ('翻译', '摘要', '总结', '提取', '分类')):
        return 'deepseek', None, 'AI 文本执行器将在第二阶段接入'
    return 'controller', None, '需要总控进一步拆解；第一阶段仅支持三个内置操作'


def execute(operation, source):
    if operation == 'text':
        return {'characters': len(source), 'lines': len(source.splitlines()),
                'non_whitespace': sum(not c.isspace() for c in source)}
    if operation == 'json':
        def reject(value):
            raise ValueError('JSON 不允许 NaN 或 Infinity')
        return {'parsed': json.loads(source, parse_constant=reject)}
    if operation == 'numbers':
        tokens = re.split(r'[,，\s]+', source.strip())
        if not source.strip() or len(tokens) > 10000:
            raise ValueError('请输入 1 至 10000 个以空格或逗号分隔的数字')
        if any(not re.fullmatch(r'[+-]?\d{1,15}(?:\.\d{1,6})?', t) for t in tokens):
            raise ValueError('仅支持最多15位整数、6位小数；不允许其他文本')
        values = [Decimal(t) for t in tokens]
        return {'count': len(values), 'sum': str(sum(values)),
                'average': str(sum(values) / len(values)),
                'min': str(min(values)), 'max': str(max(values))}
    raise ValueError('不支持的操作')


def verify(operation, source, output):
    tests = [{'name': '结果可序列化', 'passed': bool(json.dumps(output, allow_nan=False))}]
    if operation == 'text':
        ok = output['characters'] == len(source)
        ok = ok and output['non_whitespace'] == len(re.sub(r'\s', '', source))
        ok = ok and output['lines'] == len(source.splitlines())
    elif operation == 'numbers':
        values = [Decimal(t) for t in re.split(r'[,，\s]+', source.strip())]
        ok = output['count'] == len(values) and Decimal(output['sum']) == sum(values)
        ok = ok and Decimal(output['min']) == min(values) and Decimal(output['max']) == max(values)
        ok = ok and Decimal(output['average']) == sum(values) / len(values)
    else:
        ok = output['parsed'] == json.loads(source)
    tests.append({'name': '源数据一致性', 'passed': ok})
    return tests


class Store:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / 'data').mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = self.root / 'data/app.db'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        # Never resume side effects after an interrupted process.
        for task in self.list():
            if task['status'] in ('RUNNING', 'VERIFYING'):
                task['error'] = '服务中断，执行结果未知；请总控检查'
                self.event(task, 'REVIEW', task['error'])

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, task):
        task['updated_at'] = now()
        body = json.dumps(task, ensure_ascii=False, indent=2)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?, ?)', (task['task_id'], body))
        folder = self.root / 'tasks' / task['task_id']
        (folder / 'logs').mkdir(parents=True, exist_ok=True)
        self.atomic(folder / 'task.json', body)
        self.atomic(folder / 'logs/events.json', json.dumps(task['events'], ensure_ascii=False, indent=2))
        self.atomic(folder / 'result.json', json.dumps(task['result'], ensure_ascii=False, indent=2))

    @staticmethod
    def atomic(path, text):
        temp = path.with_suffix('.tmp')
        temp.write_text(text, encoding='utf-8')
        temp.replace(path)

    def get(self, task_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return json.loads(row[0])

    def list(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM tasks ORDER BY rowid DESC')]

    def event(self, task, status, message):
        task['status'] = status
        task['events'].append({'at': now(), 'status': status, 'message': message})
        self.save(task)

    def create(self, goal, source):
        with self.lock:
            executor, operation, reason = classify(goal)
            task = dict(task_id='TASK-' + uuid.uuid4().hex[:12], project_id='example-project',
                        goal=goal, context=[], constraints=['第一阶段不调用外部 AI 或执行任意命令'],
                        inputs=[source], expected_output=[operation or '总控方案'], executor=executor,
                        operation=operation, status='NEW', result=None, tests=[], risks=[],
                        created_at=now(), updated_at=now(), events=[], attempts=0, replans=0,
                        error=None, review=None)
            self.event(task, 'NEW', '创建任务')
            self.event(task, 'PLANNED', reason)
            return task

    def run(self, task_id):
        with self.lock:
            task = self.get(task_id)
            if task['status'] != 'PLANNED':
                raise ValueError('任务不能重复执行；仅 PLANNED 可执行')
            if task['executor'] != 'python':
                self.event(task, 'REVIEW', '执行器尚未接入，等待总控处理')
                return task
            budget = 1 if task['replans'] else 2
            for _ in range(budget):
                task['attempts'] += 1
                self.event(task, 'RUNNING', f"执行尝试 {task['attempts']}")
                try:
                    output = execute(task['operation'], task['inputs'][0])
                    self.event(task, 'VERIFYING', '验证输出与源数据')
                    task['tests'] = verify(task['operation'], task['inputs'][0], output)
                    if not all(t['passed'] for t in task['tests']):
                        raise ValueError('自动验证未通过')
                    task['result'] = {'summary': '执行完成，等待验收。', 'modified': [],
                                      'generated': ['result.json'], 'output': output,
                                      'tests': task['tests'], 'goal_met': '客观指标通过，待人工判断',
                                      'remaining': ['总控验收'], 'uncertainties': ['自然语言目标需人工复核'],
                                      'risks': []}
                    task['error'] = None
                    self.event(task, 'REVIEW', '自动验证通过，等待验收')
                    return task
                except (ValueError, ArithmeticError, TypeError) as error:
                    task['error'] = str(error)[:1000]
                    self.event(task, 'FAILED', task['error'])
            if not task['replans']:
                self.event(task, 'REVIEW', '已达到两次尝试上限；允许总控调整输入并重规划一次')
            return task

    def review(self, task_id, decision, note, source=None):
        with self.lock:
            task = self.get(task_id)
            if task['status'] != 'REVIEW':
                raise ValueError('仅 REVIEW 状态可验收')
            if not note.strip():
                raise ValueError('请填写验收或重规划说明')
            if decision == 'approve':
                if task['error'] or not task['result'] or not task['tests'] or not all(t['passed'] for t in task['tests']):
                    raise ValueError('无有效执行结果或测试未通过，无法批准')
                status = 'DONE'
            elif decision == 'reject':
                status = 'FAILED'
            elif decision == 'replan':
                if task['replans'] or task['executor'] != 'python' or source is None:
                    raise ValueError('仅 Python 任务允许一次调整输入后的重规划')
                task['replans'] += 1
                task.setdefault('previous_plans', []).append({
                    'inputs': task['inputs'], 'result': task['result'],
                    'tests': task['tests'], 'error': task['error'], 'at': now()})
                task['inputs'] = [source]
                task['result'], task['tests'], task['error'] = None, [], None
                status = 'PLANNED'
            else:
                raise ValueError('未知决策')
            task['review'] = {'decision': decision, 'note': note, 'at': now(), 'actor': 'local-user'}
            self.event(task, status, note)
            return task
