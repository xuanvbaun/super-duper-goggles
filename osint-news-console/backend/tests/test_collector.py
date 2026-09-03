import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import collector


class FakeScheduler:
    def __init__(self):
        self.job_kwargs = None
        self.started = False

    def add_job(self, *args, **kwargs):
        self.job_kwargs = kwargs

    def start(self):
        self.started = True

    def shutdown(self, wait=True):
        pass


class SchedulerTests(unittest.TestCase):
    def tearDown(self):
        collector._scheduler = None

    def test_recurring_collection_job_is_not_created_paused(self):
        config = SimpleNamespace(collector=SimpleNamespace(interval_minutes=15))

        with patch.object(collector, "AsyncIOScheduler", FakeScheduler), patch.object(
            collector, "get_config", return_value=config
        ):
            collector._scheduler = None
            collector.start_scheduler()

        scheduler = collector._scheduler
        self.assertTrue(scheduler.started)
        self.assertEqual(scheduler.job_kwargs["minutes"], 15)
        self.assertNotIn("next_run_time", scheduler.job_kwargs)


if __name__ == "__main__":
    unittest.main()
