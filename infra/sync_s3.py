"""S3 data and caches sync utility (PRD 2, C-5). Track C owned."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

DEFAULT_BUCKET = os.getenv("AF_S3_BUCKET", "alphaforge-data-908027403910")
DEFAULT_TABLE = os.getenv("AF_DYNAMODB_TABLE", "alphaforge-traces")
DEFAULT_REGION = os.getenv("AWS_REGION", "us-east-1")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STARTER_DIR = REPO_ROOT / "Datathon2026" / "alphaforge_starter"
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "cache"


def get_boto3_session(region: str = DEFAULT_REGION) -> boto3.Session:
    profile = os.getenv("AWS_PROFILE")
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def init_infrastructure(
    bucket_name: str = DEFAULT_BUCKET,
    table_name: str = DEFAULT_TABLE,
    region: str = DEFAULT_REGION,
) -> dict[str, Any]:
    """Ensure S3 bucket (versioned + tagged) and DynamoDB table exist."""
    session = get_boto3_session(region)
    s3 = session.client("s3")
    dynamodb = session.client("dynamodb")

    # 1. S3 Bucket
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise

    # Versioning
    s3.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={"Status": "Enabled"},
    )

    # Tagging
    s3.put_bucket_tagging(
        Bucket=bucket_name,
        Tagging={"TagSet": [{"Key": "project", "Value": "alphaforge"}]},
    )

    # 2. DynamoDB Table
    try:
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "run_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
            Tags=[{"Key": "project", "Value": "alphaforge"}],
        )
        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=table_name)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code != "ResourceInUseException":
            raise

    return {
        "bucket": bucket_name,
        "table": table_name,
        "region": region,
        "status": "ready",
    }


def upload_directory(
    s3_client: Any,
    bucket_name: str,
    local_dir: Path,
    s3_prefix: str,
) -> int:
    """Upload all files from local_dir to s3://bucket_name/s3_prefix/."""
    if not local_dir.is_dir():
        return 0

    count = 0
    for file_path in local_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith(".git"):
            rel_path = file_path.relative_to(local_dir)
            s3_key = f"{s3_prefix}/{rel_path}".replace("\\", "/").lstrip("/")
            s3_client.upload_file(str(file_path), bucket_name, s3_key)
            count += 1
    return count


def download_prefix(
    s3_client: Any,
    bucket_name: str,
    s3_prefix: str,
    target_dir: Path,
) -> int:
    """Download all objects under s3_prefix to target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    paginator = s3_client.get_paginator("list_objects_v2")
    count = 0

    for page in paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            s3_key = obj["Key"]
            rel_path = s3_key[len(s3_prefix) :].lstrip("/")
            if not rel_path:
                continue
            dest_file = target_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            s3_client.download_file(bucket_name, s3_key, str(dest_file))
            count += 1
    return count


def push_all(
    bucket_name: str = DEFAULT_BUCKET,
    starter_dir: Path = DEFAULT_STARTER_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    region: str = DEFAULT_REGION,
) -> dict[str, int]:
    """Upload starter data and data/cache/ to S3."""
    session = get_boto3_session(region)
    s3 = session.client("s3")

    starter_uploaded = upload_directory(s3, bucket_name, starter_dir, "starter")
    cache_uploaded = upload_directory(s3, bucket_name, cache_dir, "cache")

    return {
        "starter_files": starter_uploaded,
        "cache_files": cache_uploaded,
    }


def pull_caches(
    bucket_name: str | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    region: str = DEFAULT_REGION,
) -> int:
    """Pull data/cache/ from S3 if bucket is configured."""
    bucket = bucket_name or os.getenv("AF_S3_BUCKET")
    if not bucket:
        return 0

    session = get_boto3_session(region)
    s3 = session.client("s3")
    return download_prefix(s3, bucket, "cache", cache_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync S3 bucket and DynamoDB table for AlphaForge AI.")
    parser.add_argument("action", choices=["init", "push", "pull"], help="Action to perform")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="S3 bucket name")
    parser.add_argument("--table", default=DEFAULT_TABLE, help="DynamoDB table name")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS Region")

    args = parser.parse_args()

    if args.action == "init":
        res = init_infrastructure(args.bucket, args.table, args.region)
        print(f"Initialized infrastructure: {res}")
    elif args.action == "push":
        res = push_all(args.bucket, region=args.region)
        print(f"Uploaded to s3://{args.bucket}: {res}")
    elif args.action == "pull":
        count = pull_caches(args.bucket, region=args.region)
        print(f"Downloaded {count} cache files from s3://{args.bucket}/cache")


if __name__ == "__main__":
    main()
