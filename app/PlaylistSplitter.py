from concurrent.futures import ThreadPoolExecutor
from boto3.s3.transfer import TransferConfig, MB
from zipfile import ZipFile, ZIP_DEFLATED
from tempfile import TemporaryDirectory
from app.ProcessEnum import ProcessEnum
from os import getenv, path, cpu_count
from app.LoggerInstance import logger
from pydub import AudioSegment
from fastapi import WebSocket
from yt_dlp import YoutubeDL
from re import sub
import numpy as np
import boto3
import shutil
import asyncio
import librosa
import gc

class PlaylistSplitter:
    def __init__(self, url: str, tag: str, websocket: WebSocket):
        self.url = url
        self.tag = tag
        self.websocket = websocket

    async def sent_msg(self, status: ProcessEnum, msg: str, **kwargs):
        payload = {"status": status.value, "msg": msg}
        payload.update(kwargs)
        await self.websocket.send_json(payload)

    async def run(self):
        logger.info(f"[PLAYLIST SPLITTER] => "
                    f"Websocket [{self.websocket.headers.get("sec-websocket-key", "unknown")}] "
                    f": [{self.tag}]")

        await self.sent_msg(ProcessEnum.PROCESSING, "กำลังดึงข้อมูลเพลงใน Playlist")
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            # Downlaod target audio
            title, ids = await asyncio.to_thread(
                self.download_audio,
                temp_dir
            )
            logger.info(f"[PLAYLIST SPLITTER] : {self.tag} : Download completed.")
            await self.sent_msg(
                ProcessEnum.PROCESSING,
                "กำลังตรวจสอบเพลง"
            )
            playlist_path = path.join(temp_dir, self.tag, f"{ids}.mp3")

            # Calculate audio segments
            segments = await asyncio.to_thread(
                self.calculate_segments_numpy,
                playlist_path
            )

            # Handle when segments groups cannot be separated (Single song, Segmentation error, etc.)
            if (len(segments) <= 2):
                logger.info(f"[PLAYLIST SPLITTER] : {self.tag} : Cannot split segments. Create download link instead.")
                presigned_url = await asyncio.to_thread(
                    self.upload_to_s3,
                    path.join(temp_dir, self.tag, f"{ids}.mp3"),
                    f"{tag}/{title}.mp3"
                )
                await self.sent_msg(
                    ProcessEnum.BREAK,
                    "Playlist นี้ ไม่สามารถแบ่งเพลงได้ แต่คุณสามารถดาวน์โหลดได้",
                    download_url=presigned_url
                )
                return

            # Split song from segments into files.
            logger.info(f"[PLAYLIST SPLITTER] : {self.tag} : Splitting song into files.")
            await self.sent_msg(
                ProcessEnum.PROCESSING,
                "Playlist นี้แบ่งได้ กำลังแบ่งเพลง"
            )
            split_song_files = await asyncio.to_thread(
                self.split_and_save,
                playlist_path,
                path.join(temp_dir, self.tag),
                segments,
                title)

            # Zip the previously split music files.
            logger.info(f"[PLAYLIST SPLITTER] : {self.tag} : Zipping files.")
            await self.sent_msg(
                ProcessEnum.PROCESSING,
                "แบ่งเพลงสำเร็จ รออีกนิด กำลังสร้างลิ้งดาวน์โหลด"
            )

            zip_path = path.join(temp_dir, self.tag, f"playlist_{title}.zip")
            await asyncio.to_thread(
                self.zip_files,
                split_song_files,
                zip_path
            )

            # Sent Zipped file to S3 storage
            presigned_url = await asyncio.to_thread(
                self.upload_to_s3,
                zip_path,
                f"{self.tag}/playlist_{title}.zip"
            )

            # Completed !!
            await self.sent_msg(
                ProcessEnum.COMPLETED,
                "สร้างลิ้งดาวน์โหลดสำเร็จ",
                download_url=presigned_url
            )

    def download_audio(self, output_path="downloads", preferred_format="mp3", quality="128"):
        cookies = getenv("COOKIE_PATH") if getenv("COOKIE_PATH") != '' else None
        ydl_opts = {
            'format': 'bestaudio/best',
            "cookiefile": cookies,
            "sleep_interval_requests": 0.4,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': preferred_format,
                'preferredquality': quality,
            }],
            'postprocessor_args': ['-af', 'anull'],  # skip normalize volume
            'outtmpl': f'{output_path}/{self.tag}/%(id)s.%(ext)s',
        }

        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(self.url, download=True)

        title = self.sanitize_filename(result.get('title'))
        ids = result.get('id')
        return title, ids

    @staticmethod
    def calculate_segments_numpy(audio_file_path, frame_length=2048, hop_length=1024, threshold=0.005,
                                 short_silence_threshold=0.75):
        y, sr = librosa.load(audio_file_path, sr=16000)
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        non_silence_frames = rms < threshold
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

        transitions = np.diff(non_silence_frames.astype(int))
        start_indices = np.where(transitions == 1)[0] + 1
        end_indices = np.where(transitions == -1)[0] + 1
        print(start_indices)
        print(end_indices)

        start_indices, end_indices = PlaylistSplitter.adjust_indices(start_indices, end_indices, transitions)
        start_times = times[start_indices]
        end_times = times[end_indices]
        print(start_times)
        print(end_times)

        durations = end_times - start_times
        print(durations)

        valid_indices = durations > short_silence_threshold
        print(valid_indices)

        segments = np.column_stack((start_times[valid_indices], end_times[valid_indices]))
        silence_midpoints = segments.mean(axis=1)
        print(silence_midpoints)

        silence_midpoints[0] = 0
        silence_midpoints[-1] = times[-1]
        print(silence_midpoints)

        song_duration_pairs = np.column_stack((silence_midpoints[:-1], silence_midpoints[1:]))
        print(song_duration_pairs)

        del y
        gc.collect()
        return song_duration_pairs

    @staticmethod
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

    @staticmethod
    def split_and_save(audio_file_path, temp_dir, segments, base_name=None, max_threads: int = None):
        """
        Split an audio file into segments and save them as MP3 files.

        :param audio_file_path: Path to the input audio file.
        :param temp_dir: Directory to save the split audio files.
        :param segments: List of tuples (start, end) in seconds.
        :param base_name: Optional base name for output files.
        :param max_threads: Number of threads to use; if None, use system CPU count.
        :return: List of saved file paths.
        """
        # Determine max_threads dynamically if not set
        if max_threads is None:
            max_threads = cpu_count() or 1 # Use available CPU cores, default to 1 if unknown

        # Load audio file
        with open(audio_file_path, "rb") as f:
            audio = AudioSegment.from_file(f, format="mp3")

        if base_name is None:
            base_name = path.splitext(path.basename(audio_file_path))[0]

        def save_segment(i, start, end):
            start_ms = start * 1000
            end_ms = end * 1000
            output_file = path.join(temp_dir, f"{i:02}_{base_name}.mp3")
            target_audio = audio[start_ms:end_ms]
            target_audio.export(output_file, format="mp3")
            del target_audio
            return output_file

        song_files = []
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [
                executor.submit(save_segment, i, start, end)
                for i, (start, end) in enumerate(segments, start=1)
            ]
            for future in futures:
                song_files.append(future.result())

        del audio
        gc.collect()
        return song_files

    @staticmethod
    def zip_files(song_files, zip_file_path):
        length = 10 * 1024 * 1024 # 10MB Stream zip
        with ZipFile(zip_file_path, 'w', compression=ZIP_DEFLATED) as zipf:
            for file in song_files:
                with open(file, "rb") as f:
                    with zipf.open(path.basename(file), "w") as dest:
                        shutil.copyfileobj(f, dest, length=length)
        logger.info(f"Zipped {len(song_files)} files into {zip_file_path}")

    @staticmethod
    def upload_to_s3(zip_file_path, object_name=None):
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

            transfer_config = TransferConfig(
                multipart_threshold=10 * MB,
                multipart_chunksize=10 * MB
            )
            # Upload the file
            s3_client.upload_file(zip_file_path, bucket_name, object_name, Config=transfer_config)
            logger.info(f"Uploaded {zip_file_path} to bucket '{bucket_name}' as '{object_name}'.")

            # Generate presigned URL
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_name},
                ExpiresIn=3600
            )
            presigned_url = presigned_url.replace(endpoint_url, public_url)
            logger.info(f"Public URL: {presigned_url}")
            return presigned_url
        except Exception as e:
            logger.error(f"An error occurred at upload file to S3 : {type(e)} {e}")

    @staticmethod
    def sanitize_filename(filename, replacement="_"):
        """
        Remove or replace forbidden characters in a file or folder name.
        :param filename: The file or folder name to be modified.
        :param replacement: The character used to replace forbidden characters (default: "_").
        :return: The modified name.
        """
        forbidden_chars = r'[\\/:*?"<>|]'
        sanitized = sub(forbidden_chars, replacement, filename)
        return sanitized