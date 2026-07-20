# Helping the Project

Thank you for helping!

## Before you share a bug

1. Try the smallest command that shows the problem.
2. Read [Troubleshooting](TROUBLESHOOTING.md).
3. Remove private things from your message.

Safe bug report:

```text
Command: python main.py --id 123456 --start-chapter 1 --end-chapter 1
Error: DASH downloader exited with code 1
Tool version: N_m3u8DL-RE 0.3.0
```

Never include real cookies, account names, video URLs, DRM keys, or personal data.

## Before you change code

Run the offline checks:

```powershell
python -m py_compile main.py download_cache.py
python -m unittest discover -s tests -v
```

Please keep messages small, friendly, and easy to understand.
