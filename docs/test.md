# Safe Check List

These checks do not download a course.

```powershell
python --version
ffmpeg -version
.\n_m3u8dl-re.exe --version
.\shaka-packager.exe --version
python -m unittest discover -s tests -v
```

Every command should finish without a red error.

To test your own setup later, use one small lesson you are allowed to access. Never test with somebody else's account or secret files.
