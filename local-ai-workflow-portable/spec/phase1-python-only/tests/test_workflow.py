import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from app.core import Store, execute, classify


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_lifecycle_persistence_and_review(self):
        task = self.store.create('数字统计', '0.1,0.2')
        key = task['task_id']
        task = self.store.run(key)
        self.assertEqual(task['status'], 'REVIEW')
        self.assertEqual(task['result']['output']['sum'], '0.3')
        self.assertTrue(all(t['passed'] for t in task['tests']))
        self.assertTrue((self.store.root / 'tasks' / key / 'task.json').exists())
        self.assertTrue((self.store.root / 'tasks' / key / 'result.json').exists())
        self.assertEqual(Store(self.temp.name).get(key)['status'], 'REVIEW')
        self.assertEqual(self.store.review(key, 'approve', '已核对源数据')['status'], 'DONE')
        with self.assertRaises(ValueError):
            self.store.run(key)

    def test_retry_budget_and_replan(self):
        key = self.store.create('JSON校验', '{bad')['task_id']
        task = self.store.run(key)
        self.assertEqual((task['status'], task['attempts']), ('REVIEW', 2))
        with self.assertRaises(ValueError):
            self.store.review(key, 'approve', '不能通过')
        self.store.review(key, 'replan', '修正输入', '{still bad')
        task = self.store.run(key)
        self.assertEqual((task['status'], task['attempts']), ('FAILED', 3))
        with self.assertRaises(ValueError):
            self.store.review(key, 'replan', '再次尝试', '{}')

    def test_successful_replan(self):
        key = self.store.create('JSON校验', 'bad')['task_id']
        self.store.run(key)
        self.store.review(key, 'replan', '修复JSON', '{"ok":true}')
        self.assertEqual(self.store.get(key)['previous_plans'][0]['inputs'], ['bad'])
        self.assertEqual(self.store.run(key)['status'], 'REVIEW')

    def test_unconnected_executor_never_done(self):
        for goal, executor in [('修复代码bug', 'codex'), ('翻译文本', 'deepseek'), ('安排项目', 'controller'), ('删除文件', 'controller')]:
            task = self.store.create(goal, '')
            self.assertEqual(task['executor'], executor)
            task = self.store.run(task['task_id'])
            self.assertEqual(task['status'], 'REVIEW')
            self.assertIsNone(task['result'])
            with self.assertRaises(ValueError):
                self.store.review(task['task_id'], 'approve', '通过')

    def test_interruption_goes_to_review(self):
        task = self.store.create('文本统计', 'abc')
        self.store.event(task, 'RUNNING', '模拟进程中断')
        self.assertEqual(Store(self.temp.name).get(task['task_id'])['status'], 'REVIEW')

    def test_concurrent_run_executes_once(self):
        key = self.store.create('数字统计', '1 2 3')['task_id']
        def run():
            try:
                return self.store.run(key)['status']
            except ValueError:
                return 'blocked'
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(sorted(results), ['REVIEW', 'blocked'])
        self.assertEqual(self.store.get(key)['attempts'], 1)

    def test_input_validation(self):
        for source in ['', '1, hello', 'NaN', '1e999999']:
            with self.assertRaises(ValueError):
                execute('numbers', source)
        with self.assertRaises(ValueError):
            execute('json', 'NaN')
        self.assertEqual(execute('text', '你好\n A')['characters'], 5)
        self.assertEqual(execute('json', '{"中文": 1}')['parsed'], {'中文': 1})


if __name__ == '__main__':
    unittest.main()
