#!/usr/bin/env python3
"""Thread-safe, atomic download-resume cache with reporting and Rich visualization."""

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


class DownloadCache:
    def __init__(self, course_id, cache_dir="cache"):
        self.course_id = str(course_id)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / f"course_{self.course_id}.json"
        self._lock = threading.RLock()
        self.cache_data = self.load_cache()

    def load_cache(self) -> dict:
        if not self.cache_file.exists():
            return self.create_new_cache()
        try:
            with self.cache_file.open("r", encoding="utf-8") as file:
                cache_data = json.load(file)
            if not isinstance(cache_data.get("downloads"), dict):
                raise json.JSONDecodeError("downloads must be an object", "", 0)
            return cache_data
        except (json.JSONDecodeError, OSError) as error:
            backup_path = self.cache_file.with_suffix(
                self.cache_file.suffix + f".corrupt-{datetime.now():%Y%m%d%H%M%S}"
            )
            try:
                os.replace(self.cache_file, backup_path)
                print(f"Cache was corrupt ({error}); moved it to {backup_path}.")
            except OSError:
                print(f"Cache was corrupt ({error}); creating a new cache.")
            return self.create_new_cache()

    def create_new_cache(self) -> dict:
        now = datetime.now().isoformat()
        return {
            "course_id": self.course_id,
            "created_at": now,
            "last_updated": now,
            "total_downloads": 0,
            "completed_downloads": 0,
            "failed_downloads": 0,
            "downloads": {},
            "curriculum": None,
        }

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
                    try:
                        os.unlink(temp_name)
                    except OSError:
                        pass
                print(f"Failed to save cache: {error}")

    def get_download_key(self, chapter_index, lecture_index, lecture_title) -> str:
        key_string = f"{chapter_index}_{lecture_index}_{lecture_title}"
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()[:24]

    def is_download_completed(self, chapter_index, lecture_index, lecture_title, expected_path) -> Tuple[bool, Optional[dict]]:
        key = self.get_download_key(chapter_index, lecture_index, lecture_title)
        with self._lock:
            record = self.cache_data["downloads"].get(key)
            if not record or record.get("status") != "completed":
                return False, None
            cached_size = record.get("file_size", 0)
        if not os.path.isfile(expected_path) or cached_size <= 0:
            return False, None
        return (os.path.getsize(expected_path) == cached_size), record

    def mark_download_started(self, chapter_index, lecture_index, lecture_title, lecture_id, asset_type) -> str:
        key = self.get_download_key(chapter_index, lecture_index, lecture_title)
        with self._lock:
            previous = self.cache_data["downloads"].get(key, {})
            self.cache_data["downloads"][key] = {
                "chapter_index": chapter_index,
                "lecture_index": lecture_index,
                "lecture_title": lecture_title,
                "lecture_id": lecture_id,
                "asset_type": asset_type,
                "status": "started",
                "started_at": datetime.now().isoformat(),
                "file_size": 0,
                "file_path": "",
                "attempts": previous.get("attempts", 0) + 1,
            }
            self._sync_counts()
            self.save_cache()
        return key

    def mark_download_completed(self, key: str, file_path: str, elapsed_seconds: float = 0.0):
        if not os.path.isfile(file_path) or os.path.getsize(file_path) <= 0:
            self.mark_download_failed(key, "Expected output file was not created or is empty.")
            return
        with self._lock:
            if key not in self.cache_data["downloads"]:
                return
            size = os.path.getsize(file_path)
            self.cache_data["downloads"][key].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "file_path": str(file_path),
                "file_size": size,
                "elapsed_seconds": round(elapsed_seconds, 2),
            })
            self._sync_counts()
            self.save_cache()

    def mark_download_failed(self, key: str, error_message: str = ""):
        with self._lock:
            record = self.cache_data["downloads"].get(key)
            if not record:
                return
            record.update({
                "status": "failed",
                "failed_at": datetime.now().isoformat(),
                "error": str(error_message),
            })
            self._sync_counts()
            self.save_cache()

    def _sync_counts(self):
        summary = self.get_download_summary()
        self.cache_data["completed_downloads"] = summary["completed"]
        self.cache_data["failed_downloads"] = summary["failed"]

    def get_download_summary(self) -> dict:
        with self._lock:
            records = list(self.cache_data["downloads"].values())
        completed = sum(record.get("status") == "completed" for record in records)
        failed = sum(record.get("status") == "failed" for record in records)
        total_size = sum(record.get("file_size", 0) for record in records if record.get("status") == "completed")
        total = len(records)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": total - completed - failed,
            "total_bytes": total_size,
            "completion_rate": (completed / total * 100) if total else 0.0,
        }

    def get_failed_downloads(self) -> List[Tuple[str, dict]]:
        with self._lock:
            return [(key, data.copy()) for key, data in self.cache_data["downloads"].items() if data.get("status") == "failed"]

    def get_incomplete_downloads(self) -> List[Tuple[str, dict]]:
        """Returns downloads that are either started, pending or failed."""
        with self._lock:
            return [
                (key, data.copy())
                for key, data in self.cache_data["downloads"].items()
                if data.get("status") in ("failed", "started", "pending")
            ]

    def reset_failed_downloads(self) -> int:
        """Resets failed downloads to pending state and returns count."""
        with self._lock:
            count = 0
            for record in self.cache_data["downloads"].values():
                if record.get("status") == "failed":
                    record.update({"status": "pending"})
                    record.pop("failed_at", None)
                    record.pop("error", None)
                    count += 1
            self._sync_counts()
            self.save_cache()
            return count

    def retry_failed(self) -> int:
        """Alias for reset_failed_downloads."""
        return self.reset_failed_downloads()

    def get_chapter_progress(self) -> Dict[int, dict]:
        """Calculates completed, failed, and total downloads per chapter."""
        with self._lock:
            chapters = {}
            for record in self.cache_data["downloads"].values():
                ch = record.get("chapter_index", 0)
                if ch not in chapters:
                    chapters[ch] = {"total": 0, "completed": 0, "failed": 0, "size": 0}
                chapters[ch]["total"] += 1
                if record.get("status") == "completed":
                    chapters[ch]["completed"] += 1
                    chapters[ch]["size"] += record.get("file_size", 0)
                elif record.get("status") == "failed":
                    chapters[ch]["failed"] += 1
            return dict(sorted(chapters.items()))

    def save_curriculum(self, curriculum):
        with self._lock:
            self.cache_data["curriculum"] = curriculum
            self.cache_data["total_downloads"] = sum(len(chapter.get("children", [])) for chapter in curriculum)
            self.save_cache()

    def print_progress_summary(self):
        summary = self.get_download_summary()
        mb_downloaded = summary["total_bytes"] / (1024 * 1024)

        if _HAS_RICH:
            console = Console()
            table = Table(title=f"📊 Download Cache Summary — Course {self.course_id}", header_style="bold magenta")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="bold white")

            table.add_row("Tracked Items", str(summary["total"]))
            table.add_row("Completed", f"[green]{summary['completed']}[/green]")
            table.add_row("Failed", f"[red]{summary['failed']}[/red]" if summary['failed'] else "0")
            table.add_row("In Progress", str(summary["in_progress"]))
            table.add_row("Downloaded Data", f"{mb_downloaded:.2f} MB" if mb_downloaded < 1024 else f"{mb_downloaded / 1024:.2f} GB")
            table.add_row("Completion Rate", f"{summary['completion_rate']:.1f}%")

            console.print(table)

            ch_progress = self.get_chapter_progress()
            if ch_progress:
                ch_table = Table(title="📑 Chapter Breakdown", header_style="bold blue")
                ch_table.add_column("Chapter", justify="right")
                ch_table.add_column("Completed", justify="right")
                ch_table.add_column("Total", justify="right")
                ch_table.add_column("Progress", justify="right")

                for ch_num, stats in ch_progress.items():
                    rate = (stats["completed"] / stats["total"] * 100) if stats["total"] else 0
                    ch_table.add_row(
                        f"Ch {ch_num:02d}",
                        str(stats["completed"]),
                        str(stats["total"]),
                        f"{rate:.0f}%",
                    )
                console.print(ch_table)

            if summary["failed"]:
                console.print("[yellow]⚠️  Failed items will be retried on the next run with --retry-failed.[/yellow]")
        else:
            print("=" * 60)
            print(f"DOWNLOAD PROGRESS SUMMARY — Course {self.course_id}")
            print("=" * 60)
            print(f"Tracked: {summary['total']}")
            print(f"Completed: {summary['completed']}")
            print(f"Failed: {summary['failed']}")
            print(f"In progress: {summary['in_progress']}")
            print(f"Downloaded: {mb_downloaded:.2f} MB")
            print(f"Completion rate: {summary['completion_rate']:.1f}%")
            if summary["failed"]:
                print("Failed items will be retried on the next run.")
            print("=" * 60)

    def export_report(self, filepath: Optional[str] = None) -> str:
        """Exports a Markdown report of the course download progress."""
        summary = self.get_download_summary()
        mb = summary["total_bytes"] / (1024 * 1024)
        size_str = f"{mb:.2f} MB" if mb < 1024 else f"{mb / 1024:.2f} GB"

        lines = [
            f"# Course Download Report — Course ID: {self.course_id}",
            f"\n*Generated at: {datetime.now():%Y-%m-%d %H:%M:%S}*",
            "\n## Global Summary",
            f"- **Total items:** {summary['total']}",
            f"- **Completed:** {summary['completed']} ({summary['completion_rate']:.1f}%)",
            f"- **Failed:** {summary['failed']}",
            f"- **In progress:** {summary['in_progress']}",
            f"- **Total size:** {size_str}",
            "\n## Chapter Progress",
            "| Chapter | Completed | Total | Progress | Size |",
            "|---|---|---|---|---|",
        ]

        ch_progress = self.get_chapter_progress()
        for ch, s in ch_progress.items():
            rate = (s["completed"] / s["total"] * 100) if s["total"] else 0
            ch_mb = s["size"] / (1024 * 1024)
            lines.append(f"| Chapter {ch:02d} | {s['completed']} | {s['total']} | {rate:.1f}% | {ch_mb:.1f} MB |")

        failed = self.get_failed_downloads()
        if failed:
            lines.append("\n## Failed Downloads")
            for _, d in failed:
                lines.append(f"- **Ch {d.get('chapter_index')}, Lect {d.get('lecture_index')}**: {d.get('lecture_title')}")
                lines.append(f"  - Error: `{d.get('error', 'Unknown')}`")
                lines.append(f"  - Attempts: {d.get('attempts', 1)}")

        report_content = "\n".join(lines)
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report_content)
        return report_content

    def clear_cache(self):
        with self._lock:
            if self.cache_file.exists():
                self.cache_file.unlink()
            self.cache_data = self.create_new_cache()
