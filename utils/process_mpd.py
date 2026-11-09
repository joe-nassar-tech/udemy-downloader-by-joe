"""DASH (mpd) download with retries, timeout, quality selection, and cleanup."""

import os
import re
import shutil
import subprocess
import time

from constants import remove_emojis_and_binary
from utils.download_result import DownloadResult

N_M3U8DL_RE_PATH = os.getenv("N_M3U8DL_RE_PATH", "n_m3u8dl-re.exe")
SHAKA_PACKAGER_PATH = os.getenv("SHAKA_PACKAGER_PATH", "shaka-packager.exe")

DEFAULT_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "0")) or None


def _run(command, task_id, progress, timeout=DEFAULT_TIMEOUT):
    safe_command = ["[REDACTED]" if item.startswith("--key") is False and len(item) > 32 else item for item in command]
    print("DEBUG: Running N_m3u8DL-RE:", subprocess.list2cmdline(safe_command))

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
    except FileNotFoundError:
        return 127, f"Executable not found: {command[0]}"

    lines = []
    patterns = [
        re.compile(r"(\d+\.\d+)%"),
        re.compile(r"(\d+)%"),
        re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%"),
    ]

    try:
        for output in iter(process.stdout.readline, ""):
            lines.append(output)
            for pattern in patterns:
                matches = pattern.findall(output)
                if matches:
                    progress.update(task_id, completed=min(float(matches[-1]), 99))
                    break
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return 124, f"DASH downloader timed out after {timeout}s"
    except Exception as e:
        try:
            process.kill()
        except Exception:
            pass
        return 1, f"Process execution failed: {e}"

    return process.returncode, "".join(lines)


def download_and_merge_mpd(
    mpd_url,
    download_folder_path,
    title,
    length=None,
    key=None,
    task_id=None,
    progress=None,
    max_retries=2,
    timeout=DEFAULT_TIMEOUT,
):
    """Download DASH stream with retry logic, proper cleanup and error diagnostics."""
    safe_title = remove_emojis_and_binary(title)
    progress.update(task_id, description=f"Downloading DASH stream {safe_title}", completed=0)

    command = [
        N_M3U8DL_RE_PATH,
        mpd_url,
        "--save-dir",
        download_folder_path,
        "--save-name",
        f"{title}.mp4",
        "--auto-select",
        "--concurrent-download",
        "--del-after-done",
        "--no-log",
        "--tmp-dir",
        download_folder_path,
        "--log-level",
        "ERROR",
    ]
    if key:
        command.extend([
            "--key", key,
            "--decryption-engine", "SHAKA_PACKAGER",
            "--decryption-binary-path", os.path.abspath(SHAKA_PACKAGER_PATH),
            "-mt", "-M", "format=mkv",
        ])

    last_error = None
    try:
        for attempt in range(1, max_retries + 1):
            code, output = _run(command, task_id, progress, timeout=timeout)
            if code == 0:
                break
            detail = output[-2000:].strip() or "No diagnostic output was produced."
            last_error = f"DASH downloader exited with code {code}. {detail}"
            print(f"DEBUG: DASH downloader failed attempt {attempt}/{max_retries} (exit {code}):\n{detail}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        else:
            return DownloadResult.failed(last_error or "DASH downloader failed on all attempts.")

        final_file = os.path.join(os.path.dirname(download_folder_path), f"{title}.mp4")

        # Check for MKV files (DRM decrypted)
        mkv_files = [
            os.path.join(download_folder_path, name)
            for name in os.listdir(download_folder_path)
            if name.lower().endswith(".mkv")
        ]
        if mkv_files:
            try:
                convert = subprocess.run(
                    ["ffmpeg", "-loglevel", "error", "-i", mkv_files[0], "-c:v", "copy", "-c:a", "aac", "-y", final_file],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,
                )
                if convert.returncode:
                    return DownloadResult.failed(f"FFmpeg could not convert the DASH output: {convert.stderr[-1000:]}")
            except subprocess.TimeoutExpired:
                return DownloadResult.failed("FFmpeg timed out during MKV to MP4 conversion.")
        else:
            candidates = [os.path.join(download_folder_path, f"{title}.mp4"), final_file]
            source = next((path for path in candidates if os.path.isfile(path) and os.path.getsize(path) > 0), None)
            if not source:
                return DownloadResult.failed("DASH downloader completed but no playable output file was found.")
            if source != final_file:
                shutil.move(source, final_file)

        if not os.path.isfile(final_file) or os.path.getsize(final_file) == 0:
            return DownloadResult.failed("DASH processing did not create a non-empty MP4 output.")

        progress.update(task_id, completed=100)
        progress.console.log(f"[green]Downloaded {safe_title}[/green]")
        return DownloadResult.ok(file_path=final_file)

    finally:
        # Guarantee cleanup of temporary folder
        if os.path.isdir(download_folder_path):
            shutil.rmtree(download_folder_path, ignore_errors=True)
