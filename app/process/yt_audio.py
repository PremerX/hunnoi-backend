import asyncio
import yt_dlp
import librosa
import numpy as np
from pydub import AudioSegment
from os import getenv, path
import zipfile
from concurrent.futures import ThreadPoolExecutor
import boto3
import tempfile
import re

def sanitize_filename(filename, replacement="_"):
    """
    ลบหรือแทนที่อักขระต้องห้ามในชื่อไฟล์หรือโฟลเดอร์
    :param filename: ชื่อไฟล์หรือโฟลเดอร์ที่ต้องการแก้ไข
    :param replacement: อักขระที่ใช้แทนอักขระต้องห้าม (default: "_")
    :return: ชื่อที่แก้ไขแล้ว
    """
    # อักขระต้องห้ามใน Windows: \ / : * ? " < > |
    forbidden_chars = r'[\\/:*?"<>|]'
    sanitized = re.sub(forbidden_chars, replacement, filename)
    return sanitized

def adjust_indices(start_indices, end_indices, transitions):
    if len(start_indices) == len(end_indices):
        if abs(start_indices[0] - end_indices[0]) > 100:
            start_indices = np.insert(start_indices, 0, 0)
            end_indices = np.append(end_indices, len(transitions))
    else:
        if abs(start_indices[0] - end_indices[0]) > 100:
            start_indices = np.insert(start_indices, 0, 0)
            return start_indices, end_indices
        if abs(start_indices[-1] - end_indices[-1]) > 100:
            end_indices = np.append(end_indices, len(transitions))
            return start_indices, end_indices
    
    return start_indices, end_indices

def download_audio(url, tag, output_path="downloads", preferred_format="mp3", quality="128"):
    # ตั้งค่า options สำหรับ audio
    ydl_opts = {
        'format': 'bestaudio/best',
        "cookiefile": {getenv("COOKIE_PATH")},
        "verbose": True,
        "sleep_interval_requests": 1.2,
        "sleep_interval": 60,
        "max_sleep_interval": 90,
        "extractor_args": f'youtube:po_token={getenv("PO_TOKEN")}',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': preferred_format,
            'preferredquality': quality,
        }],
        'postprocessor_args': ['-af', 'anull'], # skip adjust over volume (normalize)
        'outtmpl': f'{output_path}/{tag}/%(id)s.%(ext)s',
    }

    # ดาวน์โหลด
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=True)

    # คืนค่า title หลังจากดาวน์โหลด
    title = sanitize_filename(result.get('title'))
    ids = result.get('id')
    return title, ids

def calculate_segments_numpy(audio_path, frame_length=2048, hop_length=1024, threshold=0.005, short_silence_threshold=0.75):
    y, sr = librosa.load(audio_path, sr=16000)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    non_silence_frames = rms < threshold
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    transitions = np.diff(non_silence_frames.astype(int))
    start_indices = np.where(transitions == 1)[0] + 1
    end_indices = np.where(transitions == -1)[0] + 1

    start_indices, end_indices = adjust_indices(start_indices, end_indices, transitions)

    start_times = times[start_indices]
    end_times = times[end_indices]

    durations = end_times - start_times
    valid_indices = durations > short_silence_threshold
    segments = np.column_stack((start_times[valid_indices], end_times[valid_indices]))

    silence_midpoints = segments.mean(axis=1)

    silence_midpoints[0] = 0
    silence_midpoints[-1] = times[-1]

    song_duration_pairs = np.column_stack((silence_midpoints[:-1], silence_midpoints[1:]))

    return song_duration_pairs

def split_and_save(input_file, temp_dir, segments, base_name=None):
    audio = AudioSegment.from_file(input_file)
    if base_name is None:
        base_name = path.splitext(path.basename(input_file))[0]

    def save_segment(i, start, end):
        start_ms = start * 1000
        end_ms = end * 1000
        output_file = path.join(temp_dir, f"{i:02}_{base_name}.mp3")
        target_audio = audio[start_ms:end_ms]
        target_audio.export(output_file, format="mp3")
        return output_file

    song_files = []
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(save_segment, i, start, end) for i, (start, end) in enumerate(segments, start=1)]
        for future in futures:
            song_files.append(future.result())
    
    return song_files

def zip_files(song_files, zip_file_path):
    with zipfile.ZipFile(zip_file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
        for file in song_files:
            zipf.write(file, path.basename(file))
    print(f"Zipped {len(song_files)} files into {zip_file_path}")

def upload_to_s3_and_generate_link(zip_file_path, object_name = None):
    try:
        access_key = getenv("MINIO_ACCESS_KEY")
        secret_key = getenv("MINIO_SECRET_KEY")
        endpoint_url = getenv("MINIO_ENDPOINT_URL")
        public_url = getenv("MINIO_PUBLIC_URL")
        bucket_name = getenv("MINIO_BUCKET")
        region_name = getenv("MINIO_REGION")

        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            region_name=region_name
        )

        if object_name is None:
            object_name = '/'.join(zip_file_path.split('/')[-2:])

        # Upload the file
        s3_client.upload_file(zip_file_path, bucket_name, object_name)
        print(f"Uploaded {zip_file_path} to bucket '{bucket_name}' as '{object_name}'.")

        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=3600
        )
        print(f"Presigned URL: {presigned_url}")
        presigned_url = presigned_url.replace(endpoint_url, public_url)
        print(f"Public URL: {presigned_url}")
        return presigned_url

    except Exception as e:
        print(f"An error occurred at upload file to S3 : {type(e)} {e}")

# -af loudnorm=I=-14:TP=-1.5:LRA=11 # normalize audio

async def youtube_process_main(url, tag, ws):

    print(f"Downloading audio from {url}...")
    await ws.send_json({"status": "Processing", "msg": "กำลังดึงข้อมูลเพลงใน Playlist"})

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        title, ids = await asyncio.to_thread(download_audio, url, tag, temp_dir)
        print("Download completed.")
        await ws.send_json({"status": "Processing", "msg": "กำลังตรวจสอบเพลง"})
        raw_song_file = path.join(temp_dir, tag, f"{ids}.mp3")
        segments = await asyncio.to_thread(calculate_segments_numpy, raw_song_file)

        if(len(segments) <= 2):
            presigned_url = await asyncio.to_thread(
                upload_to_s3_and_generate_link,
                path.join(temp_dir, tag, f"{ids}.mp3"),
                f"{tag}/{title}.mp3"
            )
            await ws.send_json({"status": "Break", "msg": "Playlist นี้ ไม่สามารถแบ่งเพลงได้ แต่คุณสามารถดาวน์โหลดได้", "download_url": presigned_url})
            return
        
        await ws.send_json({"status": "Processing", "msg": "Playlist นี้แบ่งได้ กำลังแบ่งเพลง"})
        split_song_files = await asyncio.to_thread(split_and_save, raw_song_file, path.join(temp_dir, tag), segments, title)

        await ws.send_json({"status": "Processing", "msg": "แบ่งเพลงสำเร็จ รออีกนิด กำลังสร้างลิ้งดาวน์โหลด"})
        zip_path = path.join(temp_dir, tag, f"playlist_{title}.zip")
        await asyncio.to_thread(zip_files, split_song_files, zip_path)
        presigned_url = await asyncio.to_thread(
            upload_to_s3_and_generate_link,
            zip_path,
            f"{tag}/playlist_{title}.zip"
        )
        # shutil.rmtree(temp_dir, ignore_errors=True)
        await ws.send_json({"status": "Completed", "msg": "สร้างลิ้งดาวน์โหลดสำเร็จ", "download_url": presigned_url})
