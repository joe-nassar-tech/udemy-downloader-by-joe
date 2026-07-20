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


def _run_downloader(source_url, output_dir, output_name, task_id, progress, drm_key=None):
    command = [N_M3U8DL_RE_PATH, source_url, "--save-dir", output_dir, "--save-name", output_name,
               "--auto-select", "--concurrent-download", "--del-after-done", "--no-log", "--tmp-dir", output_dir,
               "--log-level", "ERROR"]
    if drm_key:
        command.extend(["--key", drm_key, "--decryption-engine", "SHAKA_PACKAGER",
                        "--decryption-binary-path", os.path.abspath(SHAKA_PACKAGER_PATH), "-mt", "-M", "format=mkv"])

    safe_command = ["[REDACTED]" if item == drm_key else item for item in command]
    print("DEBUG: Running N_m3u8DL-RE:", subprocess.list2cmdline(safe_command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace")
    output_lines = []
    pattern = re.compile(r"(\d+\.\d+%)")
    for output in iter(process.stdout.readline, ""):
        output_lines.append(output)
        matches = pattern.findall(output)
        if matches:
            progress.update(task_id, completed=min(float(matches[0][:-1]), 99))
    process.wait()
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


def _select_media_playlist(master_url):
    response = requests.get(master_url, timeout=(15, 120))
    response.raise_for_status()
    playlist = m3u8.loads(response.text)
    if not playlist.playlists:
        return master_url
    best = max(playlist.playlists, key=lambda item: (item.stream_info.resolution or (0, 0))[0] * (item.stream_info.resolution or (0, 0))[1])
    return _with_parent_query(master_url, urljoin(master_url, best.uri))


def download_and_merge_m3u8(m3u8_url, download_folder_path, title, task_id, progress, drm_key=None):
    """Select the best media playlist without losing its web address."""
    progress.update(task_id, description=f"Downloading stream {remove_emojis_and_binary(title)}", completed=0)
    output_dir = os.path.dirname(download_folder_path)
    try:
        media_url = _select_media_playlist(m3u8_url)
    except requests.RequestException as error:
        return DownloadResult.failed(f"Could not fetch the HLS playlist: {error}")
    except ValueError as error:
        return DownloadResult.failed(f"Could not read the HLS playlist: {error}")
    result = _run_downloader(media_url, output_dir, f"{title}.mp4", task_id, progress, drm_key)
    if not result.success:
        progress.console.log(f"[red]HLS download failed: {remove_emojis_and_binary(title)}[/red]")
        return result
    output_file = os.path.join(output_dir, f"{title}.mp4")
    if not os.path.isfile(output_file) or os.path.getsize(output_file) == 0:
        return DownloadResult.failed(f"HLS downloader reported success but did not create {output_file}.")
    progress.update(task_id, completed=100)
    progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(title)}[/green]")
    shutil.rmtree(download_folder_path, ignore_errors=True)
    return DownloadResult.ok()
