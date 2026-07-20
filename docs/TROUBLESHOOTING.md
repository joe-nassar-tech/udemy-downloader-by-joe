# Troubleshooting: Little Problems and Big Problems

Do not worry. Errors are clues. Read the first red line and the nearby `DEBUG:` lines.

## `Download init file failed`

**What it means:** The video helper could not fetch the first tiny piece of a DASH video.

**What to do:**

1. Update to the current project code.
2. Sign in again and refresh your own cookies.
3. Try one lesson again.
4. Check that `n_m3u8dl-re.exe` is beside `main.py`.

The program now keeps the original video address so relative video pieces can be found.

## `N_m3u8DL-RE exited with code 1`

**What it means:** The video helper stopped.

**What to do:** Look directly above the error for `DEBUG: DASH downloader failed` or `DEBUG: N_m3u8DL-RE failed`.

- If it says `Download init file failed`, refresh login cookies and check the helper version.
- If it says access denied, sign in again and use your own course account.
- If it says a tool is missing, install the named tool and run its `--version` command.

## `DASH downloader completed but no playable output file was found`

**What it means:** The helper said it finished, but no usable video was made.

**What to do:** Check that FFmpeg is installed with `ffmpeg -version`. Then retry one lesson and read the `DEBUG:` output.

## Locked or DRM-protected video fails

**What it means:** The provider protected the video. A different video can require different authorization.

**What to do:** Use the provider's official download/offline option or ask the provider/instructor for help. Do not extract, guess, or share DRM keys.

## `Authentication setup failed`

**What it means:** The program could not read your cookie file.

**What to do:**

1. Make sure `cookies.txt` or `cookies.json` is in the project folder.
2. Make sure it belongs to your own account.
3. Copy `cookies.json.example` again if you need to see the shape of the JSON file.
4. Sign in again and export fresh cookies.

## `The provided cookie file could not be read`

**What it means:** `cookies.txt` is not Netscape cookie format.

**What to do:** Export it again in Netscape `cookies.txt` format, or use `cookies.json` with the example shape.

## `ffmpeg is not installed`

**What to do:** Install FFmpeg and make sure `ffmpeg -version` works in a new PowerShell window.

## `n_m3u8dl-re.exe is not installed`

**What to do:** Put `n_m3u8dl-re.exe` next to `main.py`, then run:

```powershell
.\n_m3u8dl-re.exe --version
```

## Cache says a file is complete, but the file is missing

**What to do:** Clear saved progress, then retry:

```powershell
python main.py --id 123456 --clear-cache
python main.py --id 123456 --start-chapter 1 --end-chapter 1
```

## `Cache was corrupt`

**What it means:** The old progress file was damaged. The program saves a copy with `.corrupt-YYYYMMDD...` in the `cache` folder and starts a fresh one.

## `Expected output missing`

**What it means:** A helper stopped without making the final file.

**What to do:** Read the `DEBUG:` lines above it. The item is marked failed and will be retried next time.

## I want to ask for help

Share these safe things:

- The command you typed.
- The red error line.
- The nearby `DEBUG:` lines.
- Your Python and helper-tool version numbers.

Never share cookies, passwords, account details, download URLs, or DRM keys.
