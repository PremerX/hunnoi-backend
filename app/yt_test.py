from datetime import timedelta
import re
import boto3
from dotenv import load_dotenv
from minio import Minio
from os import getenv
import requests
import yt_dlp


def upload_to_s3_and_generate_link(zip_file_path, object_name = None):
    load_dotenv()
    try:
        access_key = getenv("MINIO_ACCESS_KEY")
        secret_key = getenv("MINIO_SECRET_KEY")
        endpoint_url = getenv("MINIO_ENDPOINT")
        bucket_name = getenv("MINIO_BUCKET")
        region_name = getenv("MINIO_REGION")
        public_url = getenv("MINIO_PUBLIC_URL")

        minio_client = Minio(
            endpoint=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
            region=region_name,
            secure=False
        )

        if object_name is None:
            object_name = '/'.join(zip_file_path.split('/')[-2:])

        # Upload the file
        minio_client.fput_object(bucket_name, object_name, zip_file_path)
        print(f"Uploaded {zip_file_path} to bucket '{bucket_name}' as '{object_name}'.")

        # Generate presigned URL
        presigned_url = minio_client.presigned_get_object(
            bucket_name,
            object_name,
            expires=timedelta(hours=1)
        )
        presigned_url = presigned_url.replace(endpoint_url, public_url)
        print(f"Presigned URL: {presigned_url}")
        return presigned_url

    except Exception as e:
        print(f"An error occurred at upload file to S3 : {type(e)} {e}")

def test(zip_file_path, object_name = None):
    load_dotenv()
    try:
        access_key = getenv("MINIO_ACCESS_KEY")
        secret_key = getenv("MINIO_SECRET_KEY")
        endpoint_url = getenv("MINIO_ENDPOINT_URL")
        bucket_name = getenv("MINIO_BUCKET")
        region_name = getenv("MINIO_REGION")
        public_url = getenv("MINIO_PUBLIC_URL")

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

def test_url(link):
    ydl_opts = {
        "verbose": True,
        "format": "best",
        'cookiefile': None,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(link, download=False)
    print(info.get("id"))
    print(info.get("title"))
    print(info.get("thumbnail"))
# การใช้งาน
# zip_file_path = "main.py"
# object_name = "samva/main.py"

# # test(zip_file_path, object_name)
# upload_to_s3_and_generate_link(zip_file_path, object_name)

# test_url("https://www.youtube.com/watch?v=rc7KnQAh_1I")
test_url("https://www.youtube.com/watch?v=sB5bHrdm0Lo")
