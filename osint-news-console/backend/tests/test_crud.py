import unittest
from datetime import date

from app.crud import _daily_summaries, _resolve_date_filter


class DateStatisticsTests(unittest.TestCase):
    def test_relative_filters_use_the_supplied_utc_date(self):
        today = date(2026, 9, 3)

        self.assertEqual(_resolve_date_filter("today", today), date(2026, 9, 3))
        self.assertEqual(_resolve_date_filter("yesterday", today), date(2026, 9, 2))
        self.assertEqual(_resolve_date_filter("2026-08-31", today), date(2026, 8, 31))

    def test_missing_yesterday_is_not_replaced_with_an_older_day(self):
        today = date(2026, 9, 3)
        current = {"date": "2026-09-03", "total": 2}
        older = {"date": "2026-09-01", "total": 9}

        today_data, yesterday_data = _daily_summaries([current, older], today)

        self.assertIs(today_data, current)
        self.assertIsNone(yesterday_data)

    def test_exact_yesterday_is_returned_when_present(self):
        today = date(2026, 9, 3)
        yesterday = {"date": "2026-09-02", "total": 4}

        today_data, yesterday_data = _daily_summaries([yesterday], today)

        self.assertIsNone(today_data)
        self.assertIs(yesterday_data, yesterday)


if __name__ == "__main__":
    unittest.main()
