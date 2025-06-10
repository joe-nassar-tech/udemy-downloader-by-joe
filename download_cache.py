#!/usr/bin/env python3
"""
Download Cache System for Udemy Downloader By Joe
Tracks download progress and enables resume functionality
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

class DownloadCache:
    def __init__(self, course_id, cache_dir="cache"):
        self.course_id = str(course_id)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Create cache file path
        self.cache_file = self.cache_dir / f"course_{self.course_id}.json"
        
        # Load existing cache or create new one
        self.cache_data = self.load_cache()
    
    def load_cache(self):
        """Load existing cache data or create new cache"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                print(f"📂 Loaded download cache for course {self.course_id}")
                return cache_data
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"⚠️  Cache file corrupted, creating new cache")
                return self.create_new_cache()
        else:
            return self.create_new_cache()
    
    def create_new_cache(self):
        """Create new cache structure"""
        return {
            "course_id": self.course_id,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "total_downloads": 0,
            "completed_downloads": 0,
            "failed_downloads": 0,
            "downloads": {},
            "curriculum": None
        }
    
    def save_cache(self):
        """Save cache data to file"""
        self.cache_data["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Failed to save cache: {e}")
    
    def get_download_key(self, chapter_index, lecture_index, lecture_title):
        """Generate unique key for download tracking"""
        # Create a unique key based on chapter, lecture, and title
        key_string = f"{chapter_index}_{lecture_index}_{lecture_title}"
        return hashlib.md5(key_string.encode()).hexdigest()[:12]
    
    def is_download_completed(self, chapter_index, lecture_index, lecture_title, expected_path):
        """Check if download is already completed"""
        download_key = self.get_download_key(chapter_index, lecture_index, lecture_title)
        
        # Check cache record
        if download_key in self.cache_data["downloads"]:
            record = self.cache_data["downloads"][download_key]
            
            # Check if file actually exists and has reasonable size
            if os.path.exists(expected_path):
                file_size = os.path.getsize(expected_path)
                cached_size = record.get("file_size", 0)
                
                # If file exists and size matches (or is reasonable), consider it complete
                if file_size > 1024 and (cached_size == 0 or abs(file_size - cached_size) < 1024):
                    return True, record
        
        return False, None
    
    def mark_download_started(self, chapter_index, lecture_index, lecture_title, lecture_id, asset_type):
        """Mark download as started"""
        download_key = self.get_download_key(chapter_index, lecture_index, lecture_title)
        
        self.cache_data["downloads"][download_key] = {
            "chapter_index": chapter_index,
            "lecture_index": lecture_index,
            "lecture_title": lecture_title,
            "lecture_id": lecture_id,
            "asset_type": asset_type,
            "status": "started",
            "started_at": datetime.now().isoformat(),
            "file_size": 0,
            "file_path": "",
            "attempts": self.cache_data["downloads"].get(download_key, {}).get("attempts", 0) + 1
        }
        
        self.save_cache()
        return download_key
    
    def mark_download_completed(self, download_key, file_path, file_size=None):
        """Mark download as completed"""
        if download_key in self.cache_data["downloads"]:
            # Get actual file size if not provided
            if file_size is None and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
            
            self.cache_data["downloads"][download_key].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "file_path": str(file_path),
                "file_size": file_size or 0
            })
            
            self.cache_data["completed_downloads"] += 1
            self.save_cache()
    
    def mark_download_failed(self, download_key, error_message=""):
        """Mark download as failed"""
        if download_key in self.cache_data["downloads"]:
            self.cache_data["downloads"][download_key].update({
                "status": "failed",
                "failed_at": datetime.now().isoformat(),
                "error": error_message
            })
            
            self.cache_data["failed_downloads"] += 1
            self.save_cache()
    
    def get_download_summary(self):
        """Get download progress summary"""
        total = len(self.cache_data["downloads"])
        completed = len([d for d in self.cache_data["downloads"].values() if d["status"] == "completed"])
        failed = len([d for d in self.cache_data["downloads"].values() if d["status"] == "failed"])
        in_progress = total - completed - failed
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "completion_rate": (completed / total * 100) if total > 0 else 0
        }
    
    def get_failed_downloads(self):
        """Get list of failed downloads for retry"""
        return [
            (key, data) for key, data in self.cache_data["downloads"].items() 
            if data["status"] == "failed"
        ]
    
    def reset_failed_downloads(self):
        """Reset failed downloads to allow retry"""
        for key, data in self.cache_data["downloads"].items():
            if data["status"] == "failed":
                data["status"] = "pending"
                data.pop("failed_at", None)
                data.pop("error", None)
        
        self.cache_data["failed_downloads"] = 0
        self.save_cache()
    
    def save_curriculum(self, curriculum):
        """Save curriculum data to cache"""
        self.cache_data["curriculum"] = curriculum
        self.cache_data["total_downloads"] = self.count_total_lectures(curriculum)
        self.save_cache()
    
    def count_total_lectures(self, curriculum):
        """Count total lectures in curriculum"""
        total = 0
        for chapter in curriculum:
            if 'children' in chapter:
                total += len([item for item in chapter['children'] if item.get('_class') == 'lecture'])
        return total
    
    def print_progress_summary(self):
        """Print download progress summary"""
        summary = self.get_download_summary()
        
        print("=" * 60)
        print("📊 DOWNLOAD PROGRESS SUMMARY")
        print("=" * 60)
        print(f"📁 Course ID: {self.course_id}")
        print(f"📊 Total Downloads: {summary['total']}")
        print(f"✅ Completed: {summary['completed']}")
        print(f"❌ Failed: {summary['failed']}")
        print(f"⏳ In Progress: {summary['in_progress']}")
        print(f"📈 Completion Rate: {summary['completion_rate']:.1f}%")
        
        if summary['failed'] > 0:
            print(f"\n⚠️  {summary['failed']} downloads failed. They will be retried automatically.")
        
        if summary['completed'] > 0:
            print(f"🎯 {summary['completed']} downloads will be skipped (already completed).")
        
        print("=" * 60)
    
    def clear_cache(self):
        """Clear all cache data (force full re-download)"""
        if self.cache_file.exists():
            self.cache_file.unlink()
            print(f"🗑️  Cleared download cache for course {self.course_id}")
        self.cache_data = self.create_new_cache() 