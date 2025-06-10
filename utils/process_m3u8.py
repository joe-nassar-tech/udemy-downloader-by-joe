import re
import os
import m3u8
import shutil
import requests
import subprocess
from constants import remove_emojis_and_binary

def download_and_merge_m3u8(m3u8_file_url, download_folder_path, title_of_output_mp4, task_id, progress, drm_key=None):
    progress.update(task_id,  description=f"Downloading Stream {remove_emojis_and_binary(title_of_output_mp4)}", completed=0)
    
    response = requests.get(m3u8_file_url)
    response.raise_for_status()
    
    m3u8_content = response.text
    m3u8_obj = m3u8.loads(m3u8_content)
    playlists = m3u8_obj.playlists
    
    highest_quality_playlist = None
    max_resolution = (0, 0)

    progress.update(task_id,  completed=99)
 
    for pl in playlists:
        resolution = pl.stream_info.resolution

        if resolution and (resolution[0] * resolution[1] > max_resolution[0] * max_resolution[1]):
            highest_quality_playlist = pl
            max_resolution = resolution

    if not highest_quality_playlist:
        progress.console.log(f"No valid playlists {remove_emojis_and_binary(title_of_output_mp4)} ✕")
        progress.remove_task(task_id)
        return
    
    highest_quality_url = highest_quality_playlist.uri

    highest_quality_response = requests.get(highest_quality_url)
    m3u8_file_path = os.path.join(download_folder_path, "index.m3u8")

    with open(m3u8_file_path, 'wb') as file:
        file.write(highest_quality_response.content) 

    merge_segments_into_mp4(m3u8_file_path, download_folder_path, title_of_output_mp4, task_id, progress, drm_key)

def merge_segments_into_mp4(m3u8_file_path, download_folder_path, output_file_name, task_id, progress, drm_key=None):
    output_path = os.path.dirname(download_folder_path)

    progress.update(task_id,  description=f"Merging segments {remove_emojis_and_binary(output_file_name)}", completed=0)
    
    # Base command for n_m3u8dl-re
    nm3u8dl_command = (
        f"n_m3u8dl-re \"{m3u8_file_path}\" --save-dir \"{output_path}\" "
        f"--save-name \"{output_file_name}\" --auto-select --concurrent-download "
        f"--del-after-done --no-log --tmp-dir \"{output_path}\" --log-level ERROR"
    )
    
    # Add DRM decryption if key is provided (use Shaka Packager for DRM content)
    if drm_key:
        packager_path = os.path.abspath("shaka-packager.exe")
        nm3u8dl_command += (
            f" --key {drm_key} --decryption-engine SHAKA_PACKAGER "
            f"--decryption-binary-path \"{packager_path}\" -mt -M format=mkv"
        )

    pattern = re.compile(r'(\d+\.\d+%)')
    process = subprocess.Popen(nm3u8dl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')

    while True:
        try:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                stripped_output = output.strip().replace(' ', '')
            if stripped_output.startswith('Vid'):
                matches = pattern.findall(output)
                if matches:
                    first_percentage = float(matches[0].replace('%', ''))
                    progress.update(task_id,  completed=first_percentage)
        except (UnicodeDecodeError, UnicodeError):
            # Skip lines that can't be decoded
            continue

    stdout, stderr = process.communicate()

    if stderr or process.returncode != 0:
        progress.console.log(f"[red]Error Merging {remove_emojis_and_binary(output_file_name)}[/red] ✕")
        progress.remove_task(task_id)
        return
    
    progress.console.log(f"[green]Downloaded {remove_emojis_and_binary(output_file_name)}[/green] ✓")
    progress.remove_task(task_id)
    shutil.rmtree(download_folder_path)