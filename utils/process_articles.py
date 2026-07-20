import os
import shutil

from constants import ARTICLE_URL
from utils.download_result import DownloadResult


def download_article(udemy, article, download_folder_path, title, task_id, progress):
    progress.update(task_id, description=f"Downloading article {title}", completed=0)
    try:
        response = udemy.request(ARTICLE_URL.format(article_id=article["id"])).json()
        body = response.get("body")
        if not body:
            return DownloadResult.failed("Article API response did not include a body.")
        output = os.path.join(os.path.dirname(download_folder_path), f"{title}.html")
        with open(output, "w", encoding="utf-8", errors="replace") as file:
            file.write(body)
        progress.update(task_id, completed=100)
        progress.console.log(f"[green]Downloaded {title}[/green]")
        shutil.rmtree(download_folder_path, ignore_errors=True)
        return DownloadResult.ok()
    except (OSError, KeyError, ValueError) as error:
        return DownloadResult.failed(f"Article download failed: {error}")
