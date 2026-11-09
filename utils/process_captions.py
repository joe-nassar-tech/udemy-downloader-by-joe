import os
import time
import requests
import webvtt

from constants import logger, DEFAULT_RETRY
from utils.download_result import DownloadResult

# Number of retry attempts for caption downloads
CAPTION_MAX_RETRIES = 2


def download_captions(captions, download_folder_path, title, captions_list, convert_to_srt):
    """Download captions with retry logic, multi-format support, and progress reporting."""
    start_time = time.time()
    total_retries = 0

    try:
        matching = [c for c in captions if c.get("locale_id") in captions_list]

        if not matching:
            logger.debug(
                f"No captions matched the requested locales {captions_list} for '{title}'. "
                f"Available locales: {[c.get('locale_id') for c in captions]}"
            )
            return DownloadResult.ok(elapsed_seconds=time.time() - start_time)

        for caption in matching:
            locale = caption.get("locale_id", "unknown")
            url = caption.get("url")

            if not url:
                logger.warning(
                    f"Caption metadata for locale '{locale}' did not include a URL "
                    f"(lecture: {title})."
                )
                return DownloadResult.failed(
                    f"Caption metadata for locale '{locale}' did not include a URL."
                )

            # Detect format from filename
            file_name = caption.get("file_name", "")
            if file_name.endswith(".vtt"):
                fmt = "vtt"
            elif file_name.endswith(".srt"):
                fmt = "srt"
            elif file_name.endswith(".txt"):
                fmt = "txt"
            else:
                # Default to VTT – most common on Udemy
                fmt = "vtt"

            # ---- Download with retries ----
            response = None
            last_error = None
            for attempt in range(CAPTION_MAX_RETRIES + 1):
                try:
                    logger.debug(
                        f"Downloading caption '{locale}' for '{title}' (attempt {attempt + 1})"
                    )
                    response = requests.get(url, timeout=(10, 60))

                    # Detect expired / invalid URLs
                    if response.status_code in (403, 410):
                        return DownloadResult.failed(
                            f"Caption URL for locale '{locale}' is expired or invalid "
                            f"(HTTP {response.status_code}). Re-fetch lecture metadata."
                        )

                    response.raise_for_status()
                    break  # success

                except requests.RequestException as err:
                    last_error = err
                    total_retries += 1
                    if attempt < CAPTION_MAX_RETRIES:
                        delay = DEFAULT_RETRY.delay_for_attempt(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{CAPTION_MAX_RETRIES} caption '{locale}' "
                            f"for '{title}' after {delay:.1f}s – {err}"
                        )
                        time.sleep(delay)
                    else:
                        return DownloadResult.failed(
                            f"Caption download for locale '{locale}' failed after "
                            f"{CAPTION_MAX_RETRIES + 1} attempts: {last_error}",
                            elapsed_seconds=time.time() - start_time,
                            retries=total_retries,
                        )

            label = caption.get("video_label", "caption")
            base_name = f"{title} - {label}"

            # ---- Write the caption file ----
            if fmt == "vtt":
                vtt_path = os.path.join(download_folder_path, f"{base_name}.vtt")
                with open(vtt_path, "wb") as file:
                    file.write(response.content)
                logger.debug(f"Saved VTT caption: {vtt_path}")

                if convert_to_srt:
                    srt_path = vtt_path[:-4] + ".srt"
                    try:
                        webvtt.read(vtt_path).save_as_srt(srt_path)
                        os.remove(vtt_path)
                        logger.debug(f"Converted VTT → SRT: {srt_path}")
                    except Exception as conv_err:
                        logger.warning(
                            f"VTT→SRT conversion failed for '{label}' ({locale}): {conv_err}. "
                            f"Keeping original VTT."
                        )

            elif fmt == "srt":
                srt_path = os.path.join(download_folder_path, f"{base_name}.srt")
                with open(srt_path, "wb") as file:
                    file.write(response.content)
                logger.debug(f"Saved SRT caption: {srt_path}")

            else:
                # txt or unknown – save raw
                out_path = os.path.join(download_folder_path, f"{base_name}.{fmt}")
                with open(out_path, "wb") as file:
                    file.write(response.content)
                logger.debug(f"Saved caption ({fmt}): {out_path}")

        elapsed = time.time() - start_time
        return DownloadResult.ok(elapsed_seconds=elapsed, retries=total_retries)

    except (OSError, ValueError) as error:
        return DownloadResult.failed(
            f"Caption download failed: {error}",
            elapsed_seconds=time.time() - start_time,
            retries=total_retries,
        )
