import os
import requests
import webvtt

from utils.download_result import DownloadResult


def download_captions(captions, download_folder_path, title, captions_list, convert_to_srt):
    try:
        for caption in (caption for caption in captions if caption.get("locale_id") in captions_list):
            url = caption.get("url")
            if not url:
                return DownloadResult.failed("Caption metadata did not include a URL.")
            response = requests.get(url, timeout=(15, 120))
            response.raise_for_status()
            if not caption.get("file_name", "").endswith(".vtt"):
                return DownloadResult.failed("Only WebVTT captions are supported.")
            name = f"{title} - {caption.get('video_label', 'caption')}.vtt"
            vtt_path = os.path.join(download_folder_path, name)
            with open(vtt_path, "wb") as file:
                file.write(response.content)
            if convert_to_srt:
                srt_path = vtt_path[:-4] + ".srt"
                webvtt.read(vtt_path).save_as_srt(srt_path)
                os.remove(vtt_path)
        return DownloadResult.ok()
    except (requests.RequestException, OSError, ValueError) as error:
        return DownloadResult.failed(f"Caption download failed: {error}")
