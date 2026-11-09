import os
import re
import shutil
import requests

from constants import ARTICLE_URL, logger
from utils.download_result import DownloadResult

# HTML template for articles with clean CSS styling
_ARTICLE_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #ffffff;
            --fg: #1a1a2e;
            --accent: #a435f0;
            --code-bg: #f5f5f5;
            --border: #e0e0e0;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #1c1d1f;
                --fg: #e0e0e0;
                --accent: #c084fc;
                --code-bg: #2d2d30;
                --border: #3e4143;
            }}
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.7;
            color: var(--fg);
            background-color: var(--bg);
            max-width: 820px;
            margin: 0 auto;
            padding: 2rem 1.5rem;
        }}
        header {{
            border-bottom: 2px solid var(--accent);
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}
        header h1 {{
            font-size: 1.8rem;
            color: var(--accent);
        }}
        header .meta {{
            font-size: 0.85rem;
            color: #888;
            margin-top: 0.3rem;
        }}
        h1, h2, h3, h4, h5, h6 {{ margin-top: 1.5em; margin-bottom: 0.5em; }}
        p {{ margin-bottom: 1em; }}
        img {{ max-width: 100%; height: auto; border-radius: 4px; margin: 1em 0; }}
        pre, code {{
            font-family: "Fira Code", "Cascadia Code", "Consolas", monospace;
            background-color: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 4px;
        }}
        code {{ padding: 0.15em 0.4em; font-size: 0.9em; }}
        pre {{ padding: 1em; overflow-x: auto; margin: 1em 0; }}
        pre code {{ border: none; padding: 0; }}
        a {{ color: var(--accent); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        blockquote {{
            border-left: 4px solid var(--accent);
            padding: 0.5em 1em;
            margin: 1em 0;
            color: #666;
        }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
        th, td {{ border: 1px solid var(--border); padding: 0.6em 0.8em; text-align: left; }}
        th {{ background-color: var(--code-bg); }}
        ul, ol {{ margin: 0.5em 0 1em 1.5em; }}
        li {{ margin-bottom: 0.3em; }}
    </style>
</head>
<body>
    <header>
        <h1>{title}</h1>
        <div class="meta">{meta_line}</div>
    </header>
    <article>
{body}
    </article>
</body>
</html>
"""


def _download_embedded_images(html_body: str, output_dir: str) -> str:
    """Find <img src="..."> tags, download the images locally, and rewrite
    the src attributes to point to local files.  Returns the updated HTML."""
    img_dir = os.path.join(output_dir, "images")
    pattern = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)
    urls_found = pattern.findall(html_body)

    if not urls_found:
        return html_body

    os.makedirs(img_dir, exist_ok=True)

    for img_url in urls_found:
        if img_url.startswith("data:") or img_url.startswith("file:"):
            continue
        try:
            resp = requests.get(img_url, timeout=(10, 30), stream=True)
            resp.raise_for_status()

            # Derive a safe filename
            basename = os.path.basename(img_url.split("?")[0]) or "image.png"
            # De-duplicate
            local_path = os.path.join(img_dir, basename)
            counter = 2
            base, ext = os.path.splitext(basename)
            while os.path.exists(local_path):
                local_path = os.path.join(img_dir, f"{base}_{counter}{ext}")
                counter += 1

            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Rewrite the src to a relative path
            relative = os.path.join("images", os.path.basename(local_path))
            html_body = html_body.replace(img_url, relative, 1)
            logger.debug(f"  Downloaded article image: {img_url} → {relative}")

        except (requests.RequestException, OSError) as err:
            logger.warning(f"  Could not download article image {img_url}: {err}")
            # Leave the original URL in place

    return html_body


def download_article(udemy, article, download_folder_path, title, task_id, progress,
                     course_title: str = ""):
    """Download an article and wrap it in a styled HTML document."""
    progress.update(task_id, description=f"Downloading article {title}", completed=0)
    try:
        response = udemy.request(ARTICLE_URL.format(article_id=article["id"])).json()
        body = response.get("body")
        if not body:
            return DownloadResult.failed("Article API response did not include a body.")

        # Ensure the body is a proper unicode string
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        output_dir = os.path.dirname(download_folder_path)
        output = os.path.join(output_dir, f"{title}.html")

        # Download embedded images and rewrite paths
        body = _download_embedded_images(body, output_dir)

        # Build metadata line
        meta_parts = []
        if course_title:
            meta_parts.append(f"Course: {course_title}")
        meta_parts.append("Source: Udemy")
        meta_line = " · ".join(meta_parts)

        # Wrap in styled HTML template
        html = _ARTICLE_HTML_TEMPLATE.format(
            title=title.replace("{", "{{").replace("}", "}}") if "{" in title else title,
            meta_line=meta_line,
            body=body,
        )

        with open(output, "w", encoding="utf-8", errors="replace") as file:
            file.write(html)

        progress.update(task_id, completed=100)
        progress.console.log(f"[green]Downloaded {title}[/green]")
        shutil.rmtree(download_folder_path, ignore_errors=True)

        return DownloadResult.with_file_info(output)

    except (OSError, KeyError, ValueError) as error:
        return DownloadResult.failed(f"Article download failed: {error}")
