import os
import re
import shutil
import subprocess
import requests
from urllib.parse import urlparse
from constants import remove_emojis_and_binary, timestamp_to_seconds

def download_and_merge_mpd(mpd_file_url, download_folder_path, title_of_output_mp4, length, key, task_id, progress):
    progress.update(task_id,  description=f"Downloading Stream {remove_emojis_and_binary(title_of_output_mp4)}", completed=0)
    
    mpd_filename = os.path.basename(urlparse(mpd_file_url).path)
    mpd_file_path = os.path.join(download_folder_path, mpd_filename)

    response = requests.get(mpd_file_url)
    response.raise_for_status()

    with open(mpd_file_path, 'wb') as file:
        file.write(response.content)

    process_mpd(mpd_file_path, download_folder_path, title_of_output_mp4, length, key, task_id, progress)

def process_mpd(mpd_file_path, download_folder_path, output_file_name, length, key, task_id, progress):
    print(f"DEBUG: Key value: {key[:20] + '...' if key and len(key) > 20 else key}")
    
    # Base command for n_m3u8dl-re
    nm3u8dl_command = (
        f"n_m3u8dl-re \"{mpd_file_path}\" --save-dir \"{download_folder_path}\" "
        f"--save-name \"{output_file_name}.mp4\" --auto-select --concurrent-download "
        f"--del-after-done --no-log --tmp-dir \"{download_folder_path}\" "
        f"--log-level ERROR"
    )
    
    # Add DRM decryption if key is provided (use Shaka Packager for DRM content)
    if key:
        packager_path = os.path.abspath("shaka-packager.exe")
        nm3u8dl_command += (
            f" --key {key} --decryption-engine SHAKA_PACKAGER "
            f"--decryption-binary-path \"{packager_path}\" -mt -M format=mkv"
        )
    
    print(f"DEBUG: Running command: {nm3u8dl_command}")
    
    pattern = re.compile(r'(\d+\.\d+%)')
    process_nm3u8dl = subprocess.Popen(
        nm3u8dl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    progress.update(task_id,  description=f"Merging segments {remove_emojis_and_binary(output_file_name)}", completed=0)
    
    while True:
        output = process_nm3u8dl.stdout.readline()
        if output == '' and process_nm3u8dl.poll() is not None:
            break
        if output:
            stripped_output = output.strip().replace(' ', '')
        if stripped_output.startswith('Vid'):
            matches = pattern.findall(output)
            if matches:
                first_percentage = float(matches[0].replace('%', ''))
                if first_percentage < 100.0:
                    progress.update(task_id,  completed=first_percentage)
                else:
                    progress.update(task_id,  completed=99)

    stdout_nm3u8dl, stderr_nm3u8dl = process_nm3u8dl.communicate()

    print(f"DEBUG: n_m3u8dl-re return code: {process_nm3u8dl.returncode}")
    print(f"DEBUG: n_m3u8dl-re stdout: {stdout_nm3u8dl[:500] if stdout_nm3u8dl else 'None'}")
    print(f"DEBUG: n_m3u8dl-re stderr: {stderr_nm3u8dl[:500] if stderr_nm3u8dl else 'None'}")

    if stderr_nm3u8dl or process_nm3u8dl.returncode != 0:
        progress.console.log(f"[red]Error Downloading Segments {remove_emojis_and_binary(output_file_name)}[/red] ✕")
        progress.remove_task(task_id)
        return

    files = os.listdir(download_folder_path)
    print(f"DEBUG: Files in download folder: {files}")
    mp4_files = [f for f in files if f.endswith('.mp4')]
    m4a_files = [f for f in files if f.endswith('.m4a')]
    mkv_files = [f for f in files if f.endswith('.mkv') and ('MUX' in f or output_file_name in f)]

    # Check for MKV files (Shaka Packager output) first
    if mkv_files:
        # Use the MKV file and convert it to MP4 with proper audio/video
        mkv_path = os.path.join(download_folder_path, mkv_files[0])
        print(f"DEBUG: Found MKV file: {mkv_files[0]}, size: {os.path.getsize(mkv_path)} bytes")
        
        output_path = os.path.join(os.path.dirname(download_folder_path), f"{output_file_name}.mp4")
        
        # Convert MKV to MP4 using ffmpeg to ensure proper audio/video merge
        ffmpeg_command = (
            f"ffmpeg -loglevel error -i \"{mkv_path}\" -c:v copy -c:a aac -y \"{output_path}\""
        )
        
        print(f"DEBUG: Running ffmpeg command: {ffmpeg_command}")
        
        process_ffmpeg = subprocess.Popen(
            ffmpeg_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        stdout_ffmpeg, stderr_ffmpeg = process_ffmpeg.communicate()
        
        print(f"DEBUG: ffmpeg return code: {process_ffmpeg.returncode}")
        print(f"DEBUG: ffmpeg stdout: {stdout_ffmpeg[:500] if stdout_ffmpeg else 'None'}")
        print(f"DEBUG: ffmpeg stderr: {stderr_ffmpeg[:500] if stderr_ffmpeg else 'None'}")
        
        if process_ffmpeg.returncode == 0:
            print(f"DEBUG: Final output file size: {os.path.getsize(output_path)} bytes")
            progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(output_file_name)}[/green] ✓")
            progress.remove_task(task_id)
            shutil.rmtree(download_folder_path)
            return
        else:
            print(f"DEBUG: FFmpeg conversion failed!")
            progress.remove_task(task_id)
            return

    # Fall back to traditional MP4/M4A processing
    if not mp4_files or not m4a_files:
        progress.console.log(f"[red]Missing Video and Audio files {output_file_name}[/red] ✕")
        progress.remove_task(task_id)
        return

    progress.update(task_id,  description=f"Merging Video and Audio {remove_emojis_and_binary(output_file_name)}", completed=0)
    
    video_path = os.path.join(download_folder_path, mp4_files[0])
    audio_path = os.path.join(download_folder_path, m4a_files[0])
    output_path = os.path.join(os.path.dirname(download_folder_path), output_file_name)

    ffmpeg_command = (
        f"ffmpeg -loglevel panic -i \"{video_path}\" -i \"{audio_path}\" -c:v copy -c:a aac -y "
        f"\"{output_path}.mp4\""
    )

    process_ffmpeg = subprocess.Popen(
        ffmpeg_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    time_pattern = re.compile(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})')
    
    while True:
        output = process_ffmpeg.stderr.readline()
        if output == '' and process_ffmpeg.poll() is not None:
            break
        if output:
            match = time_pattern.search(output)
            if match:
                timestamp = match.group(1)
                seconds = timestamp_to_seconds(timestamp)
                progress.update(task_id,  completed=(int(seconds) / length) * 100)

    stdout_ffmpeg, stderr_ffmpeg = process_ffmpeg.communicate()

    if stderr_ffmpeg or process_ffmpeg.returncode != 0:
        progress.console.log(f"[red]Error Merging Video and Audio files {remove_emojis_and_binary(output_file_name)}[/red] ✕")
        progress.remove_task(task_id)
        return

    progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(output_file_name)}[/green] ✓")
    progress.remove_task(task_id)
    shutil.rmtree(download_folder_path)
