# Friendly Setup Guide

We will make the program ready one small step at a time.

## Step 1: Open the folder

Open PowerShell in the project folder:

```powershell
cd C:\Users\YourName\Desktop\udemy-downloader-by-joe
```

## Step 2: Install Python packages

```powershell
python -m pip install -r requirements.txt
```

## Step 3: Put the helper tools beside `main.py`

Put these files in the main project folder:

```text
ffmpeg.exe                 (available on your PATH)
n_m3u8dl-re.exe
shaka-packager.exe         (only for protected material with lawful authorization)
```

Try this tiny check:

```powershell
.\n_m3u8dl-re.exe --version
.\shaka-packager.exe --version
ffmpeg -version
```

Each command should print a version number.

## Step 4: Make your settings file

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor. The fake values are only examples. Leave `WIDEVINE_KEY` empty unless a provider has lawfully given you a key.

## Step 5: Add your own cookies

Cookies are tiny login tickets from your browser. They are private, like a house key.

1. Sign in to the course website in your own browser.
2. Export **your own** session cookies in Netscape `cookies.txt` format using a trusted local cookie-export method.
3. Save that file as `cookies.txt` in this project folder.

**Tip:** You can use this Firefox extension to export cookies easily: https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/

Or use JSON:

```powershell
Copy-Item cookies.json.example cookies.json
```

Replace the pretend values inside `cookies.json` with your own exported values. When `cookies.txt` is missing, the program makes it from `cookies.json`.

Never send either cookie file to anyone. They can let another person use your account.

## Step 6: Get the Widevine key (for DRM-protected videos)

Some videos have a DRM lock. To unlock them, you need a decryption key.

1. Open Firefox and go to your course.
2. Play any video lesson.
3. Install this extension: https://addons.mozilla.org/en-US/firefox/addon/widevine-l3-decrypter/
4. Click the extension icon in your toolbar.
5. Click the **Guess** button.
6. Copy the key that appears in the input box.
7. Open your `.env` file and paste the key like this:

```text
WIDEVINE_KEY=your_copied_key_here
```

Keep this key secret—it is like a password.

**Note:** The extension may fail sometimes. If it does not work, retry many times until you get the key.

Different videos may have different keys. If a related video fails to download, repeat these steps to get a new key for that video.

Or use any other lawful method you know to obtain the key.

## Step 7: Find a course number

Run:

```powershell
python get_course.py "https://www.udemy.com/course/example-course/"
```

Then copy the number it prints.

## Step 8: Try one small download

```powershell
python main.py --id 123456 --start-chapter 1 --end-chapter 1
```

Use your own course number instead of `123456`.

## Command cheat sheet

| You want to…                  | Type this                                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| Download everything           | `python main.py --id 123456`                                                                     |
| Download chapters 2 through 4 | `python main.py --id 123456 --start-chapter 2 --end-chapter 4`                                   |
| Download one lesson           | `python main.py --id 123456 --start-chapter 1 --start-lecture 2 --end-chapter 1 --end-lecture 2` |
| Skip captions                 | `python main.py --id 123456 --skip-captions`                                                     |
| Skip extra files              | `python main.py --id 123456 --skip-assets`                                                       |
| Save captions as SRT          | `python main.py --id 123456 --captions en_US --srt`                                              |
| See progress                  | `python main.py --id 123456 --show-cache`                                                        |
| Forget progress               | `python main.py --id 123456 --clear-cache`                                                       |

## Every flag explained

A **flag** is a tiny instruction that starts with `--`. Put flags after `python main.py`.

| Flag                     | Short name | Simple meaning                                                                | Example                                                |
| ------------------------ | ---------- | ----------------------------------------------------------------------------- | ------------------------------------------------------ |
| `--id NUMBER`            | `-i`       | Your course number.                                                           | `--id 123456`                                          |
| `--url URL`              | `-u`       | Your course web address.                                                      | `--url "https://www.udemy.com/course/example-course/"` |
| `--cookies FILE`         | `-c`       | Choose a cookie file.                                                         | `--cookies my-cookies.txt`                             |
| `--key VALUE`            | `-k`       | Lawful provider-supplied authorization for protected content. Keep it secret. | `--key "PROVIDER_GIVEN_VALUE"`                         |
| `--concurrent NUMBER`    | `-cn`      | Number of lessons to do at the same time.                                     | `--concurrent 2`                                       |
| `--start-chapter NUMBER` | —          | First chapter to download.                                                    | `--start-chapter 2`                                    |
| `--end-chapter NUMBER`   | —          | Last chapter to download.                                                     | `--end-chapter 4`                                      |
| `--start-lecture NUMBER` | —          | First lesson in the first chapter. Needs `--start-chapter`.                   | `--start-chapter 1 --start-lecture 2`                  |
| `--end-lecture NUMBER`   | —          | Last lesson in the last chapter. Needs `--end-chapter`.                       | `--end-chapter 1 --end-lecture 5`                      |
| `--chapter LIST`         | —          | Pick chapters with commas and ranges.                                         | `--chapter "1,3-5"`                                    |
| `--captions LIST`        | —          | Pick caption languages.                                                       | `--captions en_US`                                     |
| `--srt`                  | —          | Make SRT subtitle files.                                                      | `--captions en_US --srt`                               |
| `--skip-captions`        | —          | Do not save captions.                                                         | `--skip-captions`                                      |
| `--skip-assets`          | —          | Do not save extra files.                                                      | `--skip-assets`                                        |
| `--skip-lectures`        | —          | Do not save videos.                                                           | `--skip-lectures`                                      |
| `--skip-articles`        | —          | Do not save written lessons.                                                  | `--skip-articles`                                      |
| `--skip-assignments`     | —          | Skip assignments.                                                             | `--skip-assignments`                                   |
| `--save [FILE]`          | `-s`       | Save the course list for later.                                               | `--save course-list.json`                              |
| `--load [FILE]`          | `-l`       | Use a saved course list.                                                      | `--load course-list.json`                              |
| `--tree [FILE]`          | —          | Show or save a chapter-and-lesson tree.                                       | `--tree tree.txt`                                      |
| `--show-cache`           | —          | Show saved progress and stop.                                                 | `--id 123456 --show-cache`                             |
| `--clear-cache`          | —          | Forget saved progress and stop.                                               | `--id 123456 --clear-cache`                            |

## Protected videos

DRM is a lock on some videos. Different videos may use different authorization. If a locked video fails, the helpful next step is the official offline feature or contacting the provider. This guide does not explain how to extract, guess, or bypass DRM keys.

## When you see an error

Open [Troubleshooting](TROUBLESHOOTING.md). Copy the error words, but hide cookies, passwords, and keys first.
