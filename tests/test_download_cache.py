import os
import tempfile
import unittest

from download_cache import DownloadCache


class DownloadCacheTests(unittest.TestCase):
    def test_failed_record_with_partial_file_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = DownloadCache("course", directory)
            output = os.path.join(directory, "lecture.mp4")
            with open(output, "wb") as file:
                file.write(b"partial")
            key = cache.mark_download_started(1, 1, "Lecture", 42, "Video")
            cache.mark_download_failed(key, "network failure")
            self.assertEqual(cache.is_download_completed(1, 1, "Lecture", output), (False, None))

    def test_completed_record_requires_exact_output_size(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = DownloadCache("course", directory)
            output = os.path.join(directory, "lecture.mp4")
            with open(output, "wb") as file:
                file.write(b"complete")
            key = cache.mark_download_started(1, 1, "Lecture", 42, "Video")
            cache.mark_download_completed(key, output)
            self.assertTrue(cache.is_download_completed(1, 1, "Lecture", output)[0])
            with open(output, "ab") as file:
                file.write(b"x")
            self.assertFalse(cache.is_download_completed(1, 1, "Lecture", output)[0])


if __name__ == "__main__":
    unittest.main()
