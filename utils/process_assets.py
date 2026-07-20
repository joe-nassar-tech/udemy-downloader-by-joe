import os

from constants import LINK_ASSET_URL, FILE_ASSET_URL
from utils.download_result import DownloadResult


def download_supplementary_assets(udemy, assets, output_dir, course_id, lecture_id):
    try:
        os.makedirs(output_dir, exist_ok=True)
        for asset in assets:
            asset_type = asset.get("asset_type")
            if asset_type == "File":
                _download_file(udemy, asset, course_id, lecture_id, output_dir)
            elif asset_type == "ExternalLink":
                _write_link(udemy, asset, course_id, lecture_id, output_dir)
        return DownloadResult.ok()
    except (OSError, KeyError, IndexError, ValueError) as error:
        return DownloadResult.failed(f"Supplementary asset download failed: {error}")


def _download_file(udemy, asset, course_id, lecture_id, output_dir):
    metadata = udemy.request(FILE_ASSET_URL.format(course_id=course_id, lecture_id=lecture_id, asset_id=asset["id"])).json()
    url = metadata["download_urls"]["File"][0]["file"]
    response = udemy.request(url)
    response.raise_for_status()
    name = os.path.basename(asset.get("filename") or f"asset-{asset['id']}")
    with open(os.path.join(output_dir, name), "wb") as file:
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if chunk:
                file.write(chunk)


def _write_link(udemy, asset, course_id, lecture_id, output_dir):
    response = udemy.request(LINK_ASSET_URL.format(course_id=course_id, lecture_id=lecture_id, asset_id=asset["id"])).json()
    name = os.path.basename(asset.get("filename") or f"asset-{asset['id']}") + ".url"
    with open(os.path.join(output_dir, name), "w", encoding="utf-8") as file:
        file.write(f"[InternetShortcut]\nURL={response['external_url']}\n")
