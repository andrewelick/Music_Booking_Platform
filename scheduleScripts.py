import boto3
from botocore.client import Config

#AWS credentials
AWS_ACCESS_KEY_ID = "AKIA2RRCVFWRRXETAW55"
AWS_ACCESS_SECRET_KEY = "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"
AWS_BUCKET_NAME = "bluffbucket"

#AWS client setup
s3 = boto3.resource(
    's3',
    aws_access_key_id = AWS_ACCESS_KEY_ID,
    aws_secret_access_key = AWS_ACCESS_SECRET_KEY,
    config = Config(signature_version = 's3v4')
)

data = open("requirements.txt", 'rb')

#Write file to AWS S3 bucket
s3.Bucket(AWS_BUCKET_NAME).put_object(Key = "requirements.txt", Body = data, ContentType = 'text/html')
