import json
import os
import sys
import requests
import argparse
import subprocess
from pathvalidate import sanitize_filename
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.live import Live
from rich.tree import Tree
from rich.text import Text
from rich import print as rprint

import re
import http.cookiejar as cookielib
from concurrent.futures import ThreadPoolExecutor, as_completed

from constants import *
from utils.process_m3u8 import download_and_merge_m3u8
from utils.process_mpd import download_and_merge_mpd
from utils.process_captions import download_captions
from utils.process_assets import download_supplementary_assets
from utils.process_articles import download_article
from utils.process_mp4 import download_mp4
from download_cache import DownloadCache
from dotenv import load_dotenv

console = Console()

# Load environment variables from .env
load_dotenv()

COOKIES_PATH = os.getenv('COOKIES_PATH', 'cookies.txt')
COOKIES_JSON_PATH = os.getenv('COOKIES_JSON_PATH', 'cookies.json')
WIDEVINE_KEY = os.getenv('WIDEVINE_KEY', '')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'courses')
CONCURRENT_DOWNLOADS = int(os.getenv('CONCURRENT_DOWNLOADS', '2'))
SUBTITLE_LANG = os.getenv('SUBTITLE_LANG', 'en')
N_M3U8DL_RE_PATH = os.getenv('N_M3U8DL_RE_PATH', 'n_m3u8dl-re.exe')
SHAKA_PACKAGER_PATH = os.getenv('SHAKA_PACKAGER_PATH', 'shaka-packager.exe')
COURSE_LINK = os.getenv('COURSE_LINK', None)

# Set UTF-8 encoding for console output to handle Unicode characters
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# Convert cookies.json to cookies.txt if cookies.txt does not exist or is empty
if (not os.path.exists(COOKIES_PATH)) or os.path.getsize(COOKIES_PATH) == 0:
    if os.path.exists(COOKIES_JSON_PATH):
        try:
            with open(COOKIES_JSON_PATH, 'r', encoding='utf-8') as f:
                cookies_json = json.load(f)
            with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                for cookie in cookies_json:
                    domain = cookie.get('domain', '')
                    flag = 'TRUE' if cookie.get('hostOnly', False) is False else 'FALSE'
                    path = cookie.get('path', '/')
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expiration = str(cookie.get('expirationDate', 0))
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
        except Exception as e:
            print(f"[ERROR] Failed to convert cookies.json to cookies.txt: {e}")
            print("Please paste your browser-exported cookies in cookies.json.")
            exit(1)
    else:
        print("[ERROR] No cookies found. Please paste your browser-exported cookies in cookies.json.")
        exit(1)

def parse_chapter_filter(chapter_str):
    """
    Given a string like "1,3-5,7,9-11", return a set of chapter numbers.
    """
    chapters = set()
    for part in chapter_str.split(','):
        if '-' in part:
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                chapters.update(range(start, end + 1))
            except ValueError:
                logger.error("Invalid range in --chapter argument: %s", part)
        else:
            try:
                chapters.add(int(part.strip()))
            except ValueError:
                logger.error("Invalid chapter number in --chapter argument: %s", part)
    return chapters

class Udemy:
    def __init__(self):
        global cookie_jar
        try:
            cookie_jar = cookielib.MozillaCookieJar(COOKIES_PATH)
            cookie_jar.load()
        except Exception as e:
            logger.critical(f"The provided cookie file could not be read or is incorrectly formatted. Please ensure the file is in the correct format and contains valid authentication cookies.")
            sys.exit(1)
    
    def request(self, url):
        try:
            response = requests.get(url, cookies=cookie_jar, stream=True)
            return response
        except Exception as e:
            logger.critical(f"There was a problem reaching the Udemy server. This could be due to network issues, an invalid URL, or Udemy being temporarily unavailable.")

    def extract_course_id(self, course_url):

        with Loader(f"Fetching course ID"):            
            response = self.request(course_url)
            content_str = response.content.decode('utf-8')

        meta_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', content_str)

        if meta_match:
            url = meta_match.group(1)
            number_match = re.search(r'/(\d+)_', url)
            if number_match:
                number = number_match.group(1)
                logger.info(f"Course ID Extracted: {number}")
                return number
            else:
                logger.critical("Unable to retrieve a valid course ID from the provided course URL. Please check the course URL or try with --id.")
                sys.exit(1)
        else:
            logger.critical("Unable to retrieve a valid course ID from the provided course URL. Please check the course URL or try with --id")
            sys.exit(1)
        
    def fetch_course(self, course_id):
        try:
            response = self.request(COURSE_URL.format(course_id=course_id)).json()
    
            if response.get('detail') == 'Not found.':
                logger.critical("The course could not be found with the provided ID or URL. Please verify the course ID/URL and ensure that it is publicly accessible or you have the necessary permissions.")
                sys.exit(1)
            
            return response
        except Exception as e:
            logger.critical(f"Unable to retrieve the course details: {e}")
            sys.exit(1)
    
    def fetch_course_curriculum(self, course_id):
        all_results = []
        url = CURRICULUM_URL.format(course_id=course_id)
        total_count = 0

        logger.info("Fetching course curriculum. This may take a while")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3}%"),
            transient=True
        ) as progress:
            task = progress.add_task(description="Fetching Course Curriculum", total=total_count)

            while url:
                response = self.request(url).json()

                if response.get('detail') == 'You do not have permission to perform this action.':
                    progress.console.log("[red]The course was found, but the curriculum (lectures and materials) could not be retrieved. This could be due to API issues, restrictions on the course, or a malformed course structure.[/red]")
                    sys.exit(1)

                if response.get('detail') == 'Not found.':
                    progress.console.log("[red]The course was found, but the curriculum (lectures and materials) could not be retrieved. This could be due to API issues, restrictions on the course, or a malformed course structure.[/red]")
                    sys.exit(1)

                if total_count == 0:
                    total_count = response.get('count', 0)
                    progress.update(task, total=total_count)

                results = response.get('results', [])
                all_results.extend(results)
                progress.update(task, completed=len(all_results))

                url = response.get('next')

            progress.update(task_id = task, description="Fetched Course Curriculum", total=total_count)
        return self.organize_curriculum(all_results)
    
    def organize_curriculum(self, results):
        curriculum = []
        current_chapter = None

        total_lectures = 0

        for item in results:
            if item['_class'] == 'chapter':
                current_chapter = {
                    'id': item['id'],
                    'title': item['title'],
                    'is_published': item['is_published'],
                    'children': []
                }
                curriculum.append(current_chapter)
            elif item['_class'] == 'lecture':
                if current_chapter is not None:
                    current_chapter['children'].append(item)
                    if item['_class'] == 'lecture':
                        total_lectures += 1
                else:
                    logger.warning("Found lecture without a parent chapter.")

        num_chapters = len(curriculum)

        logger.info(f"Discovered Chapter(s): {num_chapters}")
        logger.info(f"Discovered Lectures(s): {total_lectures}")

        return curriculum

    def build_curriculum_tree(self, data, tree, index=1):
        for i, item in enumerate(data, start=index):
            if 'title' in item:
                title = f"{i:02d}. {item['title']}"
                if '_class' in item and item['_class'] == 'lecture':
                    time_estimation = item.get('asset', {}).get('time_estimation')
                    if time_estimation:
                        time_str = format_time(time_estimation)
                        title += f" ({time_str})"
                    node_text = Text(title, style="cyan")
                else:
                    node_text = Text(title, style="magenta")
                    
                node = tree.add(node_text)
                
                if 'children' in item:
                    self.build_curriculum_tree(item['children'], node, index=1)

    def fetch_lecture_info(self, course_id, lecture_id):
        try:
            return self.request(LECTURE_URL.format(course_id=course_id, lecture_id=lecture_id)).json()
        except Exception as e:
            logger.critical(f"Failed to fetch lecture info: {e}")
            sys.exit(1)
    
    def create_directory(self, path):
        try:
            os.makedirs(path)
        except FileExistsError:
            pass
        except Exception as e:
            logger.error(f"Failed to create directory \"{path}\": {e}")
            sys.exit(1)

    def download_lecture(self, course_id, lecture, lect_info, temp_folder_path, lindex, folder_path, task_id, progress, download_cache, chapter_index):
        lecture_title = sanitize_filename(lecture['title'])
        expected_file_path = os.path.join(folder_path, f"{lindex}. {lecture_title}.mp4")
        
        # Check if download is already completed
        is_completed, cached_record = download_cache.is_download_completed(
            chapter_index, lindex, lecture_title, expected_file_path
        )
        
        if is_completed:
            progress.console.log(f"[yellow]⏭️  Skipping {lecture_title} (already downloaded)[/yellow]")
            progress.remove_task(task_id)
            return
        
        # Mark download as started
        download_key = download_cache.mark_download_started(
            chapter_index, lindex, lecture_title, lecture['id'], lect_info['asset']['asset_type']
        )
        
        try:
            if not skip_captions and len(lect_info["asset"]["captions"]) > 0:
                download_captions(lect_info["asset"]["captions"], folder_path, f"{lindex}. {lecture_title}", captions, convert_to_srt)

            if not skip_assets and len(lecture["supplementary_assets"]) > 0:
                download_supplementary_assets(self, lecture["supplementary_assets"], folder_path, course_id, lect_info["id"])

            if not skip_lectures and lect_info['asset']['asset_type'] == "Video":
                mpd_url = next((item['src'] for item in lect_info['asset']['media_sources'] if item['type'] == "application/dash+xml"), None)
                mp4_url = next((item['src'] for item in lect_info['asset']['media_sources'] if item['type'] == "video/mp4"), None)
                m3u8_url = next((item['src'] for item in lect_info['asset']['media_sources'] if item['type'] == "application/x-mpegURL"), None)
                
                if mpd_url is None:
                    if m3u8_url is None:
                        if mp4_url is None:
                            logger.error(f"This lecture appears to be served in different format. We currently do not support downloading this format. Please create an issue on GitHub if you need this feature.")
                            download_cache.mark_download_failed(download_key, "Unsupported format")
                        else:
                            download_mp4(mp4_url, temp_folder_path, f"{lindex}. {lecture_title}", task_id, progress)
                    else:
                        download_and_merge_m3u8(m3u8_url, temp_folder_path, f"{lindex}. {lecture_title}", task_id, progress, key)
                else:
                    if key is None:
                        logger.warning("The video appears to be DRM-protected, and it may not play without a valid Widevine decryption key.")
                    download_and_merge_mpd(mpd_url, temp_folder_path, f"{lindex}. {lecture_title}", lecture['asset']['time_estimation'], key, task_id, progress)
            elif not skip_articles and lect_info['asset']['asset_type'] == "Article":
                download_article(self, lect_info['asset'], temp_folder_path, f"{lindex}. {lecture_title}", task_id, progress)
            
            # Mark download as completed if file exists
            if os.path.exists(expected_file_path):
                download_cache.mark_download_completed(download_key, expected_file_path)
            else:
                # For non-video content, mark as completed anyway
                download_cache.mark_download_completed(download_key, f"{folder_path}/{lindex}. {lecture_title}")
                
        except Exception as e:
            logger.error(f"Failed to download {lecture_title}: {e}")
            download_cache.mark_download_failed(download_key, str(e))

        try:
            progress.remove_task(task_id)
        except KeyError:
            pass

    def download_course(self, course_id, curriculum):
        # Initialize download cache
        download_cache = DownloadCache(course_id)
        download_cache.save_curriculum(curriculum)
        
        # Show progress summary if cache exists
        if len(download_cache.cache_data["downloads"]) > 0:
            download_cache.print_progress_summary()
        
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            ElapsedTimeColumn(),
        )
        
        tasks = {}
        futures = []

        with ThreadPoolExecutor(max_workers=max_concurrent_lectures) as executor, Live(progress, refresh_per_second=10):
            task_generator = (
                (f"{mindex:02}" if mindex < 10 else f"{mindex}", 
                chapter, 
                f"{lindex:02}" if lindex < 10 else f"{lindex}", 
                lecture,
                mindex)  # Add chapter index for cache
                for mindex, chapter in enumerate(curriculum, start=1)
                if is_valid_chapter(mindex, start_chapter, end_chapter, chapter_filter)
                for lindex, lecture in enumerate(chapter['children'], start=1)
                if is_valid_lecture(mindex, lindex, start_chapter, start_lecture, end_chapter, end_lecture)
            )

            for _ in range(max_concurrent_lectures):
                try:
                    mindex, chapter, lindex, lecture, chapter_index = next(task_generator)
                    folder_path = os.path.join(COURSE_DIR, f"{mindex}. {remove_emojis_and_binary(sanitize_filename(chapter['title']))}")
                    temp_folder_path = os.path.join(folder_path, str(lecture['id']))
                    self.create_directory(temp_folder_path)
                    lect_info = self.fetch_lecture_info(course_id, lecture['id'])
                    
                    task_id = progress.add_task(
                        f"Downloading Lecture: {lecture['title']} ({lindex}/{len(chapter['children'])})", 
                        total=100
                    )
                    tasks[task_id] = (lecture, lect_info, temp_folder_path, lindex, folder_path, chapter_index)
                    
                    future = executor.submit(
                        self.download_lecture, course_id, lecture, lect_info, temp_folder_path, lindex, folder_path, task_id, progress, download_cache, chapter_index
                    )

                    futures.append((task_id, future))
                except StopIteration:
                    break

            while futures:
                for future in as_completed(f[1] for f in futures):
                    task_id = next(task_id for task_id, f in futures if f == future)
                    future.result()
                    try:
                        progress.remove_task(task_id)
                    except:
                        pass
                    futures = [f for f in futures if f[1] != future]

                    try:
                        mindex, chapter, lindex, lecture, chapter_index = next(task_generator)
                        folder_path = os.path.join(COURSE_DIR, f"{mindex}. {sanitize_filename(chapter['title'])}")
                        temp_folder_path = os.path.join(folder_path, str(lecture['id']))
                        self.create_directory(temp_folder_path)
                        lect_info = self.fetch_lecture_info(course_id, lecture['id'])

                        task_id = progress.add_task(
                            f"Downloading Lecture: {lecture['title']} ({lindex}/{len(chapter['children'])})",
                            total=100
                        )
                        tasks[task_id] = (lecture, lect_info, temp_folder_path, lindex, folder_path, chapter_index)

                        future = executor.submit(
                            self.download_lecture, course_id, lecture, lect_info, temp_folder_path, lindex, folder_path, task_id, progress, download_cache, chapter_index
                        )

                        futures.append((task_id, future))
                    except StopIteration:
                        break

def check_prerequisites():
    if not COOKIES_PATH:
        if not os.path.isfile(os.path.join(HOME_DIR, "cookies.txt")):
            logger.error(f"Please provide a valid cookie file using the '--cookie' option.")
            return False
    else:
        if not os.path.isfile(COOKIES_PATH):
            logger.error(f"The provided cookie file path does not exist.")
            return False

    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except:
        logger.error("ffmpeg is not installed or not found in the system PATH.")
        return False
    
    try:
        subprocess.run([N_M3U8DL_RE_PATH, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except:
        logger.error(f"{N_M3U8DL_RE_PATH} is not installed or not found in the system PATH.")
        return False
    
    # Check for Shaka Packager (preferred for DRM content)
    try:
        subprocess.run([SHAKA_PACKAGER_PATH, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except:
        logger.warning(f"{SHAKA_PACKAGER_PATH} not found. DRM-protected videos may not work properly.")
    
    return True

def main():

    try:
        global course_url, key, cookie_path, COURSE_DIR, captions, max_concurrent_lectures, skip_captions, skip_assets, skip_lectures, skip_articles, skip_assignments, convert_to_srt, start_chapter, end_chapter, start_lecture, end_lecture, chapter_filter

        parser = argparse.ArgumentParser(description="Udemy Downloader By Joe - A powerful tool for downloading Udemy courses")
        parser.add_argument("--id", "-i", type=int, required=False, help="The ID of the Udemy course to download")
        parser.add_argument("--url", "-u", type=str, required=False, help="The URL of the Udemy course to download")
        parser.add_argument("--key", "-k", type=str, help="Key to decrypt the DRM-protected videos")
        parser.add_argument("--cookies", "-c", type=str, default="cookies.txt", help="Path to cookies.txt file")
        parser.add_argument("--load", "-l", help="Load course curriculum from file", action=LoadAction, const=True, nargs='?')
        parser.add_argument("--save", "-s", help="Save course curriculum to a file", action=LoadAction, const=True, nargs='?')
        parser.add_argument("--concurrent", "-cn", type=int, default=4, help="Maximum number of concurrent downloads")
        
        # parser.add_argument("--quality", "-q", type=str, help="Specify the quality of the videos to download.")
        parser.add_argument("--start-chapter", type=int, help="Start the download from the specified chapter")
        parser.add_argument("--start-lecture", type=int, help="Start the download from the specified lecture")
        parser.add_argument("--end-chapter", type=int, help="End the download at the specified chapter")
        parser.add_argument("--end-lecture", type=int, help="End the download at the specified lecture")
        parser.add_argument("--captions", type=str, help="Specify what captions to download. Separate multiple captions with commas")
        parser.add_argument("--srt", help="Convert the captions to srt format", action=LoadAction, const=True, nargs='?')
        
        parser.add_argument("--tree", help="Create a tree view of the course curriculum", action=LoadAction, nargs='?')

        parser.add_argument("--skip-captions", type=bool, default=False, help="Skip downloading captions", action=LoadAction, nargs='?')
        parser.add_argument("--skip-assets", type=bool, default=False, help="Skip downloading assets", action=LoadAction, nargs='?')
        parser.add_argument("--skip-lectures", type=bool, default=False, help="Skip downloading lectures", action=LoadAction, nargs='?')
        parser.add_argument("--skip-articles", type=bool, default=False, help="Skip downloading articles", action=LoadAction, nargs='?')
        parser.add_argument("--skip-assignments", type=bool, default=False, help="Skip downloading assignments", action=LoadAction, nargs='?')
        
        parser.add_argument("--chapter", type=str, help="Download specific chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').")
        
        # Cache management options
        parser.add_argument("--clear-cache", action="store_true", help="Clear download cache and restart from beginning")
        parser.add_argument("--show-cache", action="store_true", help="Show download cache status and exit")

        args = parser.parse_args()

        if len(sys.argv) == 1:
            print(parser.format_help())
            sys.exit(0)
        course_url = args.url or COURSE_LINK

        key = args.key or WIDEVINE_KEY

        if args.concurrent > 25:
            logger.warning("The maximum number of concurrent downloads is 25. The provided number of concurrent downloads will be capped to 25.")
            max_concurrent_lectures = 25
        elif args.concurrent < 1:
            logger.warning("The minimum number of concurrent downloads is 1. The provided number of concurrent downloads will be capped to 1.")
            max_concurrent_lectures = 1
        else:
            max_concurrent_lectures = args.concurrent

        if not course_url and not args.id:
            logger.error("You must provide either the course ID with '--id' or the course URL with '--url' (or set COURSE_LINK in .env) to proceed.")
            return
        elif course_url and args.id:
            logger.warning("Both course ID and URL provided. Prioritizing course ID over URL.")
        
        if key is not None and not ":" in key:
            logger.error("The provided Widevine key is either malformed or incorrect. Please check the key and try again.")
            return
        
        if args.cookies:
            cookie_path = args.cookies

        if not check_prerequisites():
            return
        
        udemy = Udemy()

        if args.id:
            course_id = args.id
        else:
            course_id = udemy.extract_course_id(course_url)
        
        # Handle cache management options
        if args.clear_cache:
            if course_id:
                cache = DownloadCache(course_id)
                cache.clear_cache()
                logger.info("Download cache cleared. Will restart from beginning.")
            else:
                logger.error("Cannot clear cache without course ID. Please provide --id or --url.")
                return
        
        if args.show_cache:
            if course_id:
                cache = DownloadCache(course_id)
                cache.print_progress_summary()
            else:
                logger.error("Cannot show cache without course ID. Please provide --id or --url.")
            return

        if args.captions:
            try:
                captions = args.captions.split(",")
            except:
                logger.error("Invalid captions provided. Captions should be separated by commas.")
        else:
            captions = ["en_US"]

        skip_captions = args.skip_captions
        skip_assets = args.skip_assets
        skip_lectures = args.skip_lectures
        skip_articles = args.skip_articles
        skip_assignments = args.skip_assignments

        course_info = udemy.fetch_course(course_id)
        COURSE_DIR = os.path.join(OUTPUT_DIR, remove_emojis_and_binary(sanitize_filename(course_info['title'])))

        try:
            logger.info(f"Course Title: {course_info['title']}")
        except UnicodeEncodeError:
            logger.info(f"Course Title: {remove_emojis_and_binary(course_info['title'])}")

        udemy.create_directory(os.path.join(COURSE_DIR))

        if args.load:
            if args.load is True and os.path.isfile(os.path.join(HOME_DIR, "course.json")):
                try:
                    course_curriculum = json.load(open(os.path.join(HOME_DIR, "course.json"), "r"))
                    logger.info(f"The course curriculum is successfully loaded from course.json")
                except json.JSONDecodeError:
                    logger.error("The course curriculum file provided is either malformed or corrupted.")
                    sys.exit(1)
            elif args.load:
                if os.path.isfile(args.load):
                    try:
                        course_curriculum = json.load(open(args.load, "r"))
                        logger.info(f"The course curriculum is successfully loaded from {args.load}")
                    except json.JSONDecodeError:
                        logger.error("The course curriculum file provided is either malformed or corrupted.")
                        sys.exit(1)
                else:
                    logger.error("The course curriculum file could not be located. Please verify the file path and ensure that the file exists.")
                    sys.exit(1)
            else:
                logger.error("Please provide the path to the course curriculum file.")
                sys.exit(1)
        else:
            try:
                course_curriculum = udemy.fetch_course_curriculum(course_id)
            except Exception as e:
                logger.critical(f"Unable to retrieve the course curriculum. {e}")
                sys.exit(1)

        if args.save:
            if args.save is True:
                if (os.path.isfile(os.path.join(HOME_DIR, "course.json"))):
                    logger.warning("Course curriculum file already exists. Overwriting the existing file.")
                with open(os.path.join(HOME_DIR, "course.json"), "w") as f:
                    json.dump(course_curriculum, f, indent=4)
                    logger.info(f"The course curriculum has been successfully saved to course.json")
            elif args.save:
                if (os.path.isfile(args.save)):
                    logger.warning("Course curriculum file already exists. Overwriting the existing file.")
                with open(args.save, "w") as f:
                    json.dump(course_curriculum, f, indent=4)
                    logger.info(f"The course curriculum has been successfully saved to {args.save}")

        if args.tree:
            root_tree = Tree(course_info['title'], style="green")
            udemy.build_curriculum_tree(course_curriculum, root_tree)
            rprint(root_tree)
            if args.tree is True:
                pass
            elif args.tree:
                if (os.path.isfile(args.tree)):
                    logger.warning("Course Curriculum Tree file already exists. Overwriting the existing file.")
                with open(args.tree, "w") as f:
                    rprint(root_tree, file=f)
                    logger.info(f"The course curriculum tree has been successfully saved to {args.tree}")

        if args.srt:
            convert_to_srt = True
        else:
            convert_to_srt = False
            
        if args.start_lecture:
            if args.start_chapter:
                start_chapter = args.start_chapter
                start_lecture = args.start_lecture
            else:
                logger.error("When using --start-lecture please provide --start-chapter")
                sys.exit(1)
        elif args.start_chapter:
            start_chapter = args.start_chapter
            start_lecture = 0
        else:
            start_chapter = 0
            start_lecture = 0

        if args.end_lecture:
            if args.end_chapter:
                end_chapter = args.end_chapter
                end_lecture = args.end_lecture
            elif args.end_chapter:
                logger.error("When using --end-lecture please provide --end-chapter")
                sys.exit(1)
        elif args.end_chapter:
            end_chapter = args.end_chapter
            end_lecture = 1000
        else:
            end_chapter = len(course_curriculum)
            end_lecture = 1000

        chapter_filter = None
        if args.chapter:
            chapter_filter = parse_chapter_filter(args.chapter)
            logger.info("Chapter filter applied: %s", sorted(chapter_filter))

        logger.info("The course download is starting. Please wait while the materials are being downloaded.")

        start_time = time.time()
        udemy.download_course(course_id, course_curriculum)
        end_time = time.time()

        elapsed_time = end_time - start_time
        
        logger.info(f"Download finished in {format_time(elapsed_time)}")

        logger.info("All course materials have been successfully downloaded.")    
        logger.info("Download Complete.")
    except KeyboardInterrupt:
        logger.warning("Process interrupted. Exiting")
        sys.exit(1)

if __name__ == "__main__":
    main()
