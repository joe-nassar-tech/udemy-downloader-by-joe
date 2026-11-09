import os
import re
import time
import hashlib
import logging
import argparse
from dataclasses import dataclass, field
from itertools import cycle
from threading import Thread
from typing import Set

from rich.progress import TextColumn
from rich.text import Text

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

# ---------------------------------------------------------------------------
# API URLs
# ---------------------------------------------------------------------------
COURSE_URL = "https://udemy.com/api-2.0/courses/{course_id}/"
CURRICULUM_URL = "https://udemy.com/api-2.0/courses/{course_id}/subscriber-curriculum-items/?page_size=200&fields[lecture]=title,object_index,is_published,sort_order,created,asset,supplementary_assets,is_free&fields[quiz]=title,object_index,is_published,sort_order,type&fields[practice]=title,object_index,is_published,sort_order&fields[chapter]=title,object_index,is_published,sort_order&fields[asset]=title,filename,asset_type,status,time_estimation,is_external&caching_intent=True"
LECTURE_URL = "https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course_id}/lectures/{lecture_id}?fields[lecture]=asset,description,download_url,is_free,last_watched_second&fields[asset]=asset_type,media_sources,captions"
QUIZ_URL = "https://udemy.com/api-2.0/quizzes/{quiz_id}/assessments/?version=1&page_size=200&fields[assessment]=id,assessment_type,prompt,correct_response,section,question_plain,related_lectures"
LINK_ASSET_URL = "https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course_id}/lectures/{lecture_id}/supplementary-assets/{asset_id}/?fields[asset]=external_url"
FILE_ASSET_URL = "https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course_id}/lectures/{lecture_id}/supplementary-assets/{asset_id}/?fields[asset]=download_urls"
ARTICLE_URL = "https://www.udemy.com/api-2.0/assets/{article_id}/?fields[asset]=@min,status,delayed_asset_message,processing_errors,body"

# ---------------------------------------------------------------------------
# Directories  (HOME_DIR defined once)
# ---------------------------------------------------------------------------
HOME_DIR = os.getcwd()
DOWNLOAD_DIR = os.path.join(HOME_DIR, "courses")

LOG_DIR = os.path.join(HOME_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOG_DIR, f"{time.strftime('%Y-%m-%d')}.log")

# ---------------------------------------------------------------------------
# RetryConfig dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryConfig:
    """Configuration for HTTP retry behaviour."""
    max_retries: int = 3
    backoff_factor: float = 1.0
    retry_on_status_codes: Set[int] = field(default_factory=lambda: {408, 429, 500, 502, 503, 504})

    def delay_for_attempt(self, attempt: int) -> float:
        """Return the backoff delay (in seconds) for a given attempt (0-based)."""
        return self.backoff_factor * (2 ** attempt)


# Default retry configuration used throughout the project
DEFAULT_RETRY = RetryConfig()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class LogFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    COLOR_CODES = {
        'DEBUG': "\x1b[36m",     # Cyan
        'INFO': "\x1b[32m",      # Green
        'WARNING': "\x1b[33m",   # Yellow
        'ERROR': "\x1b[31m",     # Red
        'CRITICAL': "\x1b[41m",  # Red background
    }

    def format(self, record):
        original_levelname = record.levelname

        log_color = self.COLOR_CODES.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"

        formatted_message = super().format(record)

        record.levelname = original_levelname

        return formatted_message


# Respect LOG_LEVEL env var (default: INFO)
_log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(_log_level)

console_handler = logging.StreamHandler()
console_handler.setLevel(_log_level)
console_handler.setFormatter(LogFormatter('%(asctime)s %(levelname)s : %(message)s'))
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setLevel(logging.DEBUG)  # Always capture everything in the file
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s : %(message)s'))
logger.addHandler(file_handler)

# ---------------------------------------------------------------------------
# Argparse helper
# ---------------------------------------------------------------------------

class LoadAction(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values if values is not None else True)

# ---------------------------------------------------------------------------
# Terminal spinner
# ---------------------------------------------------------------------------

# Source: https://stackoverflow.com/questions/22029562/python-how-to-make-simple-animated-loading-while-process-is-running
class Loader:

    def __init__(self, desc="Processing", timeout=0.1):
        self.desc = desc
        self.timeout = timeout
        self._thread = Thread(target=self._animate, daemon=True)
        self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        self.done = False

    def start(self):
        self._thread.start()
        return self

    def _animate(self):
        for c in cycle(self.steps):
            if self.done:
                break
            print(f"\r{self.desc} {c}", flush=True, end="")
            time.sleep(self.timeout)

    def __enter__(self):
        self.start()
        return self

    def stop(self):
        self.done = True
        # Clear the spinner line
        import shutil
        cols = shutil.get_terminal_size(fallback=(80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print("\r", end="", flush=True)

    def __exit__(self, exc_type, exc_value, tb):
        self.stop()

# ---------------------------------------------------------------------------
# Rich progress columns
# ---------------------------------------------------------------------------

class ElapsedTimeColumn(TextColumn):
    """Shows *per-task* elapsed time instead of a single global timer."""

    def __init__(self, *args, **kwargs):
        super().__init__("{elapsed_time}", *args, **kwargs)
        # Mapping of task_id -> start_time for per-task tracking
        self._task_start_times: dict = {}

    def render(self, task):
        if task.completed >= task.total:
            return Text("Completed", style="green")

        # Record the first time we see a task
        if task.id not in self._task_start_times:
            self._task_start_times[task.id] = time.time()

        elapsed = time.time() - self._task_start_times[task.id]
        formatted_time = f"{elapsed:.2f}s"
        return Text(formatted_time, style="yellow")


class SpeedColumn(TextColumn):
    """Shows current download speed (KB/s or MB/s) per task."""

    def __init__(self, *args, **kwargs):
        super().__init__("{speed}", *args, **kwargs)
        self._task_snapshots: dict = {}  # task_id -> (timestamp, completed_bytes)

    def render(self, task):
        if task.completed >= task.total:
            return Text("")

        now = time.time()
        completed = task.completed  # May be bytes or percentage

        if task.id not in self._task_snapshots:
            self._task_snapshots[task.id] = (now, completed)
            return Text("-- KB/s", style="cyan")

        prev_time, prev_completed = self._task_snapshots[task.id]
        dt = now - prev_time

        if dt < 0.5:
            # Don't update too frequently; return last known text
            return Text("-- KB/s", style="cyan")

        delta_bytes = completed - prev_completed
        self._task_snapshots[task.id] = (now, completed)

        if dt > 0 and delta_bytes > 0:
            speed = delta_bytes / dt  # bytes per second
            if speed >= 1024 * 1024:
                return Text(f"{speed / (1024 * 1024):.1f} MB/s", style="cyan")
            else:
                return Text(f"{speed / 1024:.1f} KB/s", style="cyan")

        return Text("-- KB/s", style="cyan")


# ---------------------------------------------------------------------------
# Text / path sanitisation
# ---------------------------------------------------------------------------

def remove_emojis_and_binary(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map Symbols
        "\U0001F700-\U0001F77F"  # Alchemical Symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed Characters
        "]+",
        flags=re.UNICODE
    )

    text = emoji_pattern.sub(r'', text)

    # Remove Arabic text and keep only safe filename characters
    # Keep alphanumeric, spaces, hyphens, underscores, parentheses, and dots
    text = re.sub(r'[^\w\s\-_().\[\]]+', '', text, flags=re.UNICODE)

    # Clean up multiple spaces and trim
    text = re.sub(r'\s+', ' ', text).strip()

    # If the text is empty or too short after cleaning, use a fallback name
    if len(text.strip()) < 3:
        text = "Course_Content"

    return text


def sanitize_path(text: str) -> str:
    """Convenience wrapper: removes emojis/binary *and* cleans OS-unsafe chars
    using ``pathvalidate.sanitize_filename`` when available, with a regex
    fallback otherwise.  One call instead of two."""
    text = remove_emojis_and_binary(text)
    try:
        from pathvalidate import sanitize_filename
        text = sanitize_filename(text)
    except ImportError:
        # Fallback: strip chars illegal on Windows
        text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', text)
    return text.strip() or "Course_Content"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def timestamp_to_seconds(timestamp):
    hours, minutes, seconds = timestamp.split(':')
    seconds, fraction = seconds.split('.')
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction) / 100
    return total_seconds


def format_time(seconds):
    """Format a duration given in (possibly float) seconds to a human string."""
    seconds = int(seconds)  # safely truncate floats
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)}hr {int(minutes)}min {int(secs)}s"
    return f"{int(minutes)}min {int(secs)}s"


# ---------------------------------------------------------------------------
# Chapter / lecture validators
# ---------------------------------------------------------------------------

def is_valid_chapter(mindex, start_chapter, end_chapter, chapter_filter=None):
    """
    Check if a chapter is valid based on range constraints and optional chapter filter
    """
    range_valid = start_chapter <= mindex <= end_chapter
    filter_valid = chapter_filter is None or mindex in chapter_filter
    return range_valid and filter_valid


def is_valid_lecture(mindex, lindex, start_chapter, start_lecture, end_chapter, end_lecture):
    if mindex == start_chapter and lindex < start_lecture:
        return False
    if mindex == end_chapter and lindex > end_lecture:
        return False
    return True


# ---------------------------------------------------------------------------
# File integrity helper
# ---------------------------------------------------------------------------

class FileIntegrity:
    """Utility class to verify downloaded file integrity."""

    @staticmethod
    def compute_md5(filepath: str, chunk_size: int = 8192) -> str:
        """Compute the MD5 hex digest of a file."""
        md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                md5.update(chunk)
        return md5.hexdigest()

    @staticmethod
    def verify_hash(filepath: str, expected_md5: str) -> bool:
        """Return True if the file's MD5 matches *expected_md5*."""
        return FileIntegrity.compute_md5(filepath).lower() == expected_md5.lower()

    @staticmethod
    def verify_size(filepath: str, expected_size: int) -> bool:
        """Return True if the file size matches *expected_size* bytes."""
        try:
            return os.path.getsize(filepath) == expected_size
        except OSError:
            return False

    @staticmethod
    def verify(filepath: str, expected_size: int = 0, expected_md5: str = "") -> bool:
        """Verify both size and hash (when provided).  Returns True if all
        supplied checks pass."""
        if not os.path.isfile(filepath):
            return False
        if expected_size and not FileIntegrity.verify_size(filepath, expected_size):
            return False
        if expected_md5 and not FileIntegrity.verify_hash(filepath, expected_md5):
            return False
        return True
