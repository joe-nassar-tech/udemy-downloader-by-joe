# Udemy Downloader By Joe

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Educational](https://img.shields.io/badge/Purpose-Educational%20Only-orange.svg)

## ⚠️ IMPORTANT DISCLAIMERS

> **🎓 EDUCATIONAL PURPOSE ONLY**: This software is intended strictly for educational and research purposes. Users are solely responsible for complying with all applicable laws and terms of service.
>
> **⚖️ LEGAL RESPONSIBILITY**: By using this software, you acknowledge that you have read and agree to the terms in [LEGAL_DISCLAIMER.md](LEGAL_DISCLAIMER.md). Misuse may result in legal consequences.

---

A powerful, feature-rich Udemy course downloader that supports both regular and DRM-protected content. This tool allows you to download complete Udemy courses including videos, subtitles, articles, and supplementary materials for offline viewing.

## ✨ Features

- 📺 **Full Course Download**: Download complete courses with videos, subtitles, articles, and assets
- 🔐 **DRM Support**: Download DRM-protected videos using Widevine decryption
- ⚡ **Concurrent Downloads**: Multi-threaded downloading for faster speeds
- 🎯 **Selective Download**: Choose specific chapters, lectures, or ranges to download
- 📝 **Multiple Formats**: Support for subtitles in various languages and SRT conversion
- 🎨 **Beautiful Progress**: Rich progress bars and real-time download status
- ⚙️ **Environment Configuration**: Easy setup with `.env` file support
- 🌐 **Cookie Authentication**: Secure authentication using browser cookies

## 📋 Prerequisites

### Required Software

1. **Python 3.8+**
   - Download from [python.org](https://www.python.org/downloads/)
   - Make sure to add Python to PATH during installation

2. **FFmpeg**
   - Download from [ffmpeg.org](https://ffmpeg.org/download.html)
   - Add to system PATH
   - Or use package manager:
     ```bash
     # Windows (using Chocolatey)
     choco install ffmpeg
     
     # macOS (using Homebrew)
     brew install ffmpeg
     
     # Ubuntu/Debian
     sudo apt update && sudo apt install ffmpeg
     ```

3. **N_m3u8DL-RE**
   - Download the latest release from [GitHub](https://github.com/nilaoda/N_m3u8DL-RE/releases)
   - Place `n_m3u8dl-re.exe` in the project folder or add to PATH

4. **Shaka Packager** (for DRM content)
   - Download from [GitHub](https://github.com/shaka-project/shaka-packager/releases)
   - Place `shaka-packager.exe` in the project folder or add to PATH

## 🚀 Installation

### Method 1: Download Release (Recommended)
1. Download the latest release from the [Releases page](../../releases)
2. Extract the ZIP file to your desired location
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Method 2: Clone Repository
1. Clone this repository:
   ```bash
   git clone https://github.com/joe-nassar-tech/udemy-downloader-by-joe.git
   cd udemy-downloader-by-joe
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Python Dependencies
```
requests>=2.31.0
rich>=13.7.0
pathvalidate>=3.2.0
python-dotenv>=1.0.0
```

## ⚙️ Configuration

### 1. Cookie Setup (Required)

You need to provide your Udemy authentication cookies. Choose one method:

**Option A: JSON Format (Recommended)**
1. Install a browser extension like "Cookie Editor" or "EditThisCookie"
2. Log into Udemy in your browser
3. Export cookies as JSON format
4. Save as `cookies.json` in the project folder

**Option B: Netscape Format**
1. Use a tool to export cookies in Netscape format
2. Save as `cookies.txt` in the project folder

### 2. Environment Configuration

Create a `.env` file in the project folder with the following configuration:

```env
# Cookie file paths
COOKIES_PATH=cookies.txt
COOKIES_JSON_PATH=cookies.json

# Widevine key for DRM-protected content (optional)
WIDEVINE_KEY=your_widevine_key_here

# Download settings
OUTPUT_DIR=courses
CONCURRENT_DOWNLOADS=4
SUBTITLE_LANG=en

# Tool paths (if not in PATH)
N_M3U8DL_RE_PATH=n_m3u8dl-re.exe
SHAKA_PACKAGER_PATH=shaka-packager.exe

# Default course URL (optional)
COURSE_LINK=https://www.udemy.com/course/your-course/
```

### 3. Directory Structure
```
udemy-downloader-by-joe/
├── main.py                 # Main application
├── get_course.py          # Course ID extractor utility
├── .env                    # Environment configuration
├── cookies.json           # Your Udemy cookies (JSON format)
├── cookies.txt            # Auto-generated Netscape format
├── requirements.txt       # Python dependencies
├── n_m3u8dl-re.exe       # Video downloader tool
├── shaka-packager.exe    # DRM decryption tool
├── utils/                # Utility modules
├── courses/              # Downloaded courses (auto-created)
└── README.md             # This file
```

## 📖 Usage

### Course ID Extraction

First, extract the course ID from any Udemy course URL:

```bash
# Extract course ID from URL
python get_course.py "https://www.udemy.com/course/course-name/"

# Or use the default course from .env COURSE_LINK
python get_course.py
```

### Basic Usage

```bash
# Download by course URL
python main.py --url "https://www.udemy.com/course/course-name/"

# Download by course ID (recommended)
python main.py --id 1234567

# Download with custom concurrent downloads
python main.py --id 1234567 --concurrent 8
```

### Advanced Usage

```bash
# Download specific chapters
python main.py --id 1234567 --start-chapter 3 --end-chapter 5

# Download specific lectures within a chapter
python main.py --id 1234567 --start-chapter 2 --start-lecture 5 --end-chapter 2 --end-lecture 10

# Download with custom chapter selection
python main.py --id 1234567 --chapter "1,3-5,7,9-11"

# Download with DRM key
python main.py --url "https://www.udemy.com/course/course-name/" --key "your_widevine_key"

# Download with custom subtitles
python main.py --id 1234567 --captions "en,es,fr" --srt

# Skip certain content types
python main.py --id 1234567 --skip-articles --skip-assignments
```

### Command Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `--url`, `-u` | Course URL | `--url "https://www.udemy.com/course/name/"` |
| `--id`, `-i` | Course ID | `--id 1234567` |
| `--key`, `-k` | Widevine decryption key | `--key "key_id:key_value"` |
| `--cookies`, `-c` | Cookie file path | `--cookies "my_cookies.txt"` |
| `--concurrent`, `-cn` | Concurrent downloads (1-25) | `--concurrent 8` |
| `--start-chapter` | Start from chapter | `--start-chapter 3` |
| `--end-chapter` | End at chapter | `--end-chapter 5` |
| `--start-lecture` | Start from lecture | `--start-lecture 2` |
| `--end-lecture` | End at lecture | `--end-lecture 10` |
| `--chapter` | Specific chapters | `--chapter "1,3-5,7"` |
| `--captions` | Subtitle languages | `--captions "en,es,fr"` |
| `--srt` | Convert to SRT format | `--srt` |
| `--skip-captions` | Skip subtitles | `--skip-captions` |
| `--skip-articles` | Skip articles | `--skip-articles` |
| `--skip-assignments` | Skip assignments | `--skip-assignments` |
| `--save` | Save curriculum to file | `--save curriculum.json` |
| `--load` | Load curriculum from file | `--load curriculum.json` |
| `--tree` | Show course tree | `--tree` |

## 🔧 DRM Content Support

For DRM-protected courses, you need a Widevine decryption key:

1. **Obtain Widevine Key**: Use tools like `yt-dlp` with `--allow-unplayable-formats` or browser extensions
2. **Set in Environment**: Add to `.env` file as `WIDEVINE_KEY=key_id:key_value`
3. **Command Line**: Use `--key "key_id:key_value"`

The key format should be: `key_id:key_value` (colon-separated)

## 📁 Output Structure

Downloaded courses are organized as follows:
```
courses/
└── Course Name/
    ├── 01. Chapter Name/
    │   ├── 01. Lecture Title.mp4
    │   ├── 02. Another Lecture.mp4
    │   ├── subtitles/
    │   │   ├── 01. Lecture Title.en.vtt
    │   │   └── 01. Lecture Title.es.vtt
    │   └── resources/
    │       ├── assignment.pdf
    │       └── source-code.zip
    └── 02. Next Chapter/
        └── ...
```

## 🎯 Examples

### Download Complete Course
```bash
python main.py --url "https://www.udemy.com/course/python-bootcamp/"
```

### Download Specific Chapters with Subtitles
```bash
python main.py --id 1234567 --chapter "1,3-5" --captions "en,es" --srt
```

### Download DRM Course with High Concurrency
```bash
python main.py --url "https://www.udemy.com/course/advanced-react/" --key "key_id:key_value" --concurrent 10
```

### Download and Save Curriculum for Later
```bash
python main.py --id 1234567 --save course_curriculum.json --tree course_tree.txt
```

## 🔍 Troubleshooting

### Common Issues

1. **Authentication Error**
   - Ensure cookies are fresh (login to Udemy recently)
   - Check cookie format (JSON or Netscape)
   - Verify cookie file path in `.env`

2. **DRM Videos Won't Play**
   - Verify Widevine key format: `key_id:key_value`
   - Ensure Shaka Packager is installed and in PATH
   - Check that the key is not expired

3. **Download Failures**
   - Check internet connection
   - Reduce concurrent downloads: `--concurrent 2`
   - Verify FFmpeg installation
   - Check course accessibility (enrolled/free)

4. **Missing Dependencies**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

5. **Path Issues (Windows)**
   - Use quotes around paths with spaces
   - Check that tools are in PATH or `.env` paths are correct

### Performance Tips

- **Optimal Concurrency**: Start with 4, increase gradually
- **Network**: Use wired connection for stability
- **Storage**: Ensure sufficient disk space
- **System**: Close unnecessary applications during download

## 📄 License

This project is for educational purposes only. Please respect Udemy's Terms of Service and only download courses you have legitimate access to.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## ⚠️ Disclaimer

This tool is intended for personal use only. Users are responsible for complying with Udemy's Terms of Service and applicable laws. The developers assume no responsibility for misuse of this tool.

---

**Created by Joe** - A powerful tool for offline learning 📚
