import os
import re
import shutil
import subprocess

from constants import remove_emojis_and_binary
from utils.download_result import DownloadResult

N_M3U8DL_RE_PATH = os.getenv("N_M3U8DL_RE_PATH", "n_m3u8dl-re.exe")
SHAKA_PACKAGER_PATH = os.getenv("SHAKA_PACKAGER_PATH", "shaka-packager.exe")


def _run(command, task_id, progress):
    safe_command = ["[REDACTED]" if item.startswith("--key") is False and len(item) > 32 else item for item in command]
    print("DEBUG: Running N_m3u8DL-RE:", subprocess.list2cmdline(safe_command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace")
    lines, pattern = [], re.compile(r"(\d+\.\d+%)")
    for output in iter(process.stdout.readline, ""):
        lines.append(output)
        matches = pattern.findall(output)
        if matches:
            progress.update(task_id, completed=min(float(matches[0][:-1]), 99))
    process.wait()
    return process.returncode, "".join(lines)


def download_and_merge_mpd(mpd_url, download_folder_path, title, length, key, task_id, progress):
    progress.update(task_id, description=f"Downloading stream {remove_emojis_and_binary(title)}", completed=0)
    command = [N_M3U8DL_RE_PATH, mpd_url, "--save-dir", download_folder_path, "--save-name", f"{title}.mp4",
               "--auto-select", "--concurrent-download", "--del-after-done", "--no-log", "--tmp-dir", download_folder_path,
               "--log-level", "ERROR"]
    if key:
        command.extend(["--key", key, "--decryption-engine", "SHAKA_PACKAGER",
                        "--decryption-binary-path", os.path.abspath(SHAKA_PACKAGER_PATH), "-mt", "-M", "format=mkv"])
    code, output = _run(command, task_id, progress)
    if code:
        detail = output[-2000:].strip() or "No diagnostic output was produced."
        print(f"DEBUG: DASH downloader failed (exit {code}):\n{detail}")
        return DownloadResult.failed(f"DASH downloader exited with code {code}. {detail}")

    final_file = os.path.join(os.path.dirname(download_folder_path), f"{title}.mp4")
    mkv_files = [os.path.join(download_folder_path, name) for name in os.listdir(download_folder_path) if name.lower().endswith(".mkv")]
    if mkv_files:
        convert = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", mkv_files[0], "-c:v", "copy", "-c:a", "aac", "-y", final_file],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
        if convert.returncode:
            return DownloadResult.failed(f"FFmpeg could not convert the DASH output: {convert.stderr[-1000:]}")
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
    progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(title)}[/green]")
    shutil.rmtree(download_folder_path, ignore_errors=True)
    return DownloadResult.ok()
