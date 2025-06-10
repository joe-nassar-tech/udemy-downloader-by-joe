#!/usr/bin/env python3
"""
Cache Manager for Udemy Downloader By Joe
Manage download cache files and view progress
"""

import sys
import argparse
from pathlib import Path
from download_cache import DownloadCache

def list_all_caches():
    """List all available cache files"""
    cache_dir = Path("cache")
    if not cache_dir.exists():
        print("❌ No cache directory found")
        return
    
    cache_files = list(cache_dir.glob("course_*.json"))
    if not cache_files:
        print("❌ No cache files found")
        return
    
    print("📁 Available Course Caches:")
    print("=" * 50)
    
    for cache_file in cache_files:
        course_id = cache_file.stem.replace("course_", "")
        cache = DownloadCache(course_id)
        summary = cache.get_download_summary()
        
        print(f"📚 Course ID: {course_id}")
        print(f"   ✅ Completed: {summary['completed']}")
        print(f"   ❌ Failed: {summary['failed']}")  
        print(f"   📈 Progress: {summary['completion_rate']:.1f}%")
        print("-" * 30)

def show_cache_details(course_id):
    """Show detailed cache information for a course"""
    cache = DownloadCache(course_id)
    cache.print_progress_summary()
    
    # Show failed downloads if any
    failed = cache.get_failed_downloads()
    if failed:
        print("\n❌ FAILED DOWNLOADS:")
        print("-" * 40)
        for key, data in failed:
            print(f"📄 {data['lecture_title']}")
            print(f"   Chapter: {data['chapter_index']}, Lecture: {data['lecture_index']}")
            print(f"   Error: {data.get('error', 'Unknown error')}")
            print(f"   Attempts: {data.get('attempts', 1)}")
            print()

def clear_cache(course_id):
    """Clear cache for a specific course"""
    cache = DownloadCache(course_id)
    cache.clear_cache()
    print(f"✅ Cache cleared for course {course_id}")

def reset_failed(course_id):
    """Reset failed downloads to retry them"""
    cache = DownloadCache(course_id)
    failed_count = len(cache.get_failed_downloads())
    
    if failed_count == 0:
        print("✅ No failed downloads to reset")
        return
    
    cache.reset_failed_downloads()
    print(f"🔄 Reset {failed_count} failed downloads for retry")

def main():
    parser = argparse.ArgumentParser(description="Cache Manager for Udemy Downloader By Joe")
    parser.add_argument("--list", "-l", action="store_true", help="List all course caches")
    parser.add_argument("--show", "-s", metavar="COURSE_ID", help="Show detailed cache info for course")
    parser.add_argument("--clear", "-c", metavar="COURSE_ID", help="Clear cache for course")
    parser.add_argument("--reset-failed", "-r", metavar="COURSE_ID", help="Reset failed downloads for retry")
    
    args = parser.parse_args()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    if args.list:
        list_all_caches()
    elif args.show:
        show_cache_details(args.show)
    elif args.clear:
        clear_cache(args.clear)
    elif args.reset_failed:
        reset_failed(args.reset_failed)

if __name__ == "__main__":
    main() 