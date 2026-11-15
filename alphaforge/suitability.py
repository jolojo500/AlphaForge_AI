"""Suitability Record storage and S3 PDF management (PRD B-14, #121)."""

from __future__ import annotations

import abc
import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3

from alphaforge import config
from alphaforge.suitability_pdf import generate_suitability_pdf

logger = logging.getLogger(__name__)


class RecordExistsError(Exception):
    """A suitability record already exists for this run; records are immutable."""


def _to_dynamodb_friendly(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamodb_friendly(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamodb_friendly(v) for v in obj]
    return obj


def _from_dynamodb_friendly(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _from_dynamodb_friendly(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamodb_friendly(v) for v in obj]
    return obj


class SuitabilityStore(abc.ABC):
    @abc.abstractmethod
    def save_record(self, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        """Save suitability determination record and upload its PDF."""
        pass

    @abc.abstractmethod
    def get_record(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve suitability record by run_id."""
        pass

    @abc.abstractmethod
    def get_pdf(self, run_id: str) -> bytes | None:
        """Retrieve generated suitability PDF."""
        pass


class LocalSuitabilityStore(SuitabilityStore):
    """Local suitability store for testing and offline development."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or (config.REPO_ROOT / ".storage" / "suitability")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, dict[str, Any]] = {}
        self._pdfs: dict[str, bytes] = {}

    def save_record(self, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        json_path = self.storage_dir / f"{run_id}.json"
        if run_id in self._records or json_path.exists():
            raise RecordExistsError(run_id)
        pdf_bytes = generate_suitability_pdf(record)
        self._records[run_id] = json.loads(json.dumps(record))
        self._pdfs[run_id] = pdf_bytes

        # Persist locally
        json_path = self.storage_dir / f"{run_id}.json"
        pdf_path = self.storage_dir / f"{run_id}.pdf"
        json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        pdf_path.write_bytes(pdf_bytes)

        return self._records[run_id]

    def get_record(self, run_id: str) -> dict[str, Any] | None:
        if run_id in self._records:
            return json.loads(json.dumps(self._records[run_id]))
        json_path = self.storage_dir / f"{run_id}.json"
        if json_path.is_file():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                self._records[run_id] = data
                return data
            except Exception:
                return None
        return None

    def get_pdf(self, run_id: str) -> bytes | None:
        if run_id in self._pdfs:
            return self._pdfs[run_id]
        pdf_path = self.storage_dir / f"{run_id}.pdf"
        if pdf_path.is_file():
            data = pdf_path.read_bytes()
            self._pdfs[run_id] = data
            return data
        record = self.get_record(run_id)
        if record:
            pdf_bytes = generate_suitability_pdf(record)
            self._pdfs[run_id] = pdf_bytes
            return pdf_bytes
        return None


class DynamoDBSuitabilityStore(SuitabilityStore):
    """DynamoDB and S3 backend for immutable suitability records and PDFs."""

    def __init__(
        self,
        table_name: str | None = None,
        bucket_name: str | None = None,
        region_name: str | None = None,
        table_resource: Any = None,
        s3_client: Any = None,
    ) -> None:
        self.table_name = table_name or os.getenv("AF_SUITABILITY_TABLE", "alphaforge-suitability")
        self.bucket_name = bucket_name or os.getenv("AF_S3_BUCKET", "alphaforge-data-908027403910")
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")

        if table_resource is not None:
            self._table = table_resource
        else:
            profile = os.getenv("AWS_PROFILE")
            if profile:
                session = boto3.Session(profile_name=profile, region_name=self.region_name)
            else:
                session = boto3.Session(region_name=self.region_name)
            dynamodb = session.resource("dynamodb", region_name=self.region_name)
            self._table = dynamodb.Table(self.table_name)

        if s3_client is not None:
            self._s3 = s3_client
        else:
            profile = os.getenv("AWS_PROFILE")
            if profile:
                session = boto3.Session(profile_name=profile, region_name=self.region_name)
            else:
                session = boto3.Session(region_name=self.region_name)
            self._s3 = session.client("s3", region_name=self.region_name)

    def save_record(self, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        pdf_bytes = generate_suitability_pdf(record)
        s3_key = f"suitability/{run_id}.pdf"

        # Upload PDF to S3
        try:
            self._s3.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
                Metadata={
                    "project": "alphaforge",
                    "run_id": run_id,
                    "reviewer_id": str(record.get("reviewer_id", "")),
                },
            )
        except Exception:
            logger.exception("Failed to upload suitability PDF to S3 %s/%s", self.bucket_name, s3_key)

        record_to_save = dict(
            record,
            run_id=run_id,
            pdf_s3_bucket=self.bucket_name,
            pdf_s3_key=s3_key,
        )

        # Save record in DynamoDB
        db_item = _to_dynamodb_friendly(record_to_save)
        try:
            # Write-once: a reviewed run's record can never be replaced.
            self._table.put_item(Item=db_item, ConditionExpression="attribute_not_exists(run_id)")
        except Exception as exc:
            if "ConditionalCheckFailed" in type(exc).__name__ or "ConditionalCheckFailed" in str(exc):
                raise RecordExistsError(run_id) from exc
            logger.exception("Failed to save suitability record to DynamoDB table %s", self.table_name)
            raise

        return record_to_save

    def get_record(self, run_id: str) -> dict[str, Any] | None:
        try:
            resp = self._table.get_item(Key={"run_id": run_id})
            item = resp.get("Item")
            if item:
                return _from_dynamodb_friendly(item)
        except Exception:
            logger.exception("Failed to get suitability record for %s from %s", run_id, self.table_name)
        return None

    def get_pdf(self, run_id: str) -> bytes | None:
        s3_key = f"suitability/{run_id}.pdf"
        try:
            resp = self._s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            return resp["Body"].read()
        except Exception:
            logger.warning("Failed to retrieve suitability PDF from S3 for %s", run_id)
            record = self.get_record(run_id)
            if record:
                return generate_suitability_pdf(record)
            return None


_global_suitability_store: SuitabilityStore | None = None


def get_suitability_store() -> SuitabilityStore:
    global _global_suitability_store
    if _global_suitability_store is not None:
        return _global_suitability_store

    backend = os.getenv("AF_SUITABILITY_BACKEND")
    if not backend:
        if "PYTEST_CURRENT_TEST" in os.environ or os.getenv("AF_AUTH") == "off":
            backend = "local"
        else:
            backend = "dynamodb"

    if backend == "dynamodb":
        try:
            _global_suitability_store = DynamoDBSuitabilityStore()
        except Exception:
            logger.warning("Falling back to LocalSuitabilityStore")
            _global_suitability_store = LocalSuitabilityStore()
    else:
        _global_suitability_store = LocalSuitabilityStore()

    return _global_suitability_store


def set_suitability_store_override(store: SuitabilityStore | None) -> None:
    global _global_suitability_store
    _global_suitability_store = store
