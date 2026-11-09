import os
import time
import requests

from constants import LINK_ASSET_URL, FILE_ASSET_URL, DEFAULT_RETRY, logger
from utils.download_result import DownloadResult

# Chunk size for streaming asset downloads (256 KB)
CHUNK_SIZE = 1024 * 256

# Timeout (connect, read) in seconds
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 120

# Max retries for individual asset downloads
ASSET_MAX_RETRIES = 3


def download_supplementary_assets(udemy, assets, output_dir, course_id, lecture_id):
    """Download all supplementary assets with retries, progress, and duplicate handling."""
    start_time = time.time()
    total_retries = 0

    try:
        os.makedirs(output_dir, exist_ok=True)
        for asset in assets:
            asset_type = asset.get("asset_type")
            if asset_type == "File":
                retries = _download_file(udemy, asset, course_id, lecture_id, output_dir)
                total_retries += retries
            elif asset_type == "ExternalLink":
                _write_link(udemy, asset, course_id, lecture_id, output_dir)

        elapsed = time.time() - start_time
        return DownloadResult.ok(elapsed_seconds=elapsed, retries=total_retries)

    except (OSError, KeyError, IndexError, ValueError) as error:
        return DownloadResult.failed(
            f"Supplementary asset download failed: {error}",
            elapsed_seconds=time.time() - start_time,
            retries=total_retries,
        )


def _unique_filepath(directory: str, filename: str) -> str:
    """Return a filepath in *directory* that does not collide with existing files.
    Appends ` (2)`, ` (3)`, … if needed."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


def _download_file(udemy, asset, course_id, lecture_id, output_dir) -> int:
    """Download a file asset with retry logic.  Returns the number of retries used."""
    retries_used = 0
    metadata = udemy.request(
        FILE_ASSET_URL.format(course_id=course_id, lecture_id=lecture_id, asset_id=asset["id"])
    ).json()
    url = metadata["download_urls"]["File"][0]["file"]

    raw_name = os.path.basename(asset.get("filename") or f"asset-{asset['id']}")
    filepath = _unique_filepath(output_dir, raw_name)

    last_error = None
    for attempt in range(ASSET_MAX_RETRIES + 1):
        try:
            response = udemy.request(url, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            response.raise_for_status()

            total_size = int(response.headers.get("content-length") or 0)
            downloaded = 0

            with open(filepath, "wb") as file:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)

            final_size = os.path.getsize(filepath) if os.path.isfile(filepath) else 0

            # Verify size if we got a content-length header
            if total_size and final_size != total_size:
                raise IOError(
                    f"Size mismatch for '{raw_name}': expected {total_size}, got {final_size}"
                )

            if final_size >= 1024 * 1024:
                logger.info(f"  Asset '{raw_name}': {final_size / (1024 * 1024):.1f} MB")
            else:
                logger.info(f"  Asset '{raw_name}': {final_size / 1024:.1f} KB")

            return retries_used

        except (requests.RequestException, IOError, OSError) as err:
            last_error = err
            retries_used += 1
            if attempt < ASSET_MAX_RETRIES:
                delay = DEFAULT_RETRY.delay_for_attempt(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{ASSET_MAX_RETRIES} for asset '{raw_name}' "
                    f"after {delay:.1f}s – {err}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"Asset '{raw_name}' failed after {ASSET_MAX_RETRIES + 1} attempts: "
                    f"{last_error}"
                )
                raise

    return retries_used  # shouldn't reach here, but satisfy the type checker


def _write_link(udemy, asset, course_id, lecture_id, output_dir):
    response = udemy.request(
        LINK_ASSET_URL.format(course_id=course_id, lecture_id=lecture_id, asset_id=asset["id"])
    ).json()

    raw_name = os.path.basename(asset.get("filename") or f"asset-{asset['id']}") + ".url"
    filepath = _unique_filepath(output_dir, raw_name)

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(f"[InternetShortcut]\nURL={response['external_url']}\n")
