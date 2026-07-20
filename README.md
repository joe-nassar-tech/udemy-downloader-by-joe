# Course Downloader

This is a small helper program for saving course materials you are allowed to download.

Think of it like a backpack. You give it your course number, and it puts your allowed videos, articles, captions, and files into the `courses` folder.

> Only use this with courses you own or are allowed to save. Do not share your cookies or secret keys.

## Tiny quick start

1. Install **Python 3.10 or newer**.
2. Open PowerShell in this folder.
3. Install the Python pieces:

```powershell
python -m pip install -r requirements.txt
```

4. Copy the fake settings file:

```powershell
Copy-Item .env.example .env
```

5. Put your own login cookies in `cookies.json`. Start by copying the safe example:

```powershell
Copy-Item cookies.json.example cookies.json
```

6. Add your real cookie values. Never paste them into chat, GitHub, or screenshots.
7. Download one small part first:

```powershell
python main.py --id 123456 --start-chapter 1 --end-chapter 1
```

The number `123456` is only pretend. Use your own course ID.

## What you need

| Thing | Why you need it |
|---|---|
| Python | Runs this program. |
| FFmpeg | Joins video and sound. |
| N_m3u8DL-RE | Saves video streams. |
| Shaka Packager | Needed only when a course provider gives you a lawful decryption key. |
| Your own cookies | Lets the course website know it is you. |

Read [the setup guide](docs/documentation.md) for friendly step-by-step help.

## Common commands

```powershell
# Download a course by its number
python main.py --id 123456

# Download only chapters 1 and 2
python main.py --id 123456 --start-chapter 1 --end-chapter 2

# Download one lecture
python main.py --id 123456 --start-chapter 1 --start-lecture 1 --end-chapter 1 --end-lecture 1

# See the saved-progress list
python main.py --id 123456 --show-cache

# Forget saved progress (this does not delete finished files)
python main.py --id 123456 --clear-cache
```

## Every command and flag

Start every download command with:

```powershell
python main.py
```

Then add one or more little switches called **flags**. A flag starts with `--`.

| Flag | Short name | What it means in simple words | Example |
|---|---|---|---|
| `--id NUMBER` | `-i` | Download the course with this number. | `--id 123456` |
| `--url URL` | `-u` | Use a course web address instead of a number. | `--url "https://www.udemy.com/course/example-course/"` |
| `--cookies FILE` | `-c` | Use this cookie file instead of `cookies.txt`. | `--cookies my-cookies.txt` |
| `--concurrent NUMBER` | `-cn` | Download this many lessons at one time. Start with `2`. | `--concurrent 2` |
| `--start-chapter NUMBER` | — | Start at this chapter. | `--start-chapter 2` |
| `--end-chapter NUMBER` | — | Stop after this chapter. | `--end-chapter 4` |
| `--start-lecture NUMBER` | — | Start at this lesson inside the starting chapter. Use `--start-chapter` too. | `--start-chapter 1 --start-lecture 2` |
| `--end-lecture NUMBER` | — | Stop at this lesson inside the ending chapter. Use `--end-chapter` too. | `--end-chapter 1 --end-lecture 5` |
| `--chapter LIST` | — | Pick chapters. Commas mean “and”; `-` means “through.” | `--chapter "1,3-5"` |
| `--captions LIST` | — | Save captions for these language names. | `--captions en_US` |
| `--srt` | — | Turn VTT captions into SRT captions. | `--captions en_US --srt` |
| `--skip-captions` | — | Do not save captions. | `--skip-captions` |
| `--skip-assets` | — | Do not save extra files, such as PDFs. | `--skip-assets` |
| `--skip-lectures` | — | Do not save video lessons. | `--skip-lectures` |
| `--skip-articles` | — | Do not save written lessons. | `--skip-articles` |
| `--skip-assignments` | — | Ask the program to skip assignments. | `--skip-assignments` |
| `--save [FILE]` | `-s` | Save the course list to a JSON file. No file name means `course.json`. | `--save my-course.json` |
| `--load [FILE]` | `-l` | Use a saved course list. No file name means `course.json`. | `--load my-course.json` |
| `--tree [FILE]` | — | Show the course as a little tree. You may also save the tree to a file. | `--tree course-tree.txt` |
| `--show-cache` | — | Show what the program remembers as finished or failed. | `--id 123456 --show-cache` |
| `--clear-cache` | — | Forget saved progress for one course. Finished video files stay on your computer. | `--id 123456 --clear-cache` |
| `--key VALUE` | `-k` | Provide lawful authorization given by the content provider for protected material. Keep it private. | `--key "PROVIDER_GIVEN_VALUE"` |

### Copy-and-paste examples

```powershell
# One whole course
python main.py --id 123456

# Only chapter 1
python main.py --id 123456 --start-chapter 1 --end-chapter 1

# Chapters 1, 3, 4, and 5
python main.py --id 123456 --chapter "1,3-5"

# Only captions, no videos
python main.py --id 123456 --skip-lectures --captions en_US

# Look at saved progress
python main.py --id 123456 --show-cache
```

## Where are my files?

Look in:

```text
courses\Your Course Name\
```

## Help pages

- [Setup and beginner guide](docs/documentation.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Safe cookie example](cookies.json.example)
- [Configuration example](.env.example)
- [Legal and safety rules](docs/LEGAL_DISCLAIMER.md)
- [How to help improve the project](docs/CONTRIBUTING.md)

## A note about protected videos

Some videos have a lock called DRM. This program can only process such material when you have a valid, lawful decryption key supplied through an authorized route. A key can be different for different videos. If a protected video does not work, use the course provider's official offline feature or ask its support team/instructor for help. Do not try to extract, guess, or share keys.

## License

See [LICENSE](LICENSE).
