import os
import time
import shutil
import requests

from constants import remove_emojis_and_binary, DEFAULT_RETRY, FileIntegrity, logger
from utils.download_result import DownloadResult

# Chunk size for streaming downloads (256 KB for better throughput)
CHUNK_SIZE = 1024 * 256

# Connection timeout (connect, read) in seconds
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 120


def _create_session() -> requests.Session:
    """Create a requests.Session with connection pooling."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=5,
        pool_maxsize=5,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_mp4(url, download_folder_path, title, task_id, progress):
    """Download an MP4 file with retry logic, resume support, and integrity checks."""
    safe_title = remove_emojis_and_binary(title)
    progress.update(task_id, description=f"Downloading video {safe_title}", completed=0)
    output_file = os.path.join(os.path.dirname(download_folder_path), f"{title}.mp4")

    retry_cfg = DEFAULT_RETRY
    session = _create_session()
    start_time = time.time()
    last_attempt_error = None

    for attempt in range(retry_cfg.max_retries + 1):
        try:
            # ---- Resume support: check for partial file ----
            downloaded = 0
            headers = {}
            if os.path.isfile(output_file):
                downloaded = os.path.getsize(output_file)
                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"
                    logger.debug(f"Resuming download at byte {downloaded} for {safe_title}")

            with session.get(
                url,
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                headers=headers,
            ) as response:
                # If server doesn't support Range or file is already complete
                if response.status_code == 416:
                    # Range not satisfiable – file already fully downloaded
                    logger.debug(f"File already fully downloaded: {safe_title}")
                    break

                if response.status_code in retry_cfg.retry_on_status_codes:
                    raise requests.RequestException(
                        f"Server returned retryable status {response.status_code}"
                    )

                response.raise_for_status()

                # Determine total size
                content_length = int(response.headers.get("content-length") or 0)
                if response.status_code == 206:
                    # Partial content – append to existing file
                    total_size = downloaded + content_length
                    file_mode = "ab"
                else:
                    # Full response – overwrite
                    total_size = content_length
                    downloaded = 0
                    file_mode = "wb"

                with open(output_file, file_mode) as file:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            file.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                pct = min(downloaded * 100 / total_size, 99)
                                progress.update(task_id, completed=pct)

            # ---- Integrity check ----
            if not os.path.isfile(output_file) or os.path.getsize(output_file) == 0:
                raise IOError("The MP4 response completed without creating a non-empty file.")

            # If we expected a specific size, verify it
            if total_size and not FileIntegrity.verify_size(output_file, total_size):
                raise IOError(
                    f"Size mismatch: expected {total_size}, "
                    f"got {os.path.getsize(output_file)}"
                )

            # Success
            break

        except (requests.RequestException, IOError, OSError) as error:
            last_attempt_error = error
            if attempt < retry_cfg.max_retries:
                delay = retry_cfg.delay_for_attempt(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{retry_cfg.max_retries} for {safe_title} "
                    f"after {delay:.1f}s – {error}"
                )
                time.sleep(delay)
            else:
                elapsed = time.time() - start_time
                session.close()
                return DownloadResult.failed(
                    f"MP4 download failed after {retry_cfg.max_retries + 1} attempts: {error}",
                    elapsed_seconds=elapsed,
                    retries=attempt,
                )

    elapsed = time.time() - start_time
    session.close()

    progress.update(task_id, completed=100)
    progress.console.log(f"[green]Downloaded {safe_title}[/green]")
    shutil.rmtree(download_folder_path, ignore_errors=True)

    return DownloadResult.with_file_info(
        output_file,
        elapsed_seconds=elapsed,
        retries=max(0, attempt if 'attempt' in dir() else 0),
    )
