#!/usr/bin/env python3
"""Advanced tests for cache and utilities."""

import os
import shutil
import tempfile
import unittest

from download_cache import DownloadCache
from constants import RetryConfig, sanitize_path, format_time, FileIntegrity
from utils.download_result import DownloadResult


class TestAdvancedCache(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache = DownloadCache("test_9999", cache_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cache_recording_and_retry(self):
        # Mark started
        key = self.cache.mark_download_started(1, 1, "Intro Lecture", 101, "Video")
        self.assertEqual(len(self.cache.get_incomplete_downloads()), 1)

        # Mark failed
        self.cache.mark_download_failed(key, "Network timeout")
        self.assertEqual(len(self.cache.get_failed_downloads()), 1)

        # Retry failed
        reset_count = self.cache.retry_failed()
        self.assertEqual(reset_count, 1)
        self.assertEqual(len(self.cache.get_failed_downloads()), 0)

    def test_chapter_progress_and_export(self):
        key = self.cache.mark_download_started(1, 1, "Test Lesson", 102, "Video")
        # Create dummy file to complete
        dummy_file = os.path.join(self.test_dir, "dummy.mp4")
        with open(dummy_file, "wb") as f:
            f.write(b"content" * 100)

        self.cache.mark_download_completed(key, dummy_file, elapsed_seconds=2.5)

        progress = self.cache.get_chapter_progress()
        self.assertIn(1, progress)
        self.assertEqual(progress[1]["completed"], 1)

        # Export report
        report_path = os.path.join(self.test_dir, "report.md")
        report = self.cache.export_report(report_path)
        self.assertTrue(os.path.isfile(report_path))
        self.assertIn("Course Download Report", report)


class TestConstantsAndResults(unittest.TestCase):
    def test_retry_config(self):
        cfg = RetryConfig(max_retries=3, backoff_factor=2.0)
        self.assertEqual(cfg.delay_for_attempt(0), 2.0)
        self.assertEqual(cfg.delay_for_attempt(1), 4.0)

    def test_sanitize_path(self):
        clean = sanitize_path("01. 🔥 Intro: Welcome! / How to start? 🚀")
        self.assertNotIn("🔥", clean)
        self.assertNotIn("🚀", clean)
        self.assertNotIn("?", clean)
        self.assertNotIn(":", clean)

    def test_format_time(self):
        self.assertEqual(format_time(65), "1min 5s")
        self.assertEqual(format_time(3665), "1hr 1min 5s")

    def test_download_result(self):
        res = DownloadResult.ok(elapsed_seconds=1.2)
        self.assertTrue(res.success)
        self.assertIn("OK", str(res))

        failed = DownloadResult.failed("Something went wrong")
        self.assertFalse(failed.success)
        self.assertIn("FAILED", str(failed))


if __name__ == "__main__":
    unittest.main()
