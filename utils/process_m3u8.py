"""HLS (m3u8) download with quality selection, retries, progress parsing, timeout, and cleanup."""

import os
import re
import shutil
import subprocess
from urllib.parse import urljoin, urlparse, urlunparse

import m3u8
import requests

from constants import remove_emojis_and_binary
from utils.download_result import DownloadResult

N_M3U8DL_RE_PATH = os.getenv("N_M3U8DL_RE_PATH", "n_m3u8dl-re.exe")
SHAKA_PACKAGER_PATH = os.getenv("SHAKA_PACKAGER_PATH", "shaka-packager.exe")

# Subprocess timeout (seconds) — 0 = no timeout
DEFAULT_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "0")) or None


def _run_downloader(source_url, output_dir, output_name, task_id, progress, drm_key=None, timeout=DEFAULT_TIMEOUT):
    command = [N_M3U8DL_RE_PATH, source_url, "--save-dir", output_dir, "--save-name", output_name,
               "--auto-select", "--concurrent-download", "--del-after-done", "--no-log", "--tmp-dir", output_dir,
               "--log-level", "ERROR"]
    if drm_key:
        command.extend(["--key", drm_key, "--decryption-engine", "SHAKA_PACKAGER",
                        "--decryption-binary-path", os.path.abspath(SHAKA_PACKAGER_PATH), "-mt", "-M", "format=mkv"])

    safe_command = ["[REDACTED]" if item == drm_key else item for item in command]
    print("DEBUG: Running N_m3u8DL-RE:", subprocess.list2cmdline(safe_command))

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return DownloadResult.failed(f"N_m3u8DL-RE not found at {N_M3U8DL_RE_PATH}")

    output_lines = []
    # Multiple progress patterns: "12.34%", "12%", "[download] 12.3%"
    patterns = [
        re.compile(r"(\d+\.\d+)%"),
        re.compile(r"(\d+)%"),
        re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%"),
    ]

    try:
        for output in iter(process.stdout.readline, ""):
            output_lines.append(output)
            for pattern in patterns:
                matches = pattern.findall(output)
                if matches:
                    progress.update(task_id, completed=min(float(matches[-1]), 99))
                    break
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return DownloadResult.failed(f"N_m3u8DL-RE timed out after {timeout}s")
    except Exception as e:
        try:
            process.kill()
        except Exception:
            pass
        return DownloadResult.failed(f"N_m3u8DL-RE error: {e}")

    output = "".join(output_lines)
    if process.returncode:
        detail = output[-2000:].strip() or "No diagnostic output was produced."
        print(f"DEBUG: N_m3u8DL-RE failed (exit {process.returncode}):\n{detail}")
        return DownloadResult.failed(f"N_m3u8DL-RE exited with code {process.returncode}. {detail}")
    return DownloadResult.ok()


def _with_parent_query(parent_url, child_url):
    """Keep a signed parent query when a relative child URL has none of its own."""
    parent = urlparse(parent_url)
    child = urlparse(child_url)
    if parent.query and not child.query:
        return urlunparse(child._replace(query=parent.query))
    return child_url


def _select_media_playlist(master_url, max_retries=2, preferred_quality=None):
    """Fetch the master playlist with retries, then pick the best variant.

    Selection criteria (in order):
    1. If preferred_quality is set, pick the variant closest to that height.
    2. Otherwise pick by (resolution_area * bandwidth) to balance quality and smoothness.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(master_url, timeout=(15, 120))
            response.raise_for_status()
            break
        except requests.RequestException as e:
            last_error = e
            if attempt < max_retries:
                import time
                time.sleep(2 ** attempt)
    else:
        raise requests.RequestException(f"Failed after {max_retries} retries: {last_error}")

    playlist = m3u8.loads(response.text)
    if not playlist.playlists:
        return master_url

    def _score(item):
        res = item.stream_info.resolution or (0, 0)
        bw = item.stream_info.bandwidth or 0
        return res[0] * res[1], bw

    if preferred_quality:
        # Parse quality string like "1080", "720p", etc.
        try:
            target_h = int(preferred_quality.lower().replace("p", "").replace("k", "000").strip())
        except ValueError:
            target_h = None

        if target_h:
            # Sort by distance from target height, prefer higher bandwidth on ties
            def _quality_distance(item):
                res = item.stream_info.resolution or (0, 0)
                h = res[1]
                return abs(h - target_h), -(item.stream_info.bandwidth or 0)

            best = min(playlist.playlists, key=_quality_distance)
        else:
            best = max(playlist.playlists, key=lambda p: _score(p)[0] * max(_score(p)[1], 1))
    else:
        # Default: highest resolution, with bandwidth as tiebreaker
        best = max(playlist.playlists, key=lambda p: (_score(p)[0], _score(p)[1]))

    return _with_parent_query(master_url, urljoin(master_url, best.uri))


def download_and_merge_m3u8(m3u8_url, download_folder_path, title, task_id, progress, drm_key=None,
                             preferred_quality=None, timeout=DEFAULT_TIMEOUT):
    """Select the best media playlist without losing its web address."""
    progress.update(task_id, description=f"Downloading stream {remove_emojis_and_binary(title)}", completed=0)
    output_dir = os.path.dirname(download_folder_path)
    cleanup_needed = True

    try:
        try:
            media_url = _select_media_playlist(m3u8_url, max_retries=2, preferred_quality=preferred_quality)
        except requests.RequestException as error:
            return DownloadResult.failed(f"Could not fetch the HLS playlist: {error}")
        except ValueError as error:
            return DownloadResult.failed(f"Could not read the HLS playlist: {error}")

        result = _run_downloader(media_url, output_dir, f"{title}.mp4", task_id, progress, drm_key, timeout=timeout)
        if not result.success:
            progress.console.log(f"[red]HLS download failed: {remove_emojis_and_binary(title)}[/red]")
            return result

        output_file = os.path.join(output_dir, f"{title}.mp4")
        if not os.path.isfile(output_file) or os.path.getsize(output_file) == 0:
            return DownloadResult.failed(f"HLS downloader reported success but did not create {output_file}.")

        progress.update(task_id, completed=100)
        progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(title)}[/green]")
        cleanup_needed = False  # Success — keep the file
        return DownloadResult.ok()

    finally:
        # Always clean up temp folder (even on failure)
        if os.path.isdir(download_folder_path):
            shutil.rmtree(download_folder_path, ignore_errors=True)
