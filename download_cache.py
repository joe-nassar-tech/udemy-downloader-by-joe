#!/usr/bin/env python3
"""Thread-safe, atomic download-resume cache."""

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path


class DownloadCache:
    def __init__(self, course_id, cache_dir="cache"):
        self.course_id = str(course_id)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / f"course_{self.course_id}.json"
        self._lock = threading.RLock()
        self.cache_data = self.load_cache()

    def load_cache(self):
        if not self.cache_file.exists():
            return self.create_new_cache()
        try:
            with self.cache_file.open("r", encoding="utf-8") as file:
                cache_data = json.load(file)
            if not isinstance(cache_data.get("downloads"), dict):
                raise json.JSONDecodeError("downloads must be an object", "", 0)
            print(f"Loaded download cache for course {self.course_id}")
            return cache_data
        except (json.JSONDecodeError, OSError) as error:
            backup_path = self.cache_file.with_suffix(self.cache_file.suffix + f".corrupt-{datetime.now():%Y%m%d%H%M%S}")
            try:
                os.replace(self.cache_file, backup_path)
                print(f"Cache was corrupt ({error}); moved it to {backup_path}.")
            except OSError:
                print(f"Cache was corrupt ({error}); creating a new cache.")
            return self.create_new_cache()

    def create_new_cache(self):
        now = datetime.now().isoformat()
        return {"course_id": self.course_id, "created_at": now, "last_updated": now,
                "total_downloads": 0, "completed_downloads": 0,
                "failed_downloads": 0, "downloads": {}, "curriculum": None}

    def save_cache(self):
        with self._lock:
            self.cache_data["last_updated"] = datetime.now().isoformat()
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=self.cache_dir, suffix=".tmp") as file:
                    json.dump(self.cache_data, file, indent=2, ensure_ascii=False)
                    temp_name = file.name
                os.replace(temp_name, self.cache_file)
            except OSError as error:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
                print(f"Failed to save cache: {error}")

    def get_download_key(self, chapter_index, lecture_index, lecture_title):
        key_string = f"{chapter_index}_{lecture_index}_{lecture_title}"
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()[:24]

    def is_download_completed(self, chapter_index, lecture_index, lecture_title, expected_path):
        key = self.get_download_key(chapter_index, lecture_index, lecture_title)
        with self._lock:
            record = self.cache_data["downloads"].get(key)
            if not record or record.get("status") != "completed":
                return False, None
            cached_size = record.get("file_size", 0)
        if not os.path.isfile(expected_path) or cached_size <= 0:
            return False, None
        return (os.path.getsize(expected_path) == cached_size), record

    def mark_download_started(self, chapter_index, lecture_index, lecture_title, lecture_id, asset_type):
        key = self.get_download_key(chapter_index, lecture_index, lecture_title)
        with self._lock:
            previous = self.cache_data["downloads"].get(key, {})
            self.cache_data["downloads"][key] = {
                "chapter_index": chapter_index, "lecture_index": lecture_index,
                "lecture_title": lecture_title, "lecture_id": lecture_id,
                "asset_type": asset_type, "status": "started",
                "started_at": datetime.now().isoformat(), "file_size": 0,
                "file_path": "", "attempts": previous.get("attempts", 0) + 1,
            }
            self._sync_counts()
            self.save_cache()
        return key

    def mark_download_completed(self, key, file_path):
        if not os.path.isfile(file_path) or os.path.getsize(file_path) <= 0:
            self.mark_download_failed(key, "Expected output file was not created or is empty.")
            return
        with self._lock:
            if key not in self.cache_data["downloads"]:
                return
            self.cache_data["downloads"][key].update({"status": "completed", "completed_at": datetime.now().isoformat(),
                                                        "file_path": str(file_path), "file_size": os.path.getsize(file_path)})
            self._sync_counts()
            self.save_cache()

    def mark_download_failed(self, key, error_message=""):
        with self._lock:
            record = self.cache_data["downloads"].get(key)
            if not record:
                return
            record.update({"status": "failed", "failed_at": datetime.now().isoformat(), "error": str(error_message)})
            self._sync_counts()
            self.save_cache()

    def _sync_counts(self):
        summary = self.get_download_summary()
        self.cache_data["completed_downloads"] = summary["completed"]
        self.cache_data["failed_downloads"] = summary["failed"]

    def get_download_summary(self):
        with self._lock:
            records = list(self.cache_data["downloads"].values())
        completed = sum(record.get("status") == "completed" for record in records)
        failed = sum(record.get("status") == "failed" for record in records)
        total = len(records)
        return {"total": total, "completed": completed, "failed": failed,
                "in_progress": total - completed - failed,
                "completion_rate": (completed / total * 100) if total else 0}

    def get_failed_downloads(self):
        with self._lock:
            return [(key, data.copy()) for key, data in self.cache_data["downloads"].items() if data.get("status") == "failed"]

    def reset_failed_downloads(self):
        with self._lock:
            for record in self.cache_data["downloads"].values():
                if record.get("status") == "failed":
                    record.update({"status": "pending"})
                    record.pop("failed_at", None)
                    record.pop("error", None)
            self._sync_counts()
            self.save_cache()

    def save_curriculum(self, curriculum):
        with self._lock:
            self.cache_data["curriculum"] = curriculum
            self.cache_data["total_downloads"] = sum(len(chapter.get("children", [])) for chapter in curriculum)
            self.save_cache()

    def print_progress_summary(self):
        summary = self.get_download_summary()
        print("=" * 60)
        print("DOWNLOAD PROGRESS SUMMARY")
        print("=" * 60)
        print(f"Course ID: {self.course_id}")
        print(f"Tracked: {summary['total']}")
        print(f"Completed: {summary['completed']}")
        print(f"Failed: {summary['failed']}")
        print(f"In progress: {summary['in_progress']}")
        print(f"Completion rate: {summary['completion_rate']:.1f}%")
        if summary["failed"]:
            print("Failed items will be retried on the next run.")
        print("=" * 60)

    def clear_cache(self):
        with self._lock:
            if self.cache_file.exists():
                self.cache_file.unlink()
            self.cache_data = self.create_new_cache()
