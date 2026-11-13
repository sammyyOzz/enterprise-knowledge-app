import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from api.core.config import config as app_config

BUCKET = app_config.S3_BUCKET

s3 = boto3.client(
  "s3",
  endpoint_url=app_config.S3_ENDPOINT_URL,  # remove this line for real AWS S3
  aws_access_key_id=app_config.S3_ACCESS_KEY,
  aws_secret_access_key=app_config.S3_SECRET_KEY,
  config=Config(signature_version="s3v4"),
  region_name="us-east-1",
)

def ensure_bucket():
  try:
    s3.head_bucket(Bucket=BUCKET)
  except ClientError:
    s3.create_bucket(Bucket=BUCKET)

def upload_file(fileobj, key: str, content_type: str):
  s3.upload_fileobj(fileobj, BUCKET, key, ExtraArgs={"ContentType": content_type})

def download_file(key: str) -> bytes:
  return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()

def delete_file(key: str):
  s3.delete_object(Bucket=BUCKET, Key=key)