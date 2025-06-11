# Udemy Downloader By Joe - Complete Testing Guide

This comprehensive testing guide will walk you through testing every feature of the Udemy Downloader By Joe, from basic setup to advanced functionality. Tests are organized from simplest to most complex.

## Table of Contents

1. [Prerequisites Testing](#prerequisites-testing)
2. [Authentication Testing](#authentication-testing)
3. [Basic Functionality Testing](#basic-functionality-testing)
4. [Cache System Testing](#cache-system-testing)
5. [Course ID Extraction Testing](#course-id-extraction-testing)
6. [Download Features Testing](#download-features-testing)
7. [Advanced Features Testing](#advanced-features-testing)
8. [DRM Content Testing](#drm-content-testing)
9. [Error Handling Testing](#error-handling-testing)
10. [Performance Testing](#performance-testing)
11. [Integration Testing](#integration-testing)

---

## Prerequisites Testing

### Test 1.1: Python Installation
**Objective**: Verify Python 3.8+ is properly installed

```bash
# Test Python version
python --version
# Expected: Python 3.8.x or higher

# Test pip functionality
pip --version
# Expected: pip version info

# Test package installation capability
pip install --dry-run requests
# Expected: No errors, shows what would be installed
```

**Expected Results**:
- ✅ Python version 3.8 or higher
- ✅ pip working correctly
- ✅ No permission or path issues

### Test 1.2: Dependencies Installation
**Objective**: Verify all Python dependencies install correctly

```bash
# Test requirements installation
pip install -r requirements.txt

# Verify specific packages
python -c "import requests; print('requests:', requests.__version__)"
python -c "import rich; print('rich:', rich.__version__)"
python -c "import pathvalidate; print('pathvalidate:', pathvalidate.__version__)"
python -c "from dotenv import load_dotenv; print('python-dotenv: OK')"
```

**Expected Results**:
- ✅ All packages install without errors
- ✅ Import statements work correctly
- ✅ Version numbers display properly

### Test 1.3: External Tools Testing
**Objective**: Verify FFmpeg and downloader tools are working

```bash
# Test FFmpeg
ffmpeg -version
# Expected: FFmpeg version and configuration info

# Test N_m3u8DL-RE
./n_m3u8dl-re --version
# or
n_m3u8dl-re.exe --version
# Expected: Tool version information

# Test Shaka Packager (optional for DRM)
./shaka-packager --version
# or
shaka-packager.exe --version
# Expected: Shaka Packager version info
```

**Expected Results**:
- ✅ FFmpeg shows version and build info
- ✅ N_m3u8DL-RE responds with version
- ✅ Shaka Packager available (for DRM testing)

---

## Authentication Testing

### Test 2.1: Cookie File Validation
**Objective**: Test different cookie formats and validation

#### JSON Format Testing
```bash
# Create test cookies.json
cat > test_cookies.json << EOF
[
  {
    "name": "access_token", 
    "value": "test_token_value",
    "domain": ".udemy.com"
  },
  {
    "name": "client_id",
    "value": "test_client_id", 
    "domain": ".udemy.com"
  }
]
EOF

# Test JSON validation
python -c "import json; print(json.load(open('test_cookies.json')))"
```

**Expected Results**:
- ✅ Valid JSON format loads without errors
- ✅ Required cookie fields present

#### Netscape Format Testing  
```bash
# Create test cookies.txt (Netscape format)
cat > test_cookies.txt << EOF
# Netscape HTTP Cookie File
.udemy.com	TRUE	/	FALSE	0	access_token	test_token_value
.udemy.com	TRUE	/	FALSE	0	client_id	test_client_id
EOF

# Test file format
file test_cookies.txt
head -n 3 test_cookies.txt
```

**Expected Results**:
- ✅ Proper Netscape format structure
- ✅ Tab-separated values
- ✅ Required domains and cookie names

### Test 2.2: Authentication Flow
**Objective**: Test authentication with real cookies

```bash
# Test with your real cookies (backup first!)
cp cookies.json cookies.json.backup

# Test basic authentication (dry run)
python get_course.py "https://www.udemy.com/course/any-free-course/"
```

**Expected Results**:
- ✅ No authentication errors
- ✅ Course ID extracted successfully
- ✅ No "permission denied" messages

---

## Basic Functionality Testing

### Test 3.1: Help and Version Information
**Objective**: Test basic command line interface

```bash
# Test help output
python main.py
python main.py --help

# Test course extractor help
python get_course.py --help

# Test cache manager help  
python cache_manager.py --help
```

**Expected Results**:
- ✅ Help text displays correctly
- ✅ All command line options shown
- ✅ No Python import errors

### Test 3.2: Environment Configuration
**Objective**: Test .env file loading and configuration

```bash
# Create test .env file
cat > .env.test << EOF
COOKIES_PATH=test_cookies.txt
OUTPUT_DIR=test_downloads
CONCURRENT_DOWNLOADS=2
SUBTITLE_LANG=en
EOF

# Test configuration loading
python -c "
from dotenv import load_dotenv
import os
load_dotenv('.env.test')
print('COOKIES_PATH:', os.getenv('COOKIES_PATH'))
print('OUTPUT_DIR:', os.getenv('OUTPUT_DIR'))
print('CONCURRENT_DOWNLOADS:', os.getenv('CONCURRENT_DOWNLOADS'))
"
```

**Expected Results**:
- ✅ Environment variables load correctly
- ✅ All expected values present
- ✅ No syntax errors in .env file

### Test 3.3: Directory Creation
**Objective**: Test automatic directory creation

```bash
# Test directory structure creation
python -c "
import os
from pathlib import Path

# Test cache directory
Path('test_cache').mkdir(exist_ok=True)
print('Cache dir created:', os.path.exists('test_cache'))

# Test output directory  
Path('test_output').mkdir(exist_ok=True)
print('Output dir created:', os.path.exists('test_output'))

# Cleanup
os.rmdir('test_cache')
os.rmdir('test_output')
"
```

**Expected Results**:
- ✅ Directories created successfully
- ✅ No permission errors
- ✅ Cleanup works properly

---

## Cache System Testing

### Test 4.1: Cache Creation and Loading
**Objective**: Test cache system initialization

```bash
# Test cache creation
python -c "
from download_cache import DownloadCache

# Create new cache
cache = DownloadCache('test_course_123', 'test_cache')
print('Cache created:', cache.course_id)
print('Cache file path:', cache.cache_file)
print('Cache data keys:', list(cache.cache_data.keys()))
"

# Verify cache file exists
ls -la test_cache/
cat test_cache/course_test_course_123.json
```

**Expected Results**:
- ✅ Cache file created in correct location
- ✅ JSON structure is valid
- ✅ Required fields present (course_id, created_at, downloads, etc.)

### Test 4.2: Download Progress Tracking  
**Objective**: Test download state management

```bash
# Test download tracking
python -c "
from download_cache import DownloadCache

cache = DownloadCache('test_course_456', 'test_cache')

# Test marking downloads
key1 = cache.mark_download_started(1, 1, 'Test Lecture 1', 12345, 'Video')
print('Download started:', key1)

cache.mark_download_completed(key1, '/test/path/lecture1.mp4', 1024000)
print('Download completed')

key2 = cache.mark_download_started(1, 2, 'Test Lecture 2', 12346, 'Video')
cache.mark_download_failed(key2, 'Network timeout')
print('Download failed')

# Check summary
summary = cache.get_download_summary()
print('Summary:', summary)
"
```

**Expected Results**:
- ✅ Downloads tracked with unique keys
- ✅ States update correctly (started → completed/failed)
- ✅ Summary shows accurate counts

### Test 4.3: Cache Persistence
**Objective**: Test cache survives application restarts

```bash
# Step 1: Create cache with data
python -c "
from download_cache import DownloadCache
cache = DownloadCache('persist_test', 'test_cache')
key = cache.mark_download_started(1, 1, 'Persistence Test', 999, 'Video')
cache.mark_download_completed(key, '/test/file.mp4', 5000000)
print('Cache created and saved')
"

# Step 2: Load cache in new instance
python -c "
from download_cache import DownloadCache
cache = DownloadCache('persist_test', 'test_cache')
summary = cache.get_download_summary()
print('Loaded cache summary:', summary)
print('Should show 1 completed download')
"
```

**Expected Results**:
- ✅ Cache data persists between instances
- ✅ Download states maintained correctly
- ✅ No data corruption

### Test 4.4: Cache Manager Utility
**Objective**: Test cache management tools

```bash
# Create some test caches first
python -c "
from download_cache import DownloadCache
for i in range(3):
    cache = DownloadCache(f'course_{1000+i}', 'test_cache')
    key = cache.mark_download_started(1, 1, f'Test Lecture {i}', 100+i, 'Video')
    if i == 0:
        cache.mark_download_completed(key, f'/test/lecture{i}.mp4', 1000000)
    elif i == 1:
        cache.mark_download_failed(key, 'Test failure')
print('Test caches created')
"

# Test cache manager commands
python cache_manager.py --list
python cache_manager.py --show course_1000
python cache_manager.py --show course_1001
python cache_manager.py --reset-failed course_1001
python cache_manager.py --clear course_1002
```

**Expected Results**:
- ✅ List shows all test caches
- ✅ Show displays detailed information
- ✅ Reset-failed changes failed status to pending
- ✅ Clear removes cache file

---

## Course ID Extraction Testing

### Test 5.1: URL Parsing
**Objective**: Test course ID extraction from various URL formats

```bash
# Test different URL formats
python get_course.py "https://www.udemy.com/course/test-course/"
python get_course.py "https://www.udemy.com/course/test-course/learn/"
python get_course.py "https://udemy.com/course/test-course"
python get_course.py "https://www.udemy.com/course/test-course/?utm_source=test"

# Test with course preview pages
python get_course.py "https://www.udemy.com/course/complete-python-bootcamp/"
```

**Expected Results**:
- ✅ Course IDs extracted correctly from all formats
- ✅ URL parameters ignored properly  
- ✅ No crashes on malformed URLs

### Test 5.2: Environment Variable Loading
**Objective**: Test default course URL from .env

```bash
# Add course URL to .env
echo "COURSE_LINK=https://www.udemy.com/course/default-test-course/" >> .env

# Test default loading
python get_course.py
```

**Expected Results**:
- ✅ Default course loaded from environment
- ✅ Course ID extracted from default URL

### Test 5.3: Error Handling
**Objective**: Test extraction with invalid URLs

```bash
# Test invalid URLs
python get_course.py "https://invalid-url.com"
python get_course.py "not-a-url"
python get_course.py "https://www.udemy.com/invalid-page/"
```

**Expected Results**:
- ✅ Graceful error messages
- ✅ No application crashes
- ✅ Clear instructions for user

---

## Download Features Testing

### Test 6.1: Basic Download Flow
**Objective**: Test complete download process with free course

> **Note**: Use only free courses or courses you own for testing

```bash
# Test with a free course (replace with actual free course ID)
python main.py --id FREE_COURSE_ID --concurrent 1 --skip-lectures --skip-captions

# This will test:
# - Authentication
# - Course curriculum retrieval  
# - Cache initialization
# - Directory creation
# - Asset downloading (without videos)
```

**Expected Results**:
- ✅ Authentication successful
- ✅ Course information retrieved
- ✅ Folder structure created
- ✅ Assets downloaded (if any)
- ✅ Cache tracking working

### Test 6.2: Selective Download Testing
**Objective**: Test chapter and lecture selection

```bash
# Test chapter selection
python main.py --id COURSE_ID --start-chapter 1 --end-chapter 1 --skip-lectures

# Test lecture range
python main.py --id COURSE_ID --start-chapter 1 --start-lecture 1 --end-chapter 1 --end-lecture 2 --skip-lectures

# Test chapter filter
python main.py --id COURSE_ID --chapter "1,3,5" --skip-lectures
```

**Expected Results**:
- ✅ Only specified chapters processed
- ✅ Lecture ranges respected
- ✅ Chapter filter works correctly

### Test 6.3: Content Type Selection
**Objective**: Test skipping different content types

```bash
# Test skipping videos
python main.py --id COURSE_ID --skip-lectures --concurrent 1

# Test skipping captions  
python main.py --id COURSE_ID --skip-captions --skip-lectures

# Test skipping articles
python main.py --id COURSE_ID --skip-articles --skip-lectures

# Test skipping assets
python main.py --id COURSE_ID --skip-assets --skip-lectures
```

**Expected Results**:
- ✅ Specified content types skipped
- ✅ Other content types processed normally
- ✅ Proper progress tracking

### Test 6.4: Subtitle Testing
**Objective**: Test subtitle download and conversion

```bash
# Test multiple languages
python main.py --id COURSE_ID --captions "en,es,fr" --skip-lectures --skip-articles

# Test SRT conversion
python main.py --id COURSE_ID --captions "en" --srt --skip-lectures --skip-articles

# Test caption-only download
python main.py --id COURSE_ID --skip-lectures --skip-articles --skip-assets
```

**Expected Results**:
- ✅ Multiple subtitle languages downloaded
- ✅ SRT conversion works correctly
- ✅ Subtitle files in proper locations

---

## Advanced Features Testing

### Test 7.1: Concurrent Download Testing
**Objective**: Test multi-threaded downloading

```bash
# Test different concurrency levels
python main.py --id COURSE_ID --concurrent 1 --skip-lectures
python main.py --id COURSE_ID --concurrent 4 --skip-lectures  
python main.py --id COURSE_ID --concurrent 8 --skip-lectures

# Test maximum concurrency (should cap at 25)
python main.py --id COURSE_ID --concurrent 30 --skip-lectures
```

**Expected Results**:
- ✅ Higher concurrency = faster downloads
- ✅ System handles concurrent requests properly
- ✅ Concurrency caps at maximum (25)
- ✅ No deadlocks or hangs

### Test 7.2: Curriculum Management
**Objective**: Test save/load curriculum features

```bash
# Test curriculum saving
python main.py --id COURSE_ID --save test_curriculum.json --tree test_tree.txt

# Verify files created
ls -la test_curriculum.json test_tree.txt
python -m json.tool test_curriculum.json > /dev/null
cat test_tree.txt

# Test curriculum loading
python main.py --load test_curriculum.json --skip-lectures --concurrent 1
```

**Expected Results**:
- ✅ Curriculum saves as valid JSON
- ✅ Tree file contains course structure
- ✅ Load works without re-fetching from server

### Test 7.3: Configuration Override Testing
**Objective**: Test command line overrides of .env settings

```bash
# Test cookie path override
python main.py --cookies custom_cookies.json --id COURSE_ID --skip-lectures

# Test output directory (if implemented)
# python main.py --output custom_output/ --id COURSE_ID --skip-lectures
```

**Expected Results**:
- ✅ Command line options override .env settings
- ✅ Custom paths work correctly
- ✅ No configuration conflicts

---

## DRM Content Testing

> **Warning**: Only test with courses you legitimately own and have purchased

### Test 8.1: Widevine Key Validation
**Objective**: Test DRM key format validation

```bash
# Test valid key format
python main.py --key "valid_key_id:valid_key_value" --id DRM_COURSE_ID --skip-lectures

# Test invalid key formats (should show errors)
python main.py --key "invalid_key_format" --id DRM_COURSE_ID --skip-lectures
python main.py --key "missing:colon:format" --id DRM_COURSE_ID --skip-lectures
```

**Expected Results**:
- ✅ Valid keys accepted
- ✅ Invalid keys rejected with clear error messages
- ✅ No application crashes on invalid keys

### Test 8.2: DRM Download Process
**Objective**: Test DRM-protected content download

```bash
# Test DRM download (with valid key)
python main.py --key "YOUR_VALID_KEY" --id DRM_COURSE_ID --concurrent 1

# This should test:
# - MPD stream detection
# - Widevine decryption
# - Video/audio merging
# - Shaka Packager integration
```

**Expected Results**:
- ✅ DRM content detected correctly
- ✅ Decryption process successful  
- ✅ Playable video files created
- ✅ No corrupted or empty files

### Test 8.3: DRM Error Handling
**Objective**: Test DRM-specific error scenarios

```bash
# Test without Shaka Packager (if removable)
# mv shaka-packager.exe shaka-packager.exe.backup
# python main.py --key "valid_key" --id DRM_COURSE_ID --concurrent 1

# Test with expired key
python main.py --key "expired_key_id:expired_key_value" --id DRM_COURSE_ID --concurrent 1

# Test DRM course without key
python main.py --id DRM_COURSE_ID --concurrent 1
```

**Expected Results**:
- ✅ Missing tools detected and reported
- ✅ Expired keys handled gracefully
- ✅ Warning shown for DRM without keys

---

## Error Handling Testing

### Test 9.1: Network Error Simulation
**Objective**: Test resilience to network issues

```bash
# Test with airplane mode or disconnected network
# (Disconnect network during download)
python main.py --id COURSE_ID --concurrent 1

# Reconnect network and test resume
python main.py --id COURSE_ID --concurrent 1
```

**Expected Results**:
- ✅ Network errors handled gracefully
- ✅ Downloads resume after reconnection
- ✅ Cache tracks failures correctly

### Test 9.2: Interrupted Download Testing  
**Objective**: Test recovery from process interruption

```bash
# Start download and interrupt with Ctrl+C
python main.py --id COURSE_ID --concurrent 2
# Press Ctrl+C after some downloads complete

# Resume download
python main.py --id COURSE_ID --concurrent 2
```

**Expected Results**:
- ✅ Graceful shutdown on interrupt
- ✅ Cache preserved during interruption
- ✅ Resume skips completed content

### Test 9.3: Invalid Course Testing
**Objective**: Test handling of invalid course IDs/URLs

```bash
# Test non-existent course ID
python main.py --id 999999999

# Test inaccessible course
python main.py --id PAID_COURSE_YOU_DONT_OWN

# Test course with authentication issues
python main.py --cookies invalid_cookies.json --id VALID_COURSE_ID
```

**Expected Results**:
- ✅ Clear error messages for non-existent courses
- ✅ Permission errors handled properly
- ✅ Authentication failures reported clearly

---

## Performance Testing

### Test 10.1: Memory Usage Testing
**Objective**: Monitor resource consumption

```bash
# Start memory monitoring (Linux/macOS)
# top -p $(pgrep -f "python main.py")

# Start download with monitoring
python main.py --id LARGE_COURSE_ID --concurrent 4

# Monitor for:
# - Memory leaks
# - CPU usage patterns  
# - Disk I/O efficiency
```

**Expected Results**:
- ✅ Memory usage stable (no continuous growth)
- ✅ CPU usage reasonable for concurrency level
- ✅ No excessive disk I/O

### Test 10.2: Large Course Testing
**Objective**: Test with courses having many lectures

```bash
# Test with 100+ lecture course
python main.py --id LARGE_COURSE_ID --concurrent 6 --skip-lectures

# Monitor:
# - Cache file size growth
# - Progress tracking accuracy
# - System stability
```

**Expected Results**:
- ✅ Cache handles large numbers of lectures
- ✅ Progress tracking remains accurate
- ✅ No performance degradation

### Test 10.3: Stress Testing
**Objective**: Test system limits

```bash
# Test maximum concurrency
python main.py --id COURSE_ID --concurrent 25

# Test rapid successive downloads
for i in {1..5}; do
  python main.py --id COURSE_ID_$i --concurrent 4 &
done
wait
```

**Expected Results**:
- ✅ High concurrency handled gracefully
- ✅ Multiple instances don't conflict
- ✅ System remains responsive

---

## Integration Testing

### Test 11.1: End-to-End Testing
**Objective**: Complete workflow testing

```bash
# Complete download workflow
python get_course.py "https://www.udemy.com/course/test-course/"
export COURSE_ID=$(python get_course.py "https://www.udemy.com/course/test-course/" | grep "Course ID" | cut -d: -f2 | tr -d ' ')

python main.py --id $COURSE_ID --save curriculum.json --tree tree.txt
python main.py --load curriculum.json --concurrent 2
python cache_manager.py --show $COURSE_ID
```

**Expected Results**:
- ✅ Complete workflow executes without errors
- ✅ All components work together properly
- ✅ Data flows correctly between tools

### Test 11.2: Cross-Platform Testing
**Objective**: Test on different operating systems

```bash
# Windows-specific tests
# Test with Windows paths and executables
python main.py --id COURSE_ID --concurrent 2

# Linux/macOS-specific tests  
# Test with Unix paths and permissions
chmod +x n_m3u8dl-re shaka-packager
python main.py --id COURSE_ID --concurrent 2
```

**Expected Results**:
- ✅ Path handling works on all platforms
- ✅ Executable permissions set correctly
- ✅ No platform-specific errors

### Test 11.3: Data Integrity Testing
**Objective**: Verify downloaded content integrity

```bash
# Download with verification
python main.py --id COURSE_ID --concurrent 2

# Verify file integrity
find courses/ -name "*.mp4" -exec ffmpeg -v error -i {} -f null - \;
find courses/ -name "*.srt" -exec file {} \;

# Check cache consistency
python cache_manager.py --show COURSE_ID
```

**Expected Results**:
- ✅ Video files are playable and not corrupted
- ✅ Subtitle files are valid text files
- ✅ Cache accurately reflects file system state

---

## Test Results Documentation

### Test Execution Log Template

```
# Test Execution Log
Date: [DATE]
Tester: [NAME]
Environment: [OS/Python Version]
Course Used: [COURSE_ID/NAME]

## Test Results Summary
- Prerequisites: ✅/❌
- Authentication: ✅/❌  
- Basic Functionality: ✅/❌
- Cache System: ✅/❌
- Course Extraction: ✅/❌
- Download Features: ✅/❌
- Advanced Features: ✅/❌
- DRM Testing: ✅/❌
- Error Handling: ✅/❌
- Performance: ✅/❌
- Integration: ✅/❌

## Issues Found
1. [Description of issue]
   - Steps to reproduce
   - Expected vs actual behavior
   - Severity: High/Medium/Low

## Recommendations
- [Suggestions for improvements]
- [Performance optimization opportunities]
- [User experience enhancements]
```

### Cleanup After Testing

```bash
# Clean up test files
rm -rf test_cache/
rm -rf test_downloads/
rm -f test_cookies.json test_cookies.txt
rm -f test_curriculum.json test_tree.txt
rm -f .env.test

# Reset any test configurations
git checkout -- .env cookies.json  # if modified
```

---

## Continuous Testing

### Automated Test Script

Create `run_tests.sh` for regular testing:

```bash
#!/bin/bash
# Automated test runner

echo "🚀 Starting Udemy Downloader Tests..."

# Prerequisites
echo "📋 Testing Prerequisites..."
python --version || exit 1
pip install -r requirements.txt || exit 1

# Basic functionality
echo "🔧 Testing Basic Functionality..."
python main.py --help > /dev/null || exit 1

# Cache system
echo "💾 Testing Cache System..."
python -c "from download_cache import DownloadCache; cache = DownloadCache('test', 'test_cache')" || exit 1

# Course extraction
echo "🎯 Testing Course Extraction..."
python get_course.py "https://www.udemy.com/course/test/" > /dev/null || exit 1

echo "✅ All basic tests passed!"
```

This comprehensive testing guide ensures every feature of your Udemy Downloader is thoroughly tested and working correctly! 🎯 