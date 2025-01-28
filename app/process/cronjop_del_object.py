import boto3
from datetime import datetime, timedelta
from os import getenv

access_key = getenv("MINIO_ACCESS_KEY")
secret_key = getenv("MINIO_SECRET_KEY")
endpoint_url = getenv("MINIO_ENDPOINT")
bucket = getenv("MINIO_BUCKET")
region = getenv("MINIO_REGION")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    endpoint_url=endpoint_url
)

expiration_time = datetime.now(datetime.timezone.utc) - timedelta(hours=1)

try:
    objects = s3_client.list_objects_v2(Bucket=bucket)
    if "Contents" in objects:
        for obj in objects["Contents"]:
            last_modified = obj["LastModified"].replace(tzinfo=None)
            if last_modified < expiration_time:
                s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
                print(f"Deleted {obj['Key']}")
    else:
        print(f"No objects found in bucket: {bucket}")
except Exception as e:
    print(f"An error occurred: {e}")
