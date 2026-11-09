"""Udemy Downloader By Joe — robust, production-ready download orchestrator."""

import json
import os
import sys
import signal
import requests
import argparse
import subprocess
import threading
import time as _time
from dataclasses import dataclass, field
from typing import Optional, Set, List
from pathvalidate import sanitize_filename
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.live import Live
from rich.tree import Tree
from rich.text import Text
from rich.table import Table
from rich import print as rprint

import re
import http.cookiejar as cookielib
from concurrent.futures import ThreadPoolExecutor, as_completed

from constants import (
    logger, LoadAction, COURSE_URL, CURRICULUM_URL, LECTURE_URL, HOME_DIR,
    format_time, remove_emojis_and_binary, Loader, is_valid_chapter,
    is_valid_lecture, ElapsedTimeColumn, time,
)
from utils.process_m3u8 import download_and_merge_m3u8
from utils.process_mpd import download_and_merge_mpd
from utils.process_captions import download_captions
from utils.process_assets import download_supplementary_assets
from utils.process_articles import download_article
from utils.process_mp4 import download_mp4
from download_cache import DownloadCache
from utils.download_result import DownloadResult
from dotenv import load_dotenv

console = Console()

# Load environment variables from .env
load_dotenv()

# Set UTF-8 encoding for console output to handle Unicode characters
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)


# ---------------------------------------------------------------------------
# Custom exception hierarchy — replaces sys.exit() inside the Udemy class
# ---------------------------------------------------------------------------
class UdemyError(Exception):
    """Base exception for all Udemy-related errors."""


class AuthenticationError(UdemyError):
    """Cookie / auth issues."""


class CourseNotFoundError(UdemyError):
    """The course ID or URL does not resolve to a valid course."""


class CurriculumError(UdemyError):
    """Cannot fetch / parse the course curriculum."""


class LectureError(UdemyError):
    """Cannot fetch lecture metadata."""


class DirectoryError(UdemyError):
    """Cannot create an output directory."""


class PrerequisiteError(UdemyError):
    """A required external tool is missing."""


# ---------------------------------------------------------------------------
# DownloadConfig dataclass — replaces all global mutable state
# ---------------------------------------------------------------------------
@dataclass
class DownloadConfig:
    """All runtime configuration passed through the call chain."""

    course_url: Optional[str] = None
    course_id: Optional[int] = None
    key: Optional[str] = None
    cookies_path: str = "cookies.txt"
    cookies_json_path: str = "cookies.json"
    output_dir: str = "courses"
    course_dir: str = ""

    # Concurrency
    max_concurrent_lectures: int = 4

    # Caption / subtitle settings
    captions: List[str] = field(default_factory=lambda: ["en_US"])
    subtitle_lang: str = "en"
    convert_to_srt: bool = False

    # Skip flags
    skip_captions: bool = False
    skip_assets: bool = False
    skip_lectures: bool = False
    skip_articles: bool = False
    skip_assignments: bool = False

    # Range / filter
    start_chapter: int = 0
    start_lecture: int = 0
    end_chapter: int = 0
    end_lecture: int = 1000
    chapter_filter: Optional[Set[int]] = None

    # Quality selection
    quality: Optional[str] = None  # e.g. "1080", "720", "480"

    # Feature flags
    dry_run: bool = False
    verbose: bool = False
    retry_failed: bool = False

    # External tool paths
    n_m3u8dl_re_path: str = "n_m3u8dl-re.exe"
    shaka_packager_path: str = "shaka-packager.exe"

    # Cookie jar (loaded at runtime)
    cookie_jar: Optional[cookielib.MozillaCookieJar] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Rate limiter — simple token-bucket style
# ---------------------------------------------------------------------------
class RateLimiter:
    """Simple thread-safe rate limiter that enforces a minimum interval between API calls."""

    def __init__(self, min_interval: float = 0.25):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            now = _time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                _time.sleep(self._min_interval - elapsed)
            self._last_call = _time.monotonic()


# ---------------------------------------------------------------------------
# Download speed tracker
# ---------------------------------------------------------------------------
class SpeedTracker:
    """Thread-safe throughput tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self._total_bytes: int = 0
        self._start_time: float = _time.monotonic()

    def add_bytes(self, n: int):
        with self._lock:
            self._total_bytes += n

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    @property
    def elapsed(self) -> float:
        return max(_time.monotonic() - self._start_time, 0.001)

    @property
    def speed_mbps(self) -> float:
        return (self.total_bytes / 1_048_576) / self.elapsed

    def human_total(self) -> str:
        b = self.total_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"


# ---------------------------------------------------------------------------
# Graceful shutdown coordinator
# ---------------------------------------------------------------------------
class ShutdownCoordinator:
    """Watches for Ctrl+C and lets in-flight downloads finish."""

    def __init__(self):
        self._event = threading.Event()

    def request_shutdown(self):
        self._event.set()

    @property
    def is_shutting_down(self) -> bool:
        return self._event.is_set()

    def install(self):
        def _handler(signum, frame):
            if self.is_shutting_down:
                logger.warning("Forced exit.")
                os._exit(1)
            logger.warning("Shutdown requested — finishing current downloads. Press Ctrl+C again to force.")
            self.request_shutdown()

        signal.signal(signal.SIGINT, _handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handler)


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------
def ensure_cookie_file(cfg: DownloadConfig):
    """Create a Netscape cookie file only when the selected cookie path is absent."""
    if os.path.exists(cfg.cookies_path) and os.path.getsize(cfg.cookies_path) > 0:
        return
    if not os.path.exists(cfg.cookies_json_path):
        raise AuthenticationError("No cookie file was provided and cookies.json is missing.")
    try:
        with open(cfg.cookies_json_path, 'r', encoding='utf-8') as source:
            cookies_json = json.load(source)
        with open(cfg.cookies_path, 'w', encoding='utf-8') as target:
            target.write("# Netscape HTTP Cookie File\n")
            for cookie in cookies_json:
                domain = cookie.get('domain', '')
                flag = 'TRUE' if cookie.get('hostOnly', False) is False else 'FALSE'
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                expiration = str(cookie.get('expirationDate', 0))
                target.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{cookie.get('name', '')}\t{cookie.get('value', '')}\n")
    except (OSError, json.JSONDecodeError) as error:
        raise AuthenticationError(f"Failed to prepare the cookie file: {error}") from error


def _try_browser_cookies(cfg: DownloadConfig) -> bool:
    """Try to extract Udemy cookies from Chrome/Firefox via browser_cookie3.

    Returns True if cookies were successfully written to cfg.cookies_path.
    """
    try:
        import browser_cookie3  # noqa: F401
    except ImportError:
        return False

    for loader_name, loader_fn in [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
    ]:
        try:
            jar = loader_fn(domain_name=".udemy.com")
            if not jar:
                continue
            # Convert to Netscape format
            with open(cfg.cookies_path, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                for c in jar:
                    flag = 'TRUE' if c.domain.startswith('.') else 'FALSE'
                    secure = 'TRUE' if c.secure else 'FALSE'
                    exp = str(c.expires or 0)
                    f.write(f"{c.domain}\t{flag}\t{c.path}\t{secure}\t{exp}\t{c.name}\t{c.value}\n")
            logger.info(f"Extracted Udemy cookies from {loader_name}.")
            return True
        except Exception:
            continue
    return False


def parse_chapter_filter(chapter_str):
    """
    Given a string like "1,3-5,7,9-11", return a set of chapter numbers.
    """
    chapters = set()
    for part in chapter_str.split(','):
        if '-' in part:
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                chapters.update(range(start, end + 1))
            except ValueError:
                logger.error("Invalid range in --chapter argument: %s", part)
        else:
            try:
                chapters.add(int(part.strip()))
            except ValueError:
                logger.error("Invalid chapter number in --chapter argument: %s", part)
    return chapters


# ---------------------------------------------------------------------------
# Quality selection helper
# ---------------------------------------------------------------------------
# Maps user-friendly labels to pixel heights
QUALITY_MAP = {
    "2160": 2160, "4k": 2160,
    "1080": 1080, "1080p": 1080,
    "720": 720, "720p": 720,
    "480": 480, "480p": 480,
    "360": 360, "360p": 360,
    "240": 240, "240p": 240,
    "144": 144, "144p": 144,
}


def select_media_source(sources, quality_preference: Optional[str] = None):
    """Pick the best media source from the list, respecting quality preference.

    Returns (mpd_url, m3u8_url, mp4_url) — at most one will be set.
    """
    mpd_url = next((s.get('src') for s in sources if s.get('type') == "application/dash+xml"), None)
    mp4_sources = [s for s in sources if s.get('type') == "video/mp4"]
    m3u8_url = next((s.get('src') for s in sources if s.get('type') == "application/x-mpegURL"), None)

    # For MP4, pick quality-matched source
    mp4_url = None
    if mp4_sources:
        if quality_preference and quality_preference.lower() in QUALITY_MAP:
            target_height = QUALITY_MAP[quality_preference.lower()]
            # Try exact match first, then closest below
            for src in sorted(mp4_sources, key=lambda s: abs(int(s.get('label', '0').replace('p', '') or 0) - target_height)):
                mp4_url = src.get('src')
                break
        else:
            # Default: highest quality
            mp4_sources.sort(key=lambda s: int(s.get('label', '0').replace('p', '') or 0), reverse=True)
            mp4_url = mp4_sources[0].get('src') if mp4_sources else None

    return mpd_url, m3u8_url, mp4_url


# ---------------------------------------------------------------------------
# Udemy class — no globals, no sys.exit(), raises exceptions
# ---------------------------------------------------------------------------
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_FACTOR = 2


class Udemy:

    def __init__(self, cfg: DownloadConfig):
        self.cfg = cfg
        self._rate_limiter = RateLimiter(min_interval=0.25)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # Load cookie jar
        try:
            jar = cookielib.MozillaCookieJar(cfg.cookies_path)
            jar.load()
            cfg.cookie_jar = jar
            self._session.cookies = jar
        except Exception:
            raise AuthenticationError(
                "The provided cookie file could not be read or is incorrectly formatted. "
                "Please ensure the file is in the correct format and contains valid authentication cookies."
            )

    # -- HTTP with retry + backoff + rate limiting --
    def request(self, url):
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._rate_limiter.wait()
            try:
                response = self._session.get(url, stream=True, timeout=(15, 120))
                if response.status_code in RETRY_STATUS_CODES:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and response.status_code == 429:
                        try:
                            wait = int(retry_after)
                        except ValueError:
                            wait = BACKOFF_FACTOR ** attempt
                        logger.warning("Rate limited (429). Waiting %ds before retry %d/%d", wait, attempt, MAX_RETRIES)
                        _time.sleep(wait)
                    else:
                        wait = BACKOFF_FACTOR ** attempt
                        logger.warning("Server error %d. Retrying in %ds (%d/%d)", response.status_code, wait, attempt, MAX_RETRIES)
                        _time.sleep(wait)
                    last_error = RuntimeError(f"HTTP {response.status_code} for {url}")
                    continue
                response.raise_for_status()
                return response
            except requests.ConnectionError as e:
                wait = BACKOFF_FACTOR ** attempt
                logger.warning("Connection error: %s. Retrying in %ds (%d/%d)", e, wait, attempt, MAX_RETRIES)
                _time.sleep(wait)
                last_error = e
            except requests.Timeout as e:
                wait = BACKOFF_FACTOR ** attempt
                logger.warning("Timeout: %s. Retrying in %ds (%d/%d)", e, wait, attempt, MAX_RETRIES)
                _time.sleep(wait)
                last_error = e
            except requests.RequestException as e:
                raise RuntimeError(f"Udemy request failed for {url}: {e}") from e
        raise RuntimeError(f"Udemy request failed after {MAX_RETRIES} retries for {url}: {last_error}")

    def extract_course_id(self, course_url):
        with Loader("Fetching course ID"):
            response = self.request(course_url)
            content_str = response.content.decode('utf-8')

        meta_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', content_str)

        if meta_match:
            url = meta_match.group(1)
            number_match = re.search(r'/(\d+)_', url)
            if number_match:
                number = number_match.group(1)
                logger.info(f"Course ID Extracted: {number}")
                return number
            else:
                raise CourseNotFoundError(
                    "Unable to retrieve a valid course ID from the provided course URL. Please check the course URL or try with --id."
                )
        else:
            raise CourseNotFoundError(
                "Unable to retrieve a valid course ID from the provided course URL. Please check the course URL or try with --id"
            )

    def fetch_course(self, course_id):
        try:
            response = self.request(COURSE_URL.format(course_id=course_id)).json()
            if response.get('detail') == 'Not found.':
                raise CourseNotFoundError(
                    "The course could not be found with the provided ID or URL. "
                    "Please verify the course ID/URL and ensure that it is publicly accessible or you have the necessary permissions."
                )
            return response
        except CourseNotFoundError:
            raise
        except Exception as e:
            raise CourseNotFoundError(f"Unable to retrieve the course details: {e}") from e

    def fetch_course_curriculum(self, course_id):
        all_results = []
        url = CURRICULUM_URL.format(course_id=course_id)
        total_count = 0

        logger.info("Fetching course curriculum. This may take a while")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3}%"),
            transient=True
        ) as progress:
            task = progress.add_task(description="Fetching Course Curriculum", total=total_count)

            while url:
                response = self.request(url).json()

                if response.get('detail') == 'You do not have permission to perform this action.':
                    raise CurriculumError(
                        "The course was found, but the curriculum (lectures and materials) could not be retrieved. "
                        "This could be due to API issues, restrictions on the course, or a malformed course structure."
                    )

                if response.get('detail') == 'Not found.':
                    raise CurriculumError(
                        "The course was found, but the curriculum (lectures and materials) could not be retrieved. "
                        "This could be due to API issues, restrictions on the course, or a malformed course structure."
                    )

                if total_count == 0:
                    total_count = response.get('count', 0)
                    progress.update(task, total=total_count)

                results = response.get('results', [])
                all_results.extend(results)
                progress.update(task, completed=len(all_results))

                url = response.get('next')

            progress.update(task_id=task, description="Fetched Course Curriculum", total=total_count)
        return self.organize_curriculum(all_results)

    def organize_curriculum(self, results):
        curriculum = []
        current_chapter = None
        total_lectures = 0

        for item in results:
            if item['_class'] == 'chapter':
                current_chapter = {'id': item['id'], 'title': item['title'], 'is_published': item['is_published'], 'children': []}
                curriculum.append(current_chapter)
            elif item['_class'] == 'lecture':
                if current_chapter is not None:
                    current_chapter['children'].append(item)
                    if item['_class'] == 'lecture':
                        total_lectures += 1
                else:
                    logger.warning("Found lecture without a parent chapter.")

        num_chapters = len(curriculum)
        logger.info(f"Discovered Chapter(s): {num_chapters}")
        logger.info(f"Discovered Lectures(s): {total_lectures}")

        return curriculum

    def build_curriculum_tree(self, data, tree, index=1):
        for i, item in enumerate(data, start=index):
            if 'title' in item:
                title = f"{i:02d}. {item['title']}"
                if '_class' in item and item['_class'] == 'lecture':
                    time_estimation = item.get('asset', {}).get('time_estimation')
                    if time_estimation:
                        time_str = format_time(time_estimation)
                        title += f" ({time_str})"
                    node_text = Text(title, style="cyan")
                else:
                    node_text = Text(title, style="magenta")

                node = tree.add(node_text)

                if 'children' in item:
                    self.build_curriculum_tree(item['children'], node, index=1)

    def fetch_lecture_info(self, course_id, lecture_id):
        try:
            return self.request(LECTURE_URL.format(course_id=course_id, lecture_id=lecture_id)).json()
        except Exception as e:
            raise LectureError(f"Failed to fetch lecture info for lecture {lecture_id}: {e}") from e

    def create_directory(self, path):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            raise DirectoryError(f'Failed to create directory "{path}": {e}') from e

    def download_lecture(
        self, course_id, lecture, lect_info, temp_folder_path, lindex, folder_path,
        task_id, progress, download_cache, chapter_index, speed_tracker, shutdown
    ):
        cfg = self.cfg
        lecture_title = sanitize_filename(lecture['title'])
        expected_file_path = os.path.join(folder_path, f"{lindex}. {lecture_title}.mp4")

        # Check if download is already completed
        is_completed, cached_record = download_cache.is_download_completed(chapter_index, lindex, lecture_title, expected_file_path)

        if is_completed:
            progress.console.log(f"[yellow]⏭️  Skipping {lecture_title} (already downloaded)[/yellow]")
            progress.remove_task(task_id)
            return

        # Check for graceful shutdown
        if shutdown.is_shutting_down:
            progress.console.log(f"[yellow]⏭️  Skipping {lecture_title} (shutdown requested)[/yellow]")
            try:
                progress.remove_task(task_id)
            except KeyError:
                pass
            return

        # Mark download as started
        download_key = download_cache.mark_download_started(chapter_index, lindex, lecture_title, lecture['id'], lect_info['asset']['asset_type'])

        try:
            asset = lect_info.get("asset") or {}
            if not cfg.skip_captions and asset.get("captions"):
                caption_result = download_captions(asset["captions"], folder_path, f"{lindex}. {lecture_title}", cfg.captions, cfg.convert_to_srt)
                if not caption_result.success:
                    raise RuntimeError(caption_result.error)

            if not cfg.skip_assets and lecture.get("supplementary_assets"):
                assets_dir = os.path.join(folder_path, f"{lindex}. {lecture_title}.assets")
                assets_result = download_supplementary_assets(self, lecture["supplementary_assets"], assets_dir, course_id, lect_info["id"])
                if not assets_result.success:
                    raise RuntimeError(assets_result.error)

            if asset.get('asset_type') == "Video":
                if cfg.skip_lectures:
                    progress.console.log(f"[yellow]Skipped video {lecture_title}; it was not added to the cache.[/yellow]")
                    return
                sources = asset.get("media_sources") or []

                # Use quality-aware source selection
                mpd_url, m3u8_url, mp4_url = select_media_source(sources, cfg.quality)

                if mpd_url is None:
                    if m3u8_url is None:
                        if mp4_url is None:
                            result = DownloadResult.failed("No supported media source was supplied by the course API.")
                        else:
                            result = download_mp4(mp4_url, temp_folder_path, f"{lindex}. {lecture_title}", task_id, progress)
                    else:
                        result = download_and_merge_m3u8(m3u8_url, temp_folder_path, f"{lindex}. {lecture_title}", task_id, progress, cfg.key)
                else:
                    result = download_and_merge_mpd(
                        mpd_url, temp_folder_path, f"{lindex}. {lecture_title}", lecture['asset']['time_estimation'], cfg.key, task_id, progress
                    )
                if not result.success:
                    download_cache.mark_download_failed(download_key, result.error)
                    logger.error("%s failed: %s. Check the DEBUG lines above and verify the source URL, login cookies, and installed tools.", lecture_title, result.error)
                    return
            elif asset.get('asset_type') == "Article":
                if cfg.skip_articles:
                    progress.console.log(f"[yellow]Skipped article {lecture_title}; it was not added to the cache.[/yellow]")
                    return
                article_result = download_article(self, asset, temp_folder_path, f"{lindex}. {lecture_title}", task_id, progress)
                if not article_result.success:
                    download_cache.mark_download_failed(download_key, article_result.error)
                    return
                expected_file_path = os.path.join(folder_path, f"{lindex}. {lecture_title}.html")
            else:
                download_cache.mark_download_failed(download_key, f"Unsupported asset type: {asset.get('asset_type', 'missing')}")
                return

            # Mark download as completed if file exists, and track size
            if os.path.isfile(expected_file_path):
                fsize = os.path.getsize(expected_file_path)
                download_cache.mark_download_completed(download_key, expected_file_path)
                speed_tracker.add_bytes(fsize)
            else:
                download_cache.mark_download_failed(download_key, f"Expected output missing: {expected_file_path}")

        except Exception as e:
            logger.error(f"Failed to download {lecture_title}: {e}")
            download_cache.mark_download_failed(download_key, str(e))

        try:
            progress.remove_task(task_id)
        except KeyError:
            pass

    def _generate_tasks(self, curriculum):
        """Producer: yields (mindex_str, chapter, lindex_str, lecture, chapter_index) tuples."""
        cfg = self.cfg
        for mindex, chapter in enumerate(curriculum, start=1):
            if not is_valid_chapter(mindex, cfg.start_chapter, cfg.end_chapter, cfg.chapter_filter):
                continue
            for lindex, lecture in enumerate(chapter['children'], start=1):
                if not is_valid_lecture(mindex, lindex, cfg.start_chapter, cfg.start_lecture, cfg.end_chapter, cfg.end_lecture):
                    continue
                mindex_str = f"{mindex:02}" if mindex < 10 else f"{mindex}"
                lindex_str = f"{lindex:02}" if lindex < 10 else f"{lindex}"
                yield mindex_str, chapter, lindex_str, lecture, mindex

    def _submit_one(self, task_gen, executor, progress, course_id, download_cache, speed_tracker, shutdown):
        """Pull the next lecture from the generator and submit it. Returns (task_id, future) or None."""
        try:
            mindex, chapter, lindex, lecture, chapter_index = next(task_gen)
        except StopIteration:
            return None

        folder_path = os.path.join(self.cfg.course_dir, f"{mindex}. {remove_emojis_and_binary(sanitize_filename(chapter['title']))}")
        temp_folder_path = os.path.join(folder_path, str(lecture['id']))
        self.create_directory(temp_folder_path)
        lect_info = self.fetch_lecture_info(course_id, lecture['id'])

        task_id = progress.add_task(
            f"Downloading Lecture: {lecture['title']} ({lindex}/{len(chapter['children'])})", total=100
        )

        future = executor.submit(
            self.download_lecture, course_id, lecture, lect_info, temp_folder_path,
            lindex, folder_path, task_id, progress, download_cache, chapter_index,
            speed_tracker, shutdown,
        )
        return task_id, future

    def download_course(self, course_id, curriculum, shutdown: ShutdownCoordinator):
        """Clean producer-consumer pattern for concurrent lecture downloads."""
        cfg = self.cfg

        # Initialize download cache
        download_cache = DownloadCache(course_id)
        download_cache.save_curriculum(curriculum)

        # Show progress summary if cache exists
        if len(download_cache.cache_data["downloads"]) > 0:
            download_cache.print_progress_summary()

        speed_tracker = SpeedTracker()

        # Dry-run mode: just list what would be downloaded
        if cfg.dry_run:
            console.print("\n[bold cyan]DRY RUN — the following items would be downloaded:[/bold cyan]\n")
            table = Table(title="Planned Downloads")
            table.add_column("#", style="dim")
            table.add_column("Chapter", style="magenta")
            table.add_column("Lecture", style="cyan")
            count = 0
            for mindex, chapter, lindex, lecture, _ in self._generate_tasks(curriculum):
                count += 1
                table.add_row(str(count), chapter['title'], lecture['title'])
            console.print(table)
            console.print(f"\n[bold]Total items: {count}[/bold]")
            return {"total": count, "completed": 0, "failed": 0, "in_progress": 0, "completion_rate": 0}

        progress = Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), ElapsedTimeColumn(),
        )

        futures = []  # list of (task_id, future)
        task_gen = self._generate_tasks(curriculum)

        with ThreadPoolExecutor(max_workers=cfg.max_concurrent_lectures) as executor, Live(progress, refresh_per_second=10):
            # Seed the pool with initial tasks
            for _ in range(cfg.max_concurrent_lectures):
                if shutdown.is_shutting_down:
                    break
                submitted = self._submit_one(task_gen, executor, progress, course_id, download_cache, speed_tracker, shutdown)
                if submitted is None:
                    break
                futures.append(submitted)

            # As each task completes, replace it with the next one
            while futures:
                done_futures = {f for _, f in futures}
                for future in as_completed(done_futures):
                    task_id = next(tid for tid, f in futures if f is future)
                    try:
                        future.result()
                    except Exception as e:
                        logger.error("Unhandled error in download task: %s", e)
                    try:
                        progress.remove_task(task_id)
                    except Exception:
                        pass
                    futures = [(tid, f) for tid, f in futures if f is not future]

                    if shutdown.is_shutting_down:
                        logger.info("Shutdown: waiting for %d in-flight download(s)…", len(futures))
                        break

                    submitted = self._submit_one(task_gen, executor, progress, course_id, download_cache, speed_tracker, shutdown)
                    if submitted is not None:
                        futures.append(submitted)

            # On shutdown, let remaining futures drain
            if shutdown.is_shutting_down and futures:
                for _, f in futures:
                    try:
                        f.result(timeout=300)
                    except Exception:
                        pass

        # Save cache one final time
        download_cache.save_cache()

        summary = download_cache.get_download_summary()
        summary["speed_tracker"] = speed_tracker
        return summary


# ---------------------------------------------------------------------------
# Prerequisites check
# ---------------------------------------------------------------------------
def check_prerequisites(cfg: DownloadConfig):
    if not cfg.cookies_path:
        if not os.path.isfile(os.path.join(HOME_DIR, "cookies.txt")):
            if not cfg.dry_run:
                raise PrerequisiteError("Please provide a valid cookie file using the '--cookies' option.")
            logger.warning("No cookie file found; running in dry-run/preview mode.")
    else:
        if not os.path.isfile(cfg.cookies_path):
            if not cfg.dry_run:
                raise PrerequisiteError("The provided cookie file path does not exist.")
            logger.warning(f"Cookie file '{cfg.cookies_path}' does not exist; continuing in dry-run mode.")

    # Check ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        msg = "ffmpeg is not installed or not found in system PATH (needed for video merging)."
        if cfg.dry_run or cfg.skip_lectures:
            logger.warning(msg)
        else:
            raise PrerequisiteError(f"{msg} Please install it (e.g. 'winget install Gyan.FFmpeg' or scoop/choco).")

    # Check N_m3u8DL-RE
    try:
        subprocess.run([cfg.n_m3u8dl_re_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        msg = f"{cfg.n_m3u8dl_re_path} is not installed or not found in system PATH (needed for HLS/DASH streams)."
        if cfg.dry_run or cfg.skip_lectures:
            logger.warning(msg)
        else:
            raise PrerequisiteError(f"{msg} Please download it from GitHub (n-m3u8dl-re) or place it in the project root.")

    # Check for Shaka Packager (preferred for DRM content)
    try:
        subprocess.run([cfg.shaka_packager_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        logger.warning(f"{cfg.shaka_packager_path} not found. DRM-protected videos may not work properly.")

    return True


# ---------------------------------------------------------------------------
# Post-download summary (Rich table)
# ---------------------------------------------------------------------------
def print_download_summary(summary: dict, elapsed: float):
    """Rich table showing completed / failed / skipped counts, total size, total time."""
    table = Table(title="📊 Download Summary", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    completed = summary.get("completed", 0)
    failed = summary.get("failed", 0)
    total = summary.get("total", 0)
    in_progress = summary.get("in_progress", 0)
    skipped = total - completed - failed - in_progress

    speed_tracker: Optional[SpeedTracker] = summary.get("speed_tracker")

    table.add_row("✅ Completed", f"[green]{completed}[/green]")
    table.add_row("❌ Failed", f"[red]{failed}[/red]" if failed else f"{failed}")
    table.add_row("⏭️  Skipped", str(skipped))
    table.add_row("📦 Total tracked", str(total))
    table.add_row("⏱️  Total time", format_time(elapsed))

    if speed_tracker:
        table.add_row("💾 Total downloaded", speed_tracker.human_total())
        table.add_row("🚀 Avg speed", f"{speed_tracker.speed_mbps:.2f} MB/s")

    rate = (completed / total * 100) if total else 0
    table.add_row("📈 Completion rate", f"{rate:.1f}%")

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Udemy Downloader By Joe - A powerful tool for downloading Udemy courses")
    parser.add_argument("--id", "-i", type=int, required=False, help="The ID of the Udemy course to download")
    parser.add_argument("--url", "-u", type=str, required=False, help="The URL of the Udemy course to download")
    parser.add_argument("--key", "-k", type=str, help="Key to decrypt the DRM-protected videos")
    parser.add_argument("--cookies", "-c", type=str, default="cookies.txt", help="Path to cookies.txt file")
    parser.add_argument("--load", "-l", help="Load course curriculum from file", action=LoadAction, const=True, nargs='?')
    parser.add_argument("--save", "-s", help="Save course curriculum to a file", action=LoadAction, const=True, nargs='?')
    parser.add_argument("--concurrent", "-cn", type=int, default=4, help="Maximum number of concurrent downloads")

    parser.add_argument("--quality", "-q", type=str, help="Preferred video quality (e.g. 1080p, 720p, 480p). Defaults to highest.")
    parser.add_argument("--output", "-o", type=str, help="Override the output directory (default: courses/)")
    parser.add_argument("--start-chapter", type=int, help="Start the download from the specified chapter")
    parser.add_argument("--start-lecture", type=int, help="Start the download from the specified lecture")
    parser.add_argument("--end-chapter", type=int, help="End the download at the specified chapter")
    parser.add_argument("--end-lecture", type=int, help="End the download at the specified lecture")
    parser.add_argument("--captions", type=str, help="Specify what captions to download. Separate multiple captions with commas")
    parser.add_argument("--srt", help="Convert the captions to srt format", action=LoadAction, const=True, nargs='?')

    parser.add_argument("--tree", help="Create a tree view of the course curriculum", action=LoadAction, nargs='?')

    parser.add_argument("--skip-captions", action="store_true", help="Skip downloading captions")
    parser.add_argument("--skip-assets", action="store_true", help="Skip downloading assets")
    parser.add_argument("--skip-lectures", action="store_true", help="Skip downloading lectures")
    parser.add_argument("--skip-articles", action="store_true", help="Skip downloading articles")
    parser.add_argument("--skip-assignments", action="store_true", help="Skip downloading assignments")

    parser.add_argument("--chapter", type=str, help="Download specific chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').")

    # Cache management options
    parser.add_argument("--clear-cache", action="store_true", help="Clear download cache and restart from beginning")
    parser.add_argument("--show-cache", action="store_true", help="Show download cache status and exit")

    # New flags
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without actually downloading")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--retry-failed", action="store_true", help="Automatically retry only failed downloads from cache")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        print(parser.format_help())
        sys.exit(0)

    # -- Verbose / debug logging --
    if args.verbose:
        logger.setLevel("DEBUG")
        for handler in logger.handlers:
            handler.setLevel("DEBUG")
        logger.debug("Debug logging enabled.")

    # -- Build DownloadConfig from args + env --
    env_course_link = os.getenv('COURSE_LINK', None)
    cfg = DownloadConfig(
        course_url=args.url or env_course_link,
        course_id=args.id,
        key=args.key or os.getenv('WIDEVINE_KEY', '') or None,
        cookies_path=args.cookies,
        cookies_json_path=os.getenv('COOKIES_JSON_PATH', 'cookies.json'),
        output_dir=args.output or os.getenv('OUTPUT_DIR', 'courses'),
        max_concurrent_lectures=min(max(args.concurrent, 1), 25),
        subtitle_lang=os.getenv('SUBTITLE_LANG', 'en'),
        n_m3u8dl_re_path=os.getenv('N_M3U8DL_RE_PATH', 'n_m3u8dl-re.exe'),
        shaka_packager_path=os.getenv('SHAKA_PACKAGER_PATH', 'shaka-packager.exe'),
        quality=args.quality,
        dry_run=args.dry_run,
        verbose=args.verbose,
        retry_failed=args.retry_failed,
        skip_captions=args.skip_captions,
        skip_assets=args.skip_assets,
        skip_lectures=args.skip_lectures,
        skip_articles=args.skip_articles,
        skip_assignments=args.skip_assignments,
    )

    # Validate concurrent range (log warnings like original)
    if args.concurrent > 25:
        logger.warning("The maximum number of concurrent downloads is 25. The provided number of concurrent downloads will be capped to 25.")
    elif args.concurrent < 1:
        logger.warning("The minimum number of concurrent downloads is 1. The provided number of concurrent downloads will be capped to 1.")

    if not cfg.course_url and not cfg.course_id:
        logger.error("You must provide either the course ID with '--id' or the course URL with '--url' (or set COURSE_LINK in .env) to proceed.")
        return
    elif cfg.course_url and cfg.course_id:
        logger.warning("Both course ID and URL provided. Prioritizing course ID over URL.")

    if cfg.key and ":" not in cfg.key:
        logger.error("The provided Widevine key is either malformed or incorrect. Please check the key and try again.")
        return

    # If key is empty string, set it to None
    if not cfg.key:
        cfg.key = None

    # Quick cache operations that don't require full auth
    if cfg.course_id and args.show_cache:
        DownloadCache(cfg.course_id).print_progress_summary()
        return
    if cfg.course_id and args.clear_cache:
        DownloadCache(cfg.course_id).clear_cache()
        logger.info("Download cache cleared.")
        return

    # Cookie handling: try file → JSON → browser extraction
    try:
        ensure_cookie_file(cfg)
    except AuthenticationError:
        # Fall back to browser cookie extraction
        if not _try_browser_cookies(cfg):
            logger.error("Authentication setup failed: no cookie file found and browser cookie extraction failed. "
                         "Please provide cookies via --cookies or install browser_cookie3.")
            return

    try:
        check_prerequisites(cfg)
    except PrerequisiteError as e:
        logger.error(str(e))
        return

    # Install graceful shutdown handler
    shutdown = ShutdownCoordinator()
    shutdown.install()

    try:
        udemy = Udemy(cfg)
    except AuthenticationError as e:
        logger.critical(str(e))
        return

    try:
        course_id = cfg.course_id if cfg.course_id else udemy.extract_course_id(cfg.course_url)
    except CourseNotFoundError as e:
        logger.critical(str(e))
        return

    # Handle cache management options (when course_id comes from URL)
    if args.clear_cache:
        if course_id:
            cache = DownloadCache(course_id)
            cache.clear_cache()
            logger.info("Download cache cleared. Run the command again to start a fresh download.")
            return
        else:
            logger.error("Cannot clear cache without course ID. Please provide --id or --url.")
            return

    if args.show_cache:
        if course_id:
            cache = DownloadCache(course_id)
            cache.print_progress_summary()
        else:
            logger.error("Cannot show cache without course ID. Please provide --id or --url.")
        return

    # -- Retry-failed mode --
    if cfg.retry_failed:
        cache = DownloadCache(course_id)
        count = cache.retry_failed()
        if count == 0:
            logger.info("No failed downloads to retry.")
            return
        logger.info(f"Reset {count} failed download(s) for retry. Continuing with normal download…")

    if args.captions:
        try:
            cfg.captions = args.captions.split(",")
        except Exception:
            logger.error("Invalid captions provided. Captions should be separated by commas.")
    else:
        cfg.captions = ["en_US"]

    cfg.convert_to_srt = bool(args.srt)

    try:
        course_info = udemy.fetch_course(course_id)
    except Exception as e:
        if args.load:
            logger.warning(f"Could not fetch online course metadata ({e}). Using offline placeholder title.")
            course_info = {'title': f"Course_{course_id}"}
        else:
            logger.critical(str(e))
            return

    cfg.course_dir = os.path.join(cfg.output_dir, remove_emojis_and_binary(sanitize_filename(course_info['title'])))

    try:
        logger.info(f"Course Title: {course_info['title']}")
    except UnicodeEncodeError:
        logger.info(f"Course Title: {remove_emojis_and_binary(course_info['title'])}")

    udemy.create_directory(os.path.join(cfg.course_dir))

    if args.load:
        if args.load is True and os.path.isfile(os.path.join(HOME_DIR, "course.json")):
            try:
                with open(os.path.join(HOME_DIR, "course.json"), "r") as fh:
                    course_curriculum = json.load(fh)
                logger.info("The course curriculum is successfully loaded from course.json")
            except json.JSONDecodeError:
                logger.error("The course curriculum file provided is either malformed or corrupted.")
                return
        elif args.load:
            if os.path.isfile(args.load):
                try:
                    with open(args.load, "r") as fh:
                        course_curriculum = json.load(fh)
                    logger.info(f"The course curriculum is successfully loaded from {args.load}")
                except json.JSONDecodeError:
                    logger.error("The course curriculum file provided is either malformed or corrupted.")
                    return
            else:
                logger.error("The course curriculum file could not be located. Please verify the file path and ensure that the file exists.")
                return
        else:
            logger.error("Please provide the path to the course curriculum file.")
            return
    else:
        try:
            course_curriculum = udemy.fetch_course_curriculum(course_id)
        except (CurriculumError, RuntimeError) as e:
            logger.critical(f"Unable to retrieve the course curriculum. {e}")
            return

    if args.save:
        if args.save is True:
            if os.path.isfile(os.path.join(HOME_DIR, "course.json")):
                logger.warning("Course curriculum file already exists. Overwriting the existing file.")
            with open(os.path.join(HOME_DIR, "course.json"), "w") as f:
                json.dump(course_curriculum, f, indent=4)
                logger.info("The course curriculum has been successfully saved to course.json")
        elif args.save:
            if os.path.isfile(args.save):
                logger.warning("Course curriculum file already exists. Overwriting the existing file.")
            with open(args.save, "w") as f:
                json.dump(course_curriculum, f, indent=4)
                logger.info(f"The course curriculum has been successfully saved to {args.save}")

    if args.tree:
        root_tree = Tree(course_info['title'], style="green")
        udemy.build_curriculum_tree(course_curriculum, root_tree)
        rprint(root_tree)
        if args.tree is True:
            pass
        elif args.tree:
            if os.path.isfile(args.tree):
                logger.warning("Course Curriculum Tree file already exists. Overwriting the existing file.")
            with open(args.tree, "w") as f:
                rprint(root_tree, file=f)
                logger.info(f"The course curriculum tree has been successfully saved to {args.tree}")

    if args.start_lecture:
        if args.start_chapter:
            cfg.start_chapter = args.start_chapter
            cfg.start_lecture = args.start_lecture
        else:
            logger.error("When using --start-lecture please provide --start-chapter")
            return
    elif args.start_chapter:
        cfg.start_chapter = args.start_chapter
        cfg.start_lecture = 0
    else:
        cfg.start_chapter = 0
        cfg.start_lecture = 0

    if args.end_lecture:
        if args.end_chapter:
            cfg.end_chapter = args.end_chapter
            cfg.end_lecture = args.end_lecture
        else:
            logger.error("When using --end-lecture please provide --end-chapter")
            return
    elif args.end_chapter:
        cfg.end_chapter = args.end_chapter
        cfg.end_lecture = 1000
    else:
        cfg.end_chapter = len(course_curriculum)
        cfg.end_lecture = 1000

    cfg.chapter_filter = None
    if args.chapter:
        cfg.chapter_filter = parse_chapter_filter(args.chapter)
        logger.info("Chapter filter applied: %s", sorted(cfg.chapter_filter))

    logger.info("The course download is starting. Please wait while the materials are being downloaded.")

    start_time = time.time()
    download_summary = udemy.download_course(course_id, course_curriculum, shutdown)
    end_time = time.time()

    elapsed_time = end_time - start_time

    # Print rich post-download summary
    print_download_summary(download_summary, elapsed_time)

    logger.info(f"Download finished in {format_time(elapsed_time)}")

    if download_summary.get("failed"):
        logger.error(f"Download completed with {download_summary['failed']} failed item(s). Use --retry-failed to retry them.")
    else:
        logger.info("All selected course materials have been successfully downloaded.")
    logger.info("Download Complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Process interrupted. Exiting")
        sys.exit(1)
