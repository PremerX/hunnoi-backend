from dotenv import load_dotenv
import boto3
import os

load_dotenv()

def upload_to_s3_and_generate_link(zip_file_path, bucket_name):
    try:
        # อ่านค่าจาก environment variables
        access_key = os.getenv("MINIO_ACCESS_KEY")
        secret_key = os.getenv("MINIO_SECRET_KEY")
        endpoint_url = os.getenv("MINIO_ENDPOINT_URL")

        # เชื่อมต่อ S3/MinIO
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )

        object_name = '/'.join(zip_file_path.split('/')[-2:])

        # อัปโหลดไฟล์
        s3_client.upload_file(zip_file_path, bucket_name, object_name)
        print(f"Uploaded {zip_file_path} to bucket '{bucket_name}' as '{object_name}'.")

        # สร้างลิงก์ชั่วคราว
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=3600
        )
        print(f"Temporary URL: {presigned_url}")

    except Exception as e:
        print(f"An error occurred: {e}")

# การใช้งาน
zip_file_path = "tester/sub1/font.zip"
bucket_name = "hunnoi"

upload_zip_to_s3_and_generate_link(zip_file_path, bucket_name)
