import os
import shutil
import requests

from constants import remove_emojis_and_binary
from utils.download_result import DownloadResult


def download_mp4(url, download_folder_path, title, task_id, progress):
    progress.update(task_id, description=f"Downloading video {remove_emojis_and_binary(title)}", completed=0)
    output_file = os.path.join(os.path.dirname(download_folder_path), f"{title}.mp4")
    try:
        with requests.get(url, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length") or 0)
            downloaded = 0
            with open(output_file, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            progress.update(task_id, completed=min(downloaded * 100 / total_size, 99))
        if not os.path.isfile(output_file) or os.path.getsize(output_file) == 0:
            return DownloadResult.failed("The MP4 response completed without creating a non-empty file.")
        progress.update(task_id, completed=100)
        progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(title)}[/green]")
        shutil.rmtree(download_folder_path, ignore_errors=True)
        return DownloadResult.ok()
    except requests.RequestException as error:
        return DownloadResult.failed(f"MP4 request failed: {error}")
    except OSError as error:
        return DownloadResult.failed(f"Could not write the MP4 output: {error}")
