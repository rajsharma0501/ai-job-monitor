import unittest
import os
import warnings

from job_monitor import JobMonitor

warnings.filterwarnings("ignore", message=".*LibreSSL.*", category=Warning)


class JobMonitorTests(unittest.TestCase):
    def setUp(self):
        self._orig_env = {
            'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
            'TELEGRAM_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID')
        }
        os.environ['TELEGRAM_BOT_TOKEN'] = 'test-token'
        os.environ['TELEGRAM_CHAT_ID'] = '1'
        self.monitor = JobMonitor()

    def tearDown(self):
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_calculate_job_score_high_priority(self):
        score = self.monitor.calculate_job_score("Principal AI Engineer, Agents", "high")
        self.assertGreaterEqual(score, 80)

    def test_matches_criteria(self):
        self.assertTrue(self.monitor.matches_criteria("Staff ML Engineer"))
        self.assertFalse(self.monitor.matches_criteria("Junior Sales Associate"))

    def test_priority_levels(self):
        self.assertEqual(self.monitor.get_priority_level(80), "URGENT")
        self.assertEqual(self.monitor.get_priority_level(60), "HIGH")
        self.assertEqual(self.monitor.get_priority_level(40), "MEDIUM")
        self.assertEqual(self.monitor.get_priority_level(10), "LOW")

    def test_extract_jobs_from_html(self):
        html = """
        <html><body>
          <a class="job">Principal AI Engineer</a>
          <a class="job">Junior Sales Associate</a>
        </body></html>
        """
        jobs = self.monitor.extract_jobs("TestCo", "https://example.com", html)
        titles = [job["title"] for job in jobs]
        self.assertIn("Principal AI Engineer", titles)
        self.assertNotIn("Junior Sales Associate", titles)

    def test_extract_jobs_respects_max_age(self):
        self.monitor.max_job_age_days = 1
        html = """
        <html><body>
          <a class="job">Principal AI Engineer - 3 days ago</a>
          <a class="job">Principal AI Engineer - 1 day ago</a>
        </body></html>
        """
        jobs = self.monitor.extract_jobs("TestCo", "https://example.com", html)
        titles = [job["title"] for job in jobs]
        self.assertIn("Principal AI Engineer - 1 day ago", titles)
        self.assertNotIn("Principal AI Engineer - 3 days ago", titles)

    def test_job_id_includes_url(self):
        html = """
        <html><body>
          <a class="job" href="/job/123">Principal AI Engineer</a>
          <a class="job" href="/job/456">Principal AI Engineer</a>
        </body></html>
        """
        jobs = self.monitor.extract_jobs("TestCo", "https://example.com", html)
        job_ids = {job["id"] for job in jobs}
        self.assertEqual(len(job_ids), 2)

    def test_config_has_companies(self):
        companies = self.monitor.config.get("companies", [])
        self.assertGreater(len(companies), 0)
        sample = companies[0]
        self.assertIn("name", sample)
        self.assertIn("url", sample)
        self.assertIn("priority", sample)


if __name__ == "__main__":
    unittest.main()
