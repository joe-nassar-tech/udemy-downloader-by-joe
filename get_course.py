#!/usr/bin/env python3
"""
Udemy Course ID Extractor
Extract course ID from Udemy course URLs with browser-like headers and fallback methods
"""

import re
import requests
import sys
import argparse
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}


def extract_course_id_from_url(course_url):
    """Extract course ID from Udemy course URL using regex and HTTP headers."""
    try:
        print(f"🔍 Fetching course page: {course_url}")

        # Clean URL - remove fragments and query parameters
        parsed_url = urlparse(course_url)
        clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        # Try to load cookies if available for private/enrolled course landing pages
        cookies_txt = os.getenv("COOKIES_PATH", "cookies.txt")
        if os.path.isfile(cookies_txt):
            try:
                import http.cookiejar as cookielib
                jar = cookielib.MozillaCookieJar(cookies_txt)
                jar.load()
                session.cookies = jar
            except Exception:
                pass

        response = session.get(clean_url, timeout=15)
        response.raise_for_status()

        content = response.text

        # Look for course ID in meta tags and page content
        meta_patterns = [
            r'<meta\s+property="og:image"\s+content="[^"]*\/(\d+)_[^"]*"',
            r'<meta\s+property="og:url"\s+content="[^"]*\/course\/[^"]*\/(\d+)\/"',
            r'"course_id":\s*(\d+)',
            r'"id":\s*(\d+).*?"_class":\s*"course"',
            r'data-course-id="(\d+)"',
            r'udemy\.com\/course\/.*?\/(\d{6,})',
        ]

        for pattern in meta_patterns:
            match = re.search(pattern, content)
            if match:
                course_id = match.group(1)
                return course_id

        # Fallback: Try to extract from URL structure directly
        url_pattern = r'/course/[^/]+.*?(\d{6,})'
        url_match = re.search(url_pattern, course_url)
        if url_match:
            course_id = url_match.group(1)
            return course_id

        return None

    except requests.RequestException as e:
        print(f"❌ Error fetching course page: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None


def clean_url(url):
    """Clean URL and handle different URL formats"""
    # Remove everything after #
    clean = url.split('#')[0]

    # Handle lecture URLs - extract base course URL
    lecture_match = re.search(r'(https://www\.udemy\.com/course/[^/]+)/', clean)
    if lecture_match and '/learn/' in clean:
        print("📝 Detected lecture URL, extracting course URL...")
        return lecture_match.group(1) + '/'

    # Ensure URL has trailing slash
    if not clean.endswith('/'):
        clean += '/'

    return clean


def main():
    parser = argparse.ArgumentParser(description="Extract Udemy Course ID")
    parser.add_argument("url", nargs='?', help="Udemy course URL (overrides .env COURSE_LINK)")

    args = parser.parse_args()

    # Get URL from command line argument or .env file
    course_url = args.url or os.getenv('COURSE_LINK')

    if not course_url:
        print("❌ No course URL provided!")
        print("💡 Either:")
        print("   1. Set COURSE_LINK in .env file")
        print("   2. Pass URL as argument: python get_course.py <url>")
        sys.exit(1)

    # Validate URL
    if 'udemy.com' not in course_url:
        print("❌ Invalid Udemy URL")
        sys.exit(1)

    # Clean and prepare URL
    course_url = clean_url(course_url)

    print("=" * 60)
    print("🎯 UDEMY COURSE ID EXTRACTOR")
    print("=" * 60)

    if args.url:
        print("📝 Using URL from command line")
    else:
        print("📝 Using URL from .env COURSE_LINK")

    print(f"🔗 URL: {course_url}")
    print("-" * 60)

    # Extract course ID
    course_id = extract_course_id_from_url(course_url)

    if course_id:
        print("-" * 60)
        print(f"✅ SUCCESS! Course ID: {course_id}")
        print("=" * 60)
        print("💡 Usage Examples:")
        print(f"   python main.py --id {course_id}")
        print(f"   python main.py --id {course_id} --chapter 1-5")
        print(f"   python main.py --id {course_id} --quality 1080p")
        print(f"   python main.py --id {course_id} --concurrent 4")
        print("=" * 60)
    else:
        print("❌ Failed to extract course ID")
        print("\n💡 Manual methods:")
        print("1. Check browser developer tools (F12 → Console)")
        print("2. View page source and search for 'course_id'")
        print("3. Look in Network tab for API calls")
        sys.exit(1)


if __name__ == "__main__":
    main()
