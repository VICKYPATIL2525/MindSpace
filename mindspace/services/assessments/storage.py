"""
Storage helpers for assessment media files.
Supports local storage and optional GCP storage.
"""

import os
import uuid
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from mindspace.models import MediaAsset
from mindspace.services.assessments.result_savers import safe_decimal


def env_value(name, default=""):
    value = getattr(settings, name, None)
    if value:
        return str(value).strip().strip("\"'")
    return os.getenv(name, default).strip().strip("\"'")

def save_uploaded_activity_file(
    *,
    file_obj,
    user_id,
    activity_type,
    original_filename,
    content_type,
):
    use_gcp = getattr(settings, "USE_GCP_STORAGE", False)

    ext = ""
    if original_filename and "." in original_filename:
        ext = "." + original_filename.split(".")[-1].lower()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    unique_filename = f"{uuid.uuid4()}{ext}"

    if use_gcp:
        return upload_file_to_gcp(
            file_obj=file_obj,
            user_id=user_id,
            activity_type=activity_type,
            original_filename=original_filename,
            content_type=content_type,
        )

    local_path = f"activity_uploads/user_{user_id}/{activity_type}/{today}/{unique_filename}"

    file_obj.seek(0)
    saved_path = default_storage.save(local_path, ContentFile(file_obj.read()))
    file_url = default_storage.url(saved_path)

    return {
        "storage_provider": "local",
        "object_key": saved_path,
        "file_url": file_url,
        "bucket_name": "",
        "metadata": {
            "local_file": saved_path,
            "storage_backend": "local",
        },
    }

def upload_file_to_gcp(
    *,
    file_obj,
    user_id,
    activity_type,
    original_filename,
    content_type,
):
    try:
        from google.cloud import storage
    except Exception as exc:
        raise RuntimeError(
            "google-cloud-storage is not installed. Install it using: "
            "pip install google-cloud-storage. "
            f"Original error: {exc}"
        )

    bucket_name = env_value("GS_BUCKET_NAME") or env_value("GCP_BUCKET_NAME")
    credentials_path = env_value("GOOGLE_APPLICATION_CREDENTIALS")

    if not bucket_name:
        raise RuntimeError("GS_BUCKET_NAME or GCP_BUCKET_NAME missing in settings.py/.env")

    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    ext = ""
    if original_filename and "." in original_filename:
        ext = "." + original_filename.split(".")[-1].lower()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    unique_filename = f"{uuid.uuid4()}{ext}"

    blob_name = f"users/user_{user_id}/{activity_type}/{today}/{unique_filename}"

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    file_obj.seek(0)
    blob.upload_from_file(file_obj, content_type=content_type)

    gcp_uri = f"gs://{bucket_name}/{blob_name}"

    return {
        "storage_provider": "gcp",
        "object_key": blob_name,
        "file_url": gcp_uri,
        "bucket_name": bucket_name,
        "metadata": {
            "gcp_uri": gcp_uri,
            "gcp_blob_name": blob_name,
            "storage_backend": "gcp",
        },
    }

def create_media_asset(
    *,
    request,
    media_type,
    file_obj,
    storage_data,
    activity_type,
    extra_metadata=None,
    duration_seconds=None,
):
    metadata = storage_data.get("metadata") or {}
    if extra_metadata:
        metadata.update(extra_metadata)

    model_fields = {field.name for field in MediaAsset._meta.fields}

    data = {
        "user": request.user,
        "media_type": media_type,
        "file_name": getattr(file_obj, "name", "upload"),
        "content_type": getattr(file_obj, "content_type", "") or "application/octet-stream",
        "size_bytes": getattr(file_obj, "size", 0) or 0,
        "storage_provider": storage_data["storage_provider"],
        "bucket_name": storage_data.get("bucket_name") or "",
        "object_key": storage_data["object_key"],
        "cdn_url": storage_data.get("file_url") or "",
        "upload_status": "completed",
        "metadata_json": metadata,
    }

    if "duration_seconds" in model_fields:
        data["duration_seconds"] = safe_decimal(duration_seconds, default=None)

    if "is_public" in model_fields:
        data["is_public"] = False

    return MediaAsset.objects.create(**data)

def get_local_media_absolute_path(media_asset):
    if not media_asset or media_asset.storage_provider != "local":
        return ""

    media_root = getattr(settings, "MEDIA_ROOT", None)

    if not media_root:
        raise RuntimeError("MEDIA_ROOT is missing.")

    return str(Path(media_root) / media_asset.object_key)