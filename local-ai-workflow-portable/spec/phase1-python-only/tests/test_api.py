import os
import tempfile
import unittest
from fastapi.testclient import TestClient


class ApiTests(unittest.TestCase):
    def test_api_and_local_access_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ['AI_WORKFLOW_DATA'] = folder
            from app import main
            from app.core import Store
            main.store = Store(folder)
            client = TestClient(main.app)
            headers = {'X-Workflow-Client': 'local-ui'}
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.post('/api/tasks', json={'goal': '数字统计'}).status_code, 403)
            self.assertEqual(client.post('/api/tasks', headers={**headers, 'Origin': 'http://evil.example'}, json={'goal': 'a'}).status_code, 403)
            self.assertEqual(client.get('/', headers={'Host': 'evil.example'}).status_code, 400)
            self.assertEqual(client.post('/api/tasks', headers=headers, json={'goal': '  '}).status_code, 422)
            response = client.post('/api/tasks', headers=headers, json={'goal': '数字统计', 'source': '1 2 3'})
            self.assertEqual(response.status_code, 201)
            key = response.json()['task_id']
            self.assertEqual(client.post(f'/api/tasks/{key}/run', headers=headers, json={}).json()['status'], 'REVIEW')
            self.assertEqual(client.post(f'/api/tasks/{key}/run', headers=headers, json={}).status_code, 409)
            self.assertEqual(client.post(f'/api/tasks/{key}/review', headers=headers, json={'decision': 'approve', 'note': '核对通过'}).json()['status'], 'DONE')
            self.assertEqual(client.get('/api/tasks/missing').status_code, 404)
            os.environ.pop('AI_WORKFLOW_DATA', None)
