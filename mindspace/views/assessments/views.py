import json
import os
import re
import time
import uuid
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from mindspace.models import (
    AudioExtractionResult,
    AudioScenario,
    FaceFeatureVector,
    FacialAnalysisResult,
    FusionPrediction,
    MediaAsset,
    ModalityResult,
    PcaPipelineResult,
    PhonationAttempt,
    PhonationFeature,
    PhonationSession,
    PhonationSound,
    PlatformScreeningSession,
    ScenarioSession,
    TextAnalysisResult,
    TextParameterResult,
    Transcript,
    VideoActivity,
    VideoSession,
    VoiceAnalysisResult,
)


# ============================================================
# ONBOARDING / ACCESS HELPERS
# ============================================================

MIN_FACE_VIDEO_SECONDS = 150

def get_user_profile(user):
    """
    Safe profile lookup for assessment pages.
    Assessments should only run after consent + profile completion.
    """
    profile = getattr(user, "profile", None)
    if profile:
        return profile

    from mindspace.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": "user",
            "account_status": "active",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "avatar": "avatar_1.png",
            "is_email_verified": bool(user.email),
            "profile_completed": False,
            "consented": False,
        },
    )
    return profile


def assessment_page_guard(request):
    """
    Redirect users to the correct onboarding step before assessments.
    """
    profile = get_user_profile(request.user)

    if not profile.consented:
        return redirect("consent")

    if not profile.profile_completed:
        return redirect("complete_profile")

    return None


def assessment_api_guard(request):
    """
    JSON guard for AJAX upload endpoints.
    """
    profile = get_user_profile(request.user)

    if not profile.consented:
        return JsonResponse({
            "ok": False,
            "error": "Consent is required before starting assessment.",
            "redirect_url": "/accounts/consent/",
        }, status=403)

    if not profile.profile_completed:
        return JsonResponse({
            "ok": False,
            "error": "Profile completion is required before starting assessment.",
            "redirect_url": "/accounts/complete-profile/",
        }, status=403)

    return None


# ============================================================
# PAGE RENDER VIEWS
# ============================================================

@login_required
def check_in_view(request):
    """
    Wellness Check-in page.

    POST starts a new PlatformScreeningSession and redirects to Activity 1.
    """
    guard = assessment_page_guard(request)
    if guard:
        return guard

    if request.method == "POST":
        mood = request.POST.get("mood", "").strip()
        note = request.POST.get("note", "").strip()

        # Mark any previous unfinished session as failed/abandoned safely.
        old_session_id = request.session.get("screening_session_id")
        if old_session_id:
            PlatformScreeningSession.objects.filter(
                screening_session_id=old_session_id,
                user=request.user,
                session_status__in=["started", "processing"],
            ).update(
                session_status="failed",
                current_activity="abandoned",
            )

        session = PlatformScreeningSession.objects.create(
            user=request.user,
            session_status="started",
            current_activity="face_video",
            workflow_stage=1,
            completed_activities_count=0,
        )

        request.session["screening_session_id"] = str(session.screening_session_id)
        request.session["initial_check_in"] = {
            "mood": mood,
            "note": note,
            "created_at": timezone.now().isoformat(),
        }

        return redirect("activity_session")

    return render(request, "assessments/check_in.html")


@login_required
def activity_session_view(request):
    guard = assessment_page_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)
    return render(request, "assessments/activity_session.html", {
        "session": session,
    })


@login_required
def voice_phonation_view(request):
    guard = assessment_page_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)
    return render(request, "assessments/voice_phonation.html", {
        "session": session,
    })


@login_required
def scenario_voice_response_view(request):
    guard = assessment_page_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)
    return render(request, "assessments/scenario_voice_response.html", {
        "session": session,
    })


@login_required
def activity_complete_view(request):
    guard = assessment_page_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)
    fusion = FusionPrediction.objects.filter(screening_session=session).first()

    return render(request, "assessments/activity_complete.html", {
        "session": session,
        "fusion": fusion,
    })


# ============================================================
# BASIC HELPERS
# ============================================================

def env_value(name, default=""):
    value = getattr(settings, name, None)
    if value:
        return str(value).strip().strip("\"'")
    return os.getenv(name, default).strip().strip("\"'")


def seconds(start_time):
    return round(time.time() - start_time, 4)


def api_raise(resp, label):
    if resp.ok:
        return

    try:
        body = resp.json()
    except Exception:
        body = resp.text[:500]

    raise RuntimeError(f"{label} failed with {resp.status_code}: {body}")


def build_api_headers(api_key):
    return {
        "X-API-Key": api_key,
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
    }


def safe_decimal(value, max_value=None, default=None):
    try:
        if value is None or value == "":
            return default
        number = Decimal(str(value))
        if max_value is not None and number > Decimal(str(max_value)):
            return Decimal(str(max_value))
        return number
    except (InvalidOperation, TypeError, ValueError):
        return default


def safe_score(payload, *keys, max_value=100):
    if not isinstance(payload, dict):
        return None

    for key in keys:
        if key in payload:
            return safe_decimal(payload.get(key), max_value=max_value)

    scores = payload.get("scores")
    if isinstance(scores, dict):
        for key in keys:
            if key in scores:
                return safe_decimal(scores.get(key), max_value=max_value)

    return None


def normalize_confidence_value(value):
    """
    Convert API confidence value into DB range 0.00 to 1.00.
    Accepts:
      - 0.87
      - 87
      - "87%"
    """
    if value is None or value == "":
        return None

    if isinstance(value, str):
        value = value.strip().replace("%", "")

    conf = safe_decimal(value, default=None)

    if conf is None:
        return None

    # If API sends percentage like 83.5, normalize to 0.835
    if conf > Decimal("1"):
        conf = conf / Decimal("100")

    if conf > Decimal("1"):
        conf = Decimal("1")

    if conf < Decimal("0"):
        conf = Decimal("0")

    return conf


def safe_confidence(payload):
    """
    Robust confidence parser.

    Many APIs do not return the same confidence key.
    This checks common top-level and nested keys, then falls back to max probability
    from probability/class distribution dictionaries.
    """
    if not isinstance(payload, dict):
        return None

    direct_keys = [
        "confidence_score",
        "confidence",
        "probability",
        "score",
        "model_confidence",
        "prediction_confidence",
        "final_confidence",
    ]

    for key in direct_keys:
        if key in payload:
            conf = normalize_confidence_value(payload.get(key))
            if conf is not None:
                return conf

    nested_keys = [
        "scores",
        "result",
        "prediction",
        "output",
        "data",
        "score_response",
        "model_output",
    ]

    for nested_key in nested_keys:
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            conf = safe_confidence(nested)
            if conf is not None:
                return conf

    probability_keys = [
        "probabilities",
        "class_probabilities",
        "risk_probabilities",
        "prediction_probabilities",
        "label_probabilities",
    ]

    for key in probability_keys:
        values = payload.get(key)
        if isinstance(values, dict) and values:
            parsed = [
                normalize_confidence_value(item)
                for item in values.values()
            ]
            parsed = [item for item in parsed if item is not None]
            if parsed:
                return max(parsed)

    return None


def normalize_risk_label(label):
    label = str(label or "").strip().lower()

    if label in ["low", "normal", "safe", "minimal"]:
        return "low"

    if label in ["moderate", "medium", "mid"]:
        return "moderate"

    if label in ["high", "severe"]:
        return "high"

    if label in ["critical", "emergency", "urgent"]:
        return "critical"

    return None


def pick_final_risk(payload):
    if not isinstance(payload, dict):
        return None

    raw = (
        payload.get("overall_risk")
        or payload.get("risk")
        or payload.get("risk_level")
        or payload.get("label")
        or payload.get("prediction")
        or payload.get("class")
        or payload.get("result")
    )

    return normalize_risk_label(raw)


def safe_vector(value, dimensions):
    """
    Only store pgvector values when the API returns the exact expected length.
    Otherwise return None so runtime does not break.
    """
    if not isinstance(value, list):
        return None

    if len(value) != dimensions:
        return None

    try:
        return [float(item) for item in value]
    except Exception:
        return None


def pick_embedding(payload, dimensions):
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("embedding_vector"),
        payload.get("embedding"),
        payload.get("vector"),
        payload.get("features"),
    ]

    for candidate in candidates:
        vector = safe_vector(candidate, dimensions)
        if vector is not None:
            return vector

    return None


# ============================================================
# SESSION HELPER
# ============================================================

def get_active_screening_session(request):
    session_id = request.session.get("screening_session_id")

    if session_id:
        session = PlatformScreeningSession.objects.filter(
            screening_session_id=session_id,
            user=request.user,
            deleted_at__isnull=True,
        ).first()

        if session:
            return session

    session = PlatformScreeningSession.objects.create(
        user=request.user,
        session_status="started",
        current_activity="face_video",
        workflow_stage=1,
        completed_activities_count=0,
    )

    request.session["screening_session_id"] = str(session.screening_session_id)
    return session


# Backward-compatible name, in case old code imports this helper.
get_active_multimodal_session = get_active_screening_session


@login_required
def start_multimodal_session(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = PlatformScreeningSession.objects.create(
        user=request.user,
        session_status="started",
        current_activity="face_video",
        workflow_stage=1,
        completed_activities_count=0,
    )

    request.session["screening_session_id"] = str(session.screening_session_id)

    return JsonResponse({
        "ok": True,
        "message": "Screening session started.",
        "session_id": str(session.screening_session_id),
    })


# ============================================================
# STORAGE HELPERS
# ============================================================

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
):
    metadata = storage_data.get("metadata") or {}
    if extra_metadata:
        metadata.update(extra_metadata)

    return MediaAsset.objects.create(
        user=request.user,
        media_type=media_type,
        file_name=getattr(file_obj, "name", "upload"),
        content_type=getattr(file_obj, "content_type", "") or "application/octet-stream",
        size_bytes=getattr(file_obj, "size", 0) or 0,
        storage_provider=storage_data["storage_provider"],
        bucket_name=storage_data.get("bucket_name") or "",
        object_key=storage_data["object_key"],
        cdn_url=storage_data.get("file_url") or "",
        upload_status="completed",
        metadata_json=metadata,
    )


def get_local_media_absolute_path(media_asset):
    if not media_asset or media_asset.storage_provider != "local":
        return ""

    media_root = getattr(settings, "MEDIA_ROOT", None)

    if not media_root:
        raise RuntimeError("MEDIA_ROOT is missing.")

    return str(Path(media_root) / media_asset.object_key)


# ============================================================
# VIDEO COMPRESSION HELPERS
# ============================================================

def compress_video_for_face_api(input_path):
    if not input_path:
        raise RuntimeError("Input video path missing for compression.")

    input_path = str(input_path)

    if not os.path.exists(input_path):
        raise RuntimeError(f"Input video file not found: {input_path}")

    output_dir = tempfile.mkdtemp(prefix="mindspace_face_compress_")
    output_path = os.path.join(output_dir, f"{uuid.uuid4()}.mp4")

    command = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "scale='min(480,iw)':-2,fps=12",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=900,
        )
    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed. Install it using: sudo apt install ffmpeg")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Video compression timed out.")

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg compression failed: {result.stderr[-1200:]}")

    return output_path


def cleanup_temp_file(file_path):
    if not file_path:
        return

    try:
        if os.path.exists(file_path):
            parent_dir = os.path.dirname(file_path)
            os.remove(file_path)
            if parent_dir and os.path.isdir(parent_dir):
                try:
                    os.rmdir(parent_dir)
                except Exception:
                    pass
    except Exception:
        pass


def convert_audio_to_wav(input_file):
    """
    Convert browser-recorded audio/webm or audio/ogg to clean WAV before
    sending to the Voice Feature Extraction API.

    Output:
      - mono
      - 16000 Hz
      - PCM 16-bit WAV

    This fixes API errors like:
      Format not recognised
      Error opening /tmp/tmpxxxx.wav
    """
    input_suffix = ".webm"

    original_name = getattr(input_file, "name", "") or ""
    if "." in original_name:
        input_suffix = "." + original_name.split(".")[-1].lower()

    temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix)
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")

    temp_input_path = temp_input.name
    temp_output_path = temp_output.name

    try:
        input_file.seek(0)
        temp_input.write(input_file.read())
        temp_input.flush()
        temp_input.close()
        temp_output.close()

        command = [
            "ffmpeg",
            "-y",
            "-i", temp_input_path,
            "-ac", "1",
            "-ar", "16000",
            "-sample_fmt", "s16",
            temp_output_path,
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Audio WAV conversion failed. "
                f"FFmpeg error: {result.stderr[-1200:]}"
            )

        if not os.path.exists(temp_output_path) or os.path.getsize(temp_output_path) <= 44:
            raise RuntimeError("Audio WAV conversion produced an empty/invalid WAV file.")

        return temp_output_path

    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed. Install it using: sudo apt install ffmpeg")

    finally:
        try:
            if os.path.exists(temp_input_path):
                os.remove(temp_input_path)
        except Exception:
            pass


# ============================================================
# SARVAM STT
# ============================================================

def transcribe_with_sarvam(file_obj, suffix=".webm", language_code="unknown"):
    try:
        from sarvamai import SarvamAI
    except Exception as exc:
        raise RuntimeError(f"sarvamai package not installed: {exc}")

    api_key = env_value("SARVAM_API_KEY")
    model = env_value("SARVAM_STT_MODEL", "saaras:v3")

    if not api_key:
        raise RuntimeError("SARVAM_API_KEY missing in .env/settings.py")

    file_obj.seek(0)
    audio_bytes = file_obj.read()

    with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as temp_file:
        temp_file.write(audio_bytes)
        temp_file.flush()

        client = SarvamAI(api_subscription_key=api_key)

        try:
            with open(temp_file.name, "rb") as audio_file:
                response = client.speech_to_text.transcribe(
                    file=audio_file,
                    model=model,
                    language_code=language_code,
                )
        except Exception as exc:
            raise RuntimeError(f"Sarvam transcription failed: {exc}")

    transcript = (getattr(response, "transcript", "") or "").strip()
    detected_language = (getattr(response, "language_code", None) or "unknown").strip()

    if not transcript:
        raise RuntimeError("Sarvam returned empty transcript")

    return {
        "transcript": transcript,
        "language_code": detected_language,
        "model": model,
    }


# ============================================================
# FEATURE HELPERS
# ============================================================

def safe_float(value):
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def pick_feature_payload(payload):
    if not isinstance(payload, dict):
        return {}

    if isinstance(payload.get("features"), dict):
        return payload["features"]

    if isinstance(payload.get("vector"), dict):
        return payload["vector"]

    if isinstance(payload.get("data"), dict):
        return payload["data"]

    return payload


def align_features(raw_features):
    if not isinstance(raw_features, dict):
        return {}

    aligned = {}

    for key, value in raw_features.items():
        if isinstance(value, (dict, list)):
            continue
        aligned[key] = safe_float(value)

    return aligned



def sort_pca_component_keys(components):
    """
    Sort PCA component keys in PC1, PC2, ... PC24 order.
    """
    def key_order(key):
        key_str = str(key).strip().lower()
        if key_str.startswith("pc") and key_str[2:].isdigit():
            return int(key_str[2:])
        return 999

    return sorted(components.keys(), key=key_order)


def pick_pca_components(payload):
    """
    Return PCA components as a dict because the voice classifier API expects:
        {"features": {"PC1": value, "PC2": value, ...}}

    Supports:
      {"components": {"PC1": ...}}
      {"data": {"components": {"PC1": ...}}}
    """
    if not isinstance(payload, dict):
        return {}

    components = payload.get("components")

    if not isinstance(components, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            components = data.get("components")

    if not isinstance(components, dict):
        return {}

    ordered = {}
    for key in sort_pca_component_keys(components):
        try:
            ordered[str(key)] = float(components[key])
        except Exception:
            return {}

    return ordered


def pick_pca_features(payload):
    """
    Extract PCA features as a list for DB storage/counting.
    The classifier API still receives the original components dict.
    """
    components = pick_pca_components(payload)
    if components:
        return [components[key] for key in sort_pca_component_keys(components)]

    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("pca_features"),
        payload.get("features"),
        payload.get("reduced_features"),
        payload.get("pca_vector"),
        payload.get("vector"),
    ]

    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([
            data.get("pca_features"),
            data.get("features"),
            data.get("reduced_features"),
            data.get("pca_vector"),
            data.get("vector"),
        ])

    for candidate in candidates:
        if isinstance(candidate, list):
            try:
                return [float(item) for item in candidate]
            except Exception:
                return []

    return []



def normalize_text(text):
    text = str(text or "").strip().lower()
    text = text.replace("।", "")
    text = text.replace(".", "")
    text = text.replace(",", "")
    text = text.replace("'", "")
    text = text.replace('"', "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def transcript_matches_expected(transcript, accepted_values):
    transcript_norm = normalize_text(transcript)

    for value in accepted_values:
        value_norm = normalize_text(value)

        if not value_norm:
            continue

        if transcript_norm == value_norm:
            return True

        if value_norm in transcript_norm:
            return True

    return False


# ============================================================
# API CALLS
# ============================================================

def normalize_endpoint_url(url, suffix):
    """
    If settings contain only host/port, append the expected path.
    If settings already contain a path, keep it.
    """
    url = str(url or "").strip().rstrip("/")
    if not url:
        return ""
    if "/" in url.replace("http://", "").replace("https://", ""):
        return url
    return url + suffix


def post_face_extract(video_file, filename=None, content_type=None):
    url = env_value("FACE_EXTRACT_URL")
    api_key = env_value("FACE_VIDEO_FEATURE_EXTRACTION_API_KEY") or env_value("EXTRACTION_API_KEY")

    if not url:
        raise RuntimeError("FACE_EXTRACT_URL missing in settings.py/.env")

    if not api_key:
        raise RuntimeError("FACE_VIDEO_FEATURE_EXTRACTION_API_KEY missing in settings.py/.env")

    headers = build_api_headers(api_key)

    if not api_key or api_key.startswith("your-") or api_key.startswith("PASTE_"):
        raise RuntimeError(
            "Face Extract API key is missing or still using placeholder value. "
            "Set FACE_VIDEO_FEATURE_EXTRACTION_API_KEY in .env"
        )
    video_file.seek(0)

    upload_filename = filename or os.path.basename(getattr(video_file, "name", "face_video.mp4"))
    upload_content_type = content_type or getattr(video_file, "content_type", "video/mp4") or "video/mp4"

    files = {
        "video": (
            upload_filename,
            video_file,
            upload_content_type,
        )
    }

    start = time.time()

    try:
        resp = requests.post(url, headers=headers, files=files, timeout=(30, 1800))
    except requests.exceptions.ConnectTimeout:
        raise RuntimeError(f"Face Extract API connection timed out: {url}")
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(f"Face Extract API did not return result in time: {url}")
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Face Extract API connection aborted. URL: {url}. Error: {exc}")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Face Extract API request failed. URL: {url}. Error: {exc}")

    latency = seconds(start)
    api_raise(resp, "Face feature extraction")

    return resp.json(), latency


def get_face_vector(session_id):
    template = env_value("FACE_EXTRACT_SESSION_VECTOR_URL_TEMPLATE") or env_value("FACE_VECTOR_URL_TEMPLATE")
    api_key = env_value("FACE_VIDEO_FEATURE_EXTRACTION_API_KEY") or env_value("EXTRACTION_API_KEY")

    if not template:
        # Some APIs return vector/features directly in post_face_extract response.
        return {}, 0

    if not api_key:
        raise RuntimeError("FACE_VIDEO_FEATURE_EXTRACTION_API_KEY missing in settings.py/.env")

    url = template.format(session_id=session_id)
    headers = build_api_headers(api_key)

    start = time.time()
    last_response = None

    for _ in range(300):
        try:
            resp = requests.get(url, headers=headers, timeout=(10, 60))
        except requests.exceptions.RequestException as exc:
            last_response = str(exc)
            time.sleep(5)
            continue

        if resp.status_code == 200:
            return resp.json(), seconds(start)

        try:
            last_response = resp.json()
        except Exception:
            last_response = resp.text[:300]

        time.sleep(5)

    raise RuntimeError(f"Face vector not ready after polling. Last response: {last_response}")


def post_face_score(face_vector):
    url = env_value("FACE_SCORE_URL")
    api_key = env_value("FACE_VIDEO_FEATURE_TO_MH_API_KEY") or env_value("SCORING_API_KEY")

    if not url:
        raise RuntimeError("FACE_SCORE_URL missing in settings.py/.env")

    if not api_key:
        raise RuntimeError("FACE_VIDEO_FEATURE_TO_MH_API_KEY missing in settings.py/.env")

    url = normalize_endpoint_url(url, "/predict")

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"

    start = time.time()
    resp = requests.post(url, headers=headers, json={"vector": face_vector}, timeout=(30, 900))
    latency = seconds(start)

    api_raise(resp, "Face scoring")
    return resp.json(), latency


def post_voice_extract(audio_file):
    """
    Browser records audio as WebM/Opus. Most acoustic feature APIs expect WAV.
    So we convert the uploaded audio to WAV before sending it to the extraction API.
    """
    url = normalize_endpoint_url(
        env_value("VOICE_EXTRACT_URL", "http://88.222.12.15:5800/extract"),
        "/extract",
    )

    api_key = env_value("VOICE_FEATURE_EXTRACT_API_KEY") or env_value("AUDIO_API_KEY")

    if not api_key:
        raise RuntimeError("VOICE_FEATURE_EXTRACT_API_KEY missing")

    wav_path = ""

    try:
        wav_path = convert_audio_to_wav(audio_file)

        headers = build_api_headers(api_key)

        with open(wav_path, "rb") as wav_file:
            files = {
                "file": (
                    "phonation.wav",
                    wav_file,
                    "audio/wav",
                )
            }

            start = time.time()
            resp = requests.post(
                url,
                headers=headers,
                files=files,
                timeout=(30, 900),
            )
            latency = seconds(start)

        api_raise(resp, "Voice feature extraction")
        return resp.json(), latency

    finally:
        try:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)
        except Exception:
            pass


def post_voice_pca(raw_voice_features):
    """
    Send 6373 raw voice features to PCA API.
    PCA API returns 24 reduced features.
    """
    url = normalize_endpoint_url(
        env_value("VOICE_PCA_URL", "http://88.222.12.15:5900/process"),
        "/process",
    )

    api_key = (
        env_value("VOICE_PCA_API_KEY")
        or env_value("VOICE_FEATURE_TO_MH")
        or env_value("AUDIO_API_KEY")
        or env_value("API_KEY")
    )

    if not url:
        raise RuntimeError("VOICE_PCA_URL missing in settings.py/.env")

    if not api_key:
        raise RuntimeError("VOICE_PCA_API_KEY missing in settings.py/.env")

    if not isinstance(raw_voice_features, dict):
        raise RuntimeError("PCA input must be a dictionary of 6373 voice features.")

    if len(raw_voice_features) != 6373:
        raise RuntimeError(
            f"PCA input must contain exactly 6373 features. Received {len(raw_voice_features)}."
        )

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"

    start = time.time()

    payloads = [
        {"features": raw_voice_features},
        {"voice_features": raw_voice_features},
        {"raw_features": raw_voice_features},
    ]

    last_error = None

    for payload in payloads:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=(30, 900))
            latency = seconds(start)

            if resp.ok:
                return resp.json(), latency

            try:
                last_error = resp.json()
            except Exception:
                last_error = resp.text[:500]

        except requests.exceptions.RequestException as exc:
            last_error = str(exc)

    raise RuntimeError(f"Voice PCA pipeline failed. Last error: {last_error}")


def post_voice_score(pca_components):
    """
    Send PCA components to the Voice Classifier API.

    Swagger-confirmed API format:
        POST /predict
        Body:
        {
            "PC1": value,
            "PC2": value,
            ...
            "PC24": value
        }

    Important:
        Do NOT wrap the payload inside {"features": ...}
    """
    url = normalize_endpoint_url(
        env_value("VOICE_SCORE_URL", "http://88.222.212.15:5600/predict"),
        "/predict",
    )

    api_key = (
        env_value("VOICE_FEATURE_TO_MH")
        or env_value("VOICE_SCORE_API_KEY")
        or env_value("AUDIO_API_KEY")
        or env_value("API_KEY")
    )

    if not url:
        raise RuntimeError("VOICE_SCORE_URL missing in settings.py/.env")

    if not api_key:
        raise RuntimeError("VOICE_FEATURE_TO_MH or VOICE_SCORE_API_KEY missing in settings.py/.env")

    if not isinstance(pca_components, dict):
        raise RuntimeError("Voice Score API expects PCA components as a dictionary.")

    if len(pca_components) != 24:
        raise RuntimeError(
            f"Voice Score API expects exactly 24 PCA components. Received {len(pca_components)}."
        )

    # Ensure body contains PC1..PC24 as top-level JSON keys.
    payload = {}
    for key in sort_pca_component_keys(pca_components):
        payload[str(key)] = float(pca_components[key])

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"
    headers["accept"] = "application/json"

    start = time.time()

    try:
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=(30, 900),
        )
        latency = seconds(start)
        api_raise(resp, "Voice scoring")
        return resp.json(), latency

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Voice scoring request failed. URL: {url}. Error: {exc}")


def post_text_extract(transcript):
    url = normalize_endpoint_url(env_value("TEXT_EXTRACT_URL", "http://88.222.12.15:8025/analyze"), "/analyze")
    api_key = env_value("TEXT_PARAMETER_EXTRACT_API_KEY") or env_value("TEXT_ANALYSIS_API_KEY")

    if not api_key:
        raise RuntimeError("TEXT_PARAMETER_EXTRACT_API_KEY missing")

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"

    conversation_text = str(transcript or "").strip()

    if not conversation_text:
        raise RuntimeError("Empty transcript for text extraction")

    if not conversation_text.lower().startswith("client:"):
        conversation_text = f"Client: {conversation_text}"

    start = time.time()

    resp = requests.post(
        url,
        headers=headers,
        json={"conversation": conversation_text},
        timeout=(30, 900),
    )

    if not resp.ok:
        resp = requests.post(
            url,
            headers=headers,
            json={"text": conversation_text},
            timeout=(30, 900),
        )

    latency = seconds(start)
    api_raise(resp, "Text parameter extraction")
    return resp.json(), latency


def post_text_score(text_features):
    url = normalize_endpoint_url(env_value("TEXT_SCORE_URL", "http://88.222.12.15:9000/predict"), "/predict")
    api_key = env_value("TEXT_ANALYSIS_API_KEY") or env_value("API_KEY")

    if not api_key:
        raise RuntimeError("TEXT_ANALYSIS_API_KEY missing")

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"

    start = time.time()
    resp = requests.post(url, headers=headers, json=text_features, timeout=(30, 900))

    if not resp.ok:
        resp = requests.post(url, headers=headers, json={"features": text_features}, timeout=(30, 900))

    latency = seconds(start)
    api_raise(resp, "Text scoring")
    return resp.json(), latency


def post_fusion_score(combined_features):
    url = normalize_endpoint_url(env_value("FUSION_SCORE_URL", "http://88.222.12.15:8000/predict"), "/predict")
    api_key = env_value("MODEL_API_KEY")

    if not api_key:
        raise RuntimeError("MODEL_API_KEY missing")

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"

    start = time.time()
    resp = requests.post(url, headers=headers, json={"features": combined_features}, timeout=(30, 900))
    latency = seconds(start)

    api_raise(resp, "Fusion scoring")
    return resp.json(), latency


# ============================================================
# DB RESULT CREATION HELPERS
# ============================================================

def get_or_create_default_video_activity(activity_id="", title="", prompt=""):
    activity_code = activity_id or "face_video_default"

    activity, _ = VideoActivity.objects.get_or_create(
        activity_code=activity_code,
        defaults={
            "title": title or "Face Video Activity",
            "instruction_text": prompt or "Record the requested face activity.",
            "image_set_json": {},
            "is_active": True,
        },
    )

    return activity


def get_or_create_phonation_sound(expected_label="", expected_prompt=""):
    character = expected_label or expected_prompt or "unknown"
    sound_code = str(character).strip() or "unknown"

    sound = PhonationSound.objects.filter(sound_character=sound_code).first()

    if sound:
        return sound

    next_order = PhonationSound.objects.count() + 1

    return PhonationSound.objects.create(
        language_code="hi",
        sound_character=sound_code,
        sound_name=expected_prompt or sound_code,
        sound_order=next_order,
    )


def get_or_create_audio_scenario(scenario_id=""):
    scenario_code = scenario_id or "default_scenario"

    scenario, _ = AudioScenario.objects.get_or_create(
        scenario_code=scenario_code,
        defaults={
            "title": "Scenario Voice Response",
            "prompt_text": "Respond to the scenario in your own words.",
            "is_active": True,
        },
    )

    return scenario


def make_json_safe(value):
    """
    PostgreSQL JSONField should not receive Decimal, UUID, datetime, or model objects directly.
    This helper converts nested values into JSON-safe values before saving.
    """
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, uuid.UUID):
        return str(value)

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [make_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]

    return value



def create_pca_pipeline_result_safe(
    *,
    screening_session,
    phonation_feature,
    raw_features,
    pca_response,
    pca_features,
    pca_components=None,
    latency=None,
):
    """
    Save PCA pipeline result safely.

    Important:
      - pca_pipeline_results.screening_session_id is NOT NULL in your DB
      - so screening_session must always be passed
      - raw input is 6373 voice features
      - PCA output is 24 components/features
    """
    model_fields = {field.name for field in PcaPipelineResult._meta.fields}

    raw_feature_count = len(raw_features) if isinstance(raw_features, dict) else 0
    pca_feature_count = len(pca_features) if isinstance(pca_features, list) else 0
    pca_component_count = len(pca_components) if isinstance(pca_components, dict) else 0

    possible_values = {
        # Required relation in your DB
        "screening_session": screening_session,

        # Optional relation depending on your model
        "phonation_feature": phonation_feature,
        "feature": phonation_feature,

        # Counts
        "input_feature_count": raw_feature_count,
        "raw_feature_count": raw_feature_count,
        "output_feature_count": pca_feature_count or pca_component_count,
        "pca_feature_count": pca_feature_count,
        "pca_component_count": pca_component_count,

        # JSON payloads
        "input_features_json": raw_features,
        "raw_features_json": raw_features,
        "pca_response_json": pca_response,
        "response_json": pca_response,
        "pca_components_json": pca_components or {},

        # PCA values
        "pca_features": pca_features,
        "reduced_features": pca_features,
        "pca_vector": pca_features,
        "pca_components": pca_components or {},

        # Timing/status
        "processing_time_seconds": safe_decimal(latency, default=None),
        "latency_seconds": safe_decimal(latency, default=None),
        "pipeline_status": "completed",
        "status": "completed",
        "processed_at": timezone.now(),
    }

    data = {}

    for field_name, value in possible_values.items():
        if field_name not in model_fields:
            continue

        if field_name in ["screening_session", "phonation_feature", "feature"]:
            data[field_name] = value
        else:
            data[field_name] = make_json_safe(value)

    return PcaPipelineResult.objects.create(**data)



def model_uuid_or_pk(instance):
    if not instance:
        return None

    for field_name in [
        "result_id",
        "prediction_id",
        "feature_id",
        "media_id",
        "session_id",
        "attempt_id",
        "text_parameter_id",
        "transcript_id",
        "id",
        "pk",
    ]:
        value = getattr(instance, field_name, None)
        if value:
            return str(value)

    return str(getattr(instance, "pk", ""))


def result_score_summary(result_obj):
    if not result_obj:
        return {}

    summary = {}

    for field_name in [
        "stress_score",
        "depression_score",
        "anxiety_score",
        "speech_impairment_score",
        "confidence_score",
        "risk_label",
        "api_version",
        "processed_at",
    ]:
        if hasattr(result_obj, field_name):
            value = getattr(result_obj, field_name)
            if value is not None and value != "":
                summary[field_name] = make_json_safe(value)

    return summary


def derive_confidence_from_result_and_payload(result_obj=None, payload=None, explicit_confidence=None):
    """
    Final fallback resolver for modality_results.confidence_score.

    Priority:
      1. explicit confidence passed to create_modality_result()
      2. result_obj.confidence_score
      3. payload.summary.confidence_score
      4. payload.score_response confidence/probability keys
      5. whole payload confidence/probability keys
      6. fallback: 1.00 when API succeeded but no confidence is returned

    The last fallback prevents NULL in modality_results when the model API gives
    valid scores but no confidence field.
    """
    conf = normalize_confidence_value(explicit_confidence)
    if conf is not None:
        return conf

    if result_obj is not None and hasattr(result_obj, "confidence_score"):
        conf = normalize_confidence_value(getattr(result_obj, "confidence_score", None))
        if conf is not None:
            return conf

    payload = payload or {}

    if isinstance(payload, dict):
        summary = payload.get("summary")
        if isinstance(summary, dict):
            conf = safe_confidence(summary)
            if conf is not None:
                return conf

        score_response = payload.get("score_response")
        if isinstance(score_response, dict):
            conf = safe_confidence(score_response)
            if conf is not None:
                return conf

        conf = safe_confidence(payload)
        if conf is not None:
            return conf

        # API produced score_response but did not expose confidence.
        # Store 1.00 as "accepted successful API result", instead of NULL.
        if isinstance(score_response, dict) and score_response:
            return Decimal("1.00")

    return Decimal("1.00")


def create_modality_result(*, session, modality, result_obj, payload, confidence=None):
    """
    Create or update one clean row per screening session + modality.

    This keeps modality_results useful:
      - modality = face / voice / text
      - correct FK column filled
      - confidence_score never stays NULL for successful results
      - result_payload is JSON-safe
      - avoids duplicate modality rows when user retries the same activity
    """
    modality = str(modality or "").strip().lower()

    if modality not in ["face", "voice", "text"]:
        raise ValueError(f"Invalid modality: {modality}")

    final_confidence = derive_confidence_from_result_and_payload(
        result_obj=result_obj,
        payload=payload,
        explicit_confidence=confidence,
    )

    safe_payload = make_json_safe(payload or {})
    safe_payload["modality"] = modality
    safe_payload["screening_session_id"] = str(session.screening_session_id)
    safe_payload["linked_result_id"] = model_uuid_or_pk(result_obj)
    safe_payload["result_summary"] = result_score_summary(result_obj)
    safe_payload["resolved_confidence_score"] = make_json_safe(final_confidence)
    safe_payload["saved_at"] = timezone.now().isoformat()

    defaults = {
        "confidence_score": final_confidence,
        "result_payload": safe_payload,
        "face_result": None,
        "voice_result": None,
        "text_result": None,
    }

    if modality == "face":
        defaults["face_result"] = result_obj
    elif modality == "voice":
        defaults["voice_result"] = result_obj
    elif modality == "text":
        defaults["text_result"] = result_obj

    modality_result, created = ModalityResult.objects.update_or_create(
        screening_session=session,
        modality=modality,
        defaults=defaults,
    )

    return modality_result


def update_session_progress(session, *, current_activity, completed_count, status="processing"):
    session.session_status = status
    session.current_activity = current_activity
    session.completed_activities_count = max(
        session.completed_activities_count or 0,
        completed_count,
    )

    if completed_count <= 0:
        session.workflow_stage = 1
    elif completed_count == 1:
        session.workflow_stage = 2
    elif completed_count == 2:
        session.workflow_stage = 3
    elif completed_count >= 3:
        session.workflow_stage = 4

    session.save(update_fields=[
        "session_status",
        "current_activity",
        "completed_activities_count",
        "workflow_stage",
    ])


def mark_session_failed(session, error):
    session.session_status = "failed"
    session.current_activity = "error"

    update_fields = ["session_status", "current_activity"]

    if hasattr(session, "metadata_json"):
        existing_metadata = session.metadata_json or {}
        existing_metadata["last_error"] = str(error)
        existing_metadata["failed_at"] = timezone.now().isoformat()
        session.metadata_json = existing_metadata
        update_fields.append("metadata_json")

    session.save(update_fields=update_fields)


# ============================================================
# ACTIVITY 1: FACE VIDEO
# ============================================================

@login_required
@require_POST
@csrf_protect
def upload_face_video(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    activity_id = request.POST.get("activity_id", "").strip()
    activity_title = request.POST.get("activity_title", "").strip()
    activity_prompt = request.POST.get("activity_prompt", "").strip()

    video_file = request.FILES.get("video")

    if not video_file:
        return JsonResponse({
            "ok": False,
            "error": "No video file received. Send file using form field name: video",
        }, status=400)

    duration_seconds = request.POST.get("duration_seconds", "0")

    try:
        duration_seconds = float(duration_seconds)
    except Exception:
        duration_seconds = 0

    if duration_seconds < MIN_FACE_VIDEO_SECONDS:
        return JsonResponse({
            "ok": False,
            "error": f"Face video must be at least {MIN_FACE_VIDEO_SECONDS} seconds.",
            "required_seconds": MIN_FACE_VIDEO_SECONDS,
            "received_seconds": duration_seconds,
        }, status=400)

    compressed_video_path = ""
    compressed_size = 0

    try:
        storage_data = save_uploaded_activity_file(
            file_obj=video_file,
            user_id=request.user.id,
            activity_type="face-video",
            original_filename=video_file.name,
            content_type=video_file.content_type or "video/webm",
        )

        media = create_media_asset(
            request=request,
            media_type="activity_video",
            file_obj=video_file,
            storage_data=storage_data,
            activity_type="face-video",
            extra_metadata={
                "activity_id": activity_id,
                "activity_title": activity_title,
                "activity_prompt": activity_prompt,
                "duration_seconds": duration_seconds,
                "required_duration_seconds": MIN_FACE_VIDEO_SECONDS,
            },
        )

        activity = get_or_create_default_video_activity(activity_id, activity_title, activity_prompt)

        video_session = VideoSession.objects.create(
            screening_session=session,
            video_activity=activity,
            media=media,
            extraction_status="processing",
            analysis_status="pending",
            session_status="processing",
            processing_started_at=timezone.now(),
        )

        api_file = None

        if media.storage_provider == "local":
            original_video_path = get_local_media_absolute_path(media)
            compressed_video_path = compress_video_for_face_api(original_video_path)
            compressed_size = os.path.getsize(compressed_video_path)
            api_file = open(compressed_video_path, "rb")
            api_filename = "compressed_face_video.mp4"
            api_content_type = "video/mp4"
        else:
            video_file.seek(0)
            api_file = video_file
            api_filename = video_file.name
            api_content_type = video_file.content_type or "video/webm"

        try:
            extract_response, extract_latency = post_face_extract(
                api_file,
                filename=api_filename,
                content_type=api_content_type,
            )
        finally:
            if media.storage_provider == "local" and api_file:
                api_file.close()

        face_api_session_id = extract_response.get("session_id") or extract_response.get("id")

        if face_api_session_id:
            vector_response, vector_latency = get_face_vector(face_api_session_id)
            if not vector_response:
                vector_response = extract_response
        else:
            vector_response = extract_response
            vector_latency = 0

        raw_vector = pick_feature_payload(vector_response)
        aligned_vector = align_features(raw_vector)

        score_response, score_latency = post_face_score(aligned_vector)

        face_feature = FaceFeatureVector.objects.create(
            video_session=video_session,
            frame_number=0,
            face_landmarks=vector_response.get("face_landmarks") if isinstance(vector_response, dict) else None,
            emotion_scores=vector_response.get("emotion_scores") if isinstance(vector_response, dict) else None,
            head_pose=vector_response.get("head_pose") if isinstance(vector_response, dict) else None,
            eye_tracking=vector_response.get("eye_tracking") if isinstance(vector_response, dict) else None,
            blink_rate=safe_decimal(aligned_vector.get("blink_rate"), default=None),
            embedding_vector=pick_embedding(vector_response, 512),
            model_version=str(extract_response.get("model_version", "")) if isinstance(extract_response, dict) else "",
            api_processed_at=timezone.now(),
        )

        facial_result = FacialAnalysisResult.objects.create(
            feature=face_feature,
            stress_score=safe_score(score_response, "stress_score", "stress"),
            depression_score=safe_score(score_response, "depression_score", "depression"),
            anxiety_score=safe_score(score_response, "anxiety_score", "anxiety"),
            confidence_score=safe_confidence(score_response),
            risk_label=str(
                score_response.get("risk_label")
                or score_response.get("label")
                or score_response.get("prediction")
                or ""
            ),
            api_version=str(score_response.get("api_version", "")),
            processed_at=timezone.now(),
        )

        payload = {
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "extract_response": extract_response,
            "vector_response": vector_response,
            "aligned_features": aligned_vector,
            "score_response": score_response,
            "summary": {
                "stress_score": make_json_safe(facial_result.stress_score),
                "depression_score": make_json_safe(facial_result.depression_score),
                "anxiety_score": make_json_safe(facial_result.anxiety_score),
                "confidence_score": make_json_safe(facial_result.confidence_score),
                "risk_label": facial_result.risk_label,
            },
            "latency": {
                "face_extract_post_s": extract_latency,
                "face_vector_get_s": vector_latency,
                "face_score_post_s": score_latency,
                "original_file_size": video_file.size,
                "compressed_file_size": compressed_size,
                "compression_enabled": bool(compressed_video_path),
            },
        }

        create_modality_result(
            session=session,
            modality="face",
            result_obj=facial_result,
            payload=payload,
            confidence=facial_result.confidence_score,
        )

        video_session.extraction_status = "completed"
        video_session.analysis_status = "completed"
        video_session.session_status = "completed"
        video_session.processing_completed_at = timezone.now()
        video_session.completed_at = timezone.now()
        video_session.save()

        update_session_progress(
            session,
            current_activity="voice_phonation",
            completed_count=1,
            status="processing",
        )

        return JsonResponse({
            "ok": True,
            "message": "Face video compressed and processed successfully.",
            "session_id": str(session.screening_session_id),
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "original_file_size": video_file.size,
            "compressed_file_size": compressed_size,
            "face_score": score_response,
            "redirect_url": "/assessments/voice-phonation/",
        })

    except Exception as exc:
        mark_session_failed(session, exc)
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    finally:
        cleanup_temp_file(compressed_video_path)


# ============================================================
# ACTIVITY 2: VOICE PHONATION
# ============================================================

@login_required
@require_POST
@csrf_protect
def upload_voice_phonation(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)
    audio_file = request.FILES.get("audio")

    if not audio_file:
        return JsonResponse({
            "ok": False,
            "error": "No audio file received. Send file using form field name: audio",
        }, status=400)

    expected_label = request.POST.get("expected_label", "").strip()
    expected_prompt = request.POST.get("expected_prompt", "").strip()
    accepted_values_raw = request.POST.get("accepted_values", "[]")

    try:
        accepted_values = json.loads(accepted_values_raw)
        if not isinstance(accepted_values, list):
            accepted_values = []
    except Exception:
        accepted_values = []

    try:
        volume_score = float(request.POST.get("volume_score", 0) or 0)
    except Exception:
        volume_score = 0.0

    try:
        hold_ms = int(float(request.POST.get("hold_ms", 0) or 0))
    except Exception:
        hold_ms = 0

    try:
        baseline_noise_level = float(request.POST.get("baseline_noise_level", 0) or 0)
    except Exception:
        baseline_noise_level = 0.0

    try:
        storage_data = save_uploaded_activity_file(
            file_obj=audio_file,
            user_id=request.user.id,
            activity_type="voice-phonation",
            original_filename=audio_file.name,
            content_type=audio_file.content_type or "audio/webm",
        )

        media = create_media_asset(
            request=request,
            media_type="phonation_audio",
            file_obj=audio_file,
            storage_data=storage_data,
            activity_type="voice-phonation",
            extra_metadata={
                "expected_label": expected_label,
                "expected_prompt": expected_prompt,
                "accepted_values": accepted_values,
                "volume_score": volume_score,
                "hold_ms": hold_ms,
                "baseline_noise_level": baseline_noise_level,
            },
        )

        phonation_session, _ = PhonationSession.objects.get_or_create(
            screening_session=session,
            defaults={"session_status": "processing"},
        )

        sound = get_or_create_phonation_sound(expected_label, expected_prompt)

        if volume_score < 30:
            return JsonResponse({
                "ok": False,
                "passed": False,
                "reason": "Voice strength too low. Please speak a little louder and try again.",
            }, status=400)

        if hold_ms < 900:
            return JsonResponse({
                "ok": False,
                "passed": False,
                "reason": "Sound was not held long enough.",
            }, status=400)

        # For vocal-cord phonation analysis, transcript verification is optional.
        # Sustained sounds like आ, ई, ऊ, म are often not transcribed reliably by STT.
        # Default: skip STT and continue to Voice Feature Extraction -> PCA -> Scoring.
        use_stt_verification = str(
            env_value("VOICE_PHONATION_USE_STT", "False")
        ).strip().lower() in ["1", "true", "yes", "on"]

        transcript = ""
        language_code = "unknown"
        transcription = {
            "skipped": True,
            "reason": "VOICE_PHONATION_USE_STT is False. Using acoustic feature pipeline only.",
        }

        if use_stt_verification:
            suffix = ".webm"
            if audio_file.name and "." in audio_file.name:
                suffix = "." + audio_file.name.split(".")[-1].lower()

            audio_file.seek(0)
            transcription = transcribe_with_sarvam(
                audio_file,
                suffix=suffix,
                language_code="unknown",
            )

            transcript = transcription.get("transcript", "")
            language_code = transcription.get("language_code", "unknown")

            matched = transcript_matches_expected(transcript, accepted_values) if accepted_values else True

            if not matched:
                media.metadata_json = {
                    **(media.metadata_json or {}),
                    "transcript": transcript,
                    "transcript_language": language_code,
                    "verification_status": "failed",
                    "verification_reason": f"Transcript did not match expected sound. Transcript: {transcript}",
                }
                media.save(update_fields=["metadata_json"])

                return JsonResponse({
                    "ok": False,
                    "passed": False,
                    "transcript": transcript,
                    "reason": media.metadata_json["verification_reason"],
                }, status=400)

        # One row per sound per phonation session.
        # If the user retries the same sound, update the existing row instead of crashing
        # on unique constraint: phonation_session_id + sound_id.
        attempt, _ = PhonationAttempt.objects.update_or_create(
            phonation_session=phonation_session,
            sound=sound,
            defaults={
                "media": media,
                "pronunciation_detected": True,
                "character_accuracy_score": Decimal("100.00"),
                "noise_level": safe_decimal(baseline_noise_level, default=Decimal("0")),
                "silence_duration_ms": 0,
                "response_time_ms": hold_ms,
            },
        )

        audio_file.seek(0)
        extract_response, extract_latency = post_voice_extract(audio_file)

        raw_features = pick_feature_payload(extract_response)
        aligned_features = align_features(raw_features)

        if len(aligned_features) != 6373:
            raise RuntimeError(
                f"Voice Feature Extract API returned {len(aligned_features)} features. "
                "Expected exactly 6373 features before PCA."
            )

        pca_response, pca_latency = post_voice_pca(aligned_features)
        pca_components = pick_pca_components(pca_response)
        pca_features = pick_pca_features(pca_response)

        if len(pca_components) != 24:
            raise RuntimeError(
                f"PCA API returned {len(pca_components)} components. Expected exactly 24 components."
            )

        score_response, score_latency = post_voice_score(pca_components)

        audio_extract, _ = AudioExtractionResult.objects.update_or_create(
            attempt=attempt,
            defaults={
                "raw_wave_features": extract_response,
                "noise_profile": {"baseline_noise_level": baseline_noise_level},
                "frequency_profile": aligned_features,
                "extraction_status": "completed",
                "processed_at": timezone.now(),
            },
        )

        phonation_feature, _ = PhonationFeature.objects.update_or_create(
            audio_extraction=audio_extract,
            defaults={
                "pitch_mean": safe_decimal(aligned_features.get("pitch_mean"), default=None),
                "jitter": safe_decimal(aligned_features.get("jitter"), default=None),
                "shimmer": safe_decimal(aligned_features.get("shimmer"), default=None),
                "hnr": safe_decimal(aligned_features.get("hnr"), default=None),
                "voice_energy": safe_decimal(aligned_features.get("voice_energy"), default=None),
                "mfcc_features": extract_response.get("mfcc_features") if isinstance(extract_response, dict) else None,
                "embedding_vector": pick_embedding(extract_response, 256),
                "model_version": str(extract_response.get("model_version", "")) if isinstance(extract_response, dict) else "",
                "processed_at": timezone.now(),
            },
        )

        pca_result = create_pca_pipeline_result_safe(
            screening_session=session,
            phonation_feature=phonation_feature,
            raw_features=aligned_features,
            pca_response=pca_response,
            pca_features=pca_features,
            pca_components=pca_components,
            latency=pca_latency,
        )

        voice_result, _ = VoiceAnalysisResult.objects.update_or_create(
            feature=phonation_feature,
            defaults={
                "stress_score": safe_score(score_response, "stress_score", "stress"),
                "depression_score": safe_score(score_response, "depression_score", "depression"),
                "speech_impairment_score": safe_score(score_response, "speech_impairment_score", "speech_score"),
                "confidence_score": safe_confidence(score_response),
                "api_version": str(score_response.get("api_version", "")),
                "processed_at": timezone.now(),
            },
        )

        payload = {
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "expected_label": expected_label,
            "expected_prompt": expected_prompt,
            "accepted_values": accepted_values,
            "transcript": transcript,
            "transcript_language": language_code,
            "verification_status": "passed",
            "verification_reason": "Voice passed strength and hold validation. Acoustic feature pipeline completed.",
            "extract_response": extract_response,
            "raw_feature_count": len(aligned_features),
            "aligned_features": aligned_features,
            "pca_response": pca_response,
            "pca_component_count": len(pca_components),
            "pca_components": pca_components,
            "pca_feature_count": len(pca_features),
            "pca_features": pca_features,
            "pca_result_id": str(getattr(pca_result, "pk", "")),
            "score_response": score_response,
            "summary": {
                "stress_score": make_json_safe(voice_result.stress_score),
                "depression_score": make_json_safe(voice_result.depression_score),
                "speech_impairment_score": make_json_safe(voice_result.speech_impairment_score),
                "confidence_score": make_json_safe(voice_result.confidence_score),
            },
            "latency": {
                "voice_extract_post_s": extract_latency,
                "voice_pca_post_s": pca_latency,
                "voice_score_post_s": score_latency,
            },
        }

        create_modality_result(
            session=session,
            modality="voice",
            result_obj=voice_result,
            payload=payload,
            confidence=voice_result.confidence_score,
        )

        # Keep the phonation session open while the frontend sends 7 separate sounds.
        # The frontend moves to the scenario page only after all 7 sounds are successfully processed.
        phonation_session.session_status = "processing"
        phonation_session.save(update_fields=["session_status"])

        update_session_progress(
            session,
            current_activity="voice_phonation",
            completed_count=1,
            status="processing",
        )

        return JsonResponse({
            "ok": True,
            "passed": True,
            "message": "Voice phonation processed successfully.",
            "session_id": str(session.screening_session_id),
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "transcript": transcript,
            "raw_feature_count": len(aligned_features),
            "pca_feature_count": len(pca_features),
            "pca_result_id": str(getattr(pca_result, "pk", "")),
            "voice_score": score_response,
            "redirect_url": "/assessments/scenario-voice-response/",
        })

    except Exception as exc:
        mark_session_failed(session, exc)
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


# ============================================================
# ACTIVITY 3: SCENARIO VOICE RESPONSE
# ============================================================

@login_required
@require_POST
@csrf_protect
def upload_scenario_voice_response(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)
    audio_file = request.FILES.get("audio")

    if not audio_file:
        return JsonResponse({
            "ok": False,
            "error": "No scenario audio file received. Send file using form field name: audio",
        }, status=400)

    scenario_id = request.POST.get("scenario_id", "").strip()

    try:
        storage_data = save_uploaded_activity_file(
            file_obj=audio_file,
            user_id=request.user.id,
            activity_type="scenario-voice-response",
            original_filename=audio_file.name,
            content_type=audio_file.content_type or "audio/webm",
        )

        media = create_media_asset(
            request=request,
            media_type="scenario_audio",
            file_obj=audio_file,
            storage_data=storage_data,
            activity_type="scenario-voice-response",
            extra_metadata={"scenario_id": scenario_id},
        )

        scenario = get_or_create_audio_scenario(scenario_id)

        scenario_session = ScenarioSession.objects.create(
            screening_session=session,
            audio_scenario=scenario,
            media=media,
            session_status="processing",
        )

        suffix = ".webm"
        if audio_file.name and "." in audio_file.name:
            suffix = "." + audio_file.name.split(".")[-1].lower()

        audio_file.seek(0)
        transcription = transcribe_with_sarvam(
            audio_file,
            suffix=suffix,
            language_code="unknown",
        )

        transcript_text = transcription.get("transcript", "")
        language_code = transcription.get("language_code", "unknown")

        transcript = Transcript.objects.create(
            scenario_session=scenario_session,
            transcript_text=transcript_text,
            language_code=language_code,
            transcript_json=transcription,
        )

        extract_response, extract_latency = post_text_extract(transcript_text)

        raw_features = pick_feature_payload(extract_response)
        aligned_features = align_features(raw_features)

        score_response, score_latency = post_text_score(aligned_features)

        text_parameter = TextParameterResult.objects.create(
            transcript=transcript,
            sentiment_score=safe_score(extract_response, "sentiment_score", "sentiment", max_value=100),
            emotion_distribution=extract_response.get("emotion_distribution") if isinstance(extract_response, dict) else None,
            keyword_analysis=extract_response.get("keyword_analysis") if isinstance(extract_response, dict) else None,
            linguistic_features=extract_response.get("linguistic_features") if isinstance(extract_response, dict) else aligned_features,
            embedding_vector=pick_embedding(extract_response, 1536),
            api_version=str(extract_response.get("api_version", "")) if isinstance(extract_response, dict) else "",
            processed_at=timezone.now(),
        )

        text_result = TextAnalysisResult.objects.create(
            text_parameter=text_parameter,
            stress_score=safe_score(score_response, "stress_score", "stress"),
            depression_score=safe_score(score_response, "depression_score", "depression"),
            anxiety_score=safe_score(score_response, "anxiety_score", "anxiety"),
            confidence_score=safe_confidence(score_response),
            api_version=str(score_response.get("api_version", "")),
            processed_at=timezone.now(),
        )

        payload = {
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "scenario_id": scenario_id,
            "transcript": transcript_text,
            "transcript_language": language_code,
            "extract_response": extract_response,
            "aligned_features": aligned_features,
            "score_response": score_response,
            "summary": {
                "stress_score": make_json_safe(text_result.stress_score),
                "depression_score": make_json_safe(text_result.depression_score),
                "anxiety_score": make_json_safe(text_result.anxiety_score),
                "confidence_score": make_json_safe(text_result.confidence_score),
            },
            "latency": {
                "text_extract_post_s": extract_latency,
                "text_score_post_s": score_latency,
            },
        }

        create_modality_result(
            session=session,
            modality="text",
            result_obj=text_result,
            payload=payload,
            confidence=text_result.confidence_score,
        )

        scenario_session.session_status = "completed"
        scenario_session.completed_at = timezone.now()
        scenario_session.save()

        update_session_progress(
            session,
            current_activity="fusion",
            completed_count=3,
            status="processing",
        )

        return JsonResponse({
            "ok": True,
            "message": "Scenario voice response processed successfully.",
            "session_id": str(session.screening_session_id),
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "transcript": transcript_text,
            "text_score": score_response,
            "redirect_url": "/assessments/activity-complete/",
        })

    except Exception as exc:
        mark_session_failed(session, exc)
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


# ============================================================
# FINAL STEP: MULTIMODAL FUSION
# ============================================================

@login_required
@require_POST
@csrf_protect
def run_multimodal_fusion(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    try:
        face_result = ModalityResult.objects.filter(
            screening_session=session,
            modality="face",
        ).order_by("-created_at").first()

        voice_result = ModalityResult.objects.filter(
            screening_session=session,
            modality="voice",
        ).order_by("-created_at").first()

        text_result = ModalityResult.objects.filter(
            screening_session=session,
            modality="text",
        ).order_by("-created_at").first()

        if not face_result:
            return JsonResponse({"ok": False, "error": "Face result missing. Complete Activity 1 first."}, status=400)

        if not voice_result:
            return JsonResponse({"ok": False, "error": "Voice result missing. Complete Activity 2 first."}, status=400)

        if not text_result:
            return JsonResponse({"ok": False, "error": "Text result missing. Complete Activity 3 first."}, status=400)

        face_payload = face_result.result_payload or {}
        voice_payload = voice_result.result_payload or {}
        text_payload = text_result.result_payload or {}

        combined_features = {
            "face_features": face_payload.get("aligned_features", {}),
            "voice_features": voice_payload.get("pca_features") or voice_payload.get("aligned_features", {}),
            "text_features": text_payload.get("aligned_features", {}),
        }

        fusion_response, fusion_latency = post_fusion_score(combined_features)

        overall_risk = pick_final_risk(fusion_response)

        prediction, _ = FusionPrediction.objects.update_or_create(
            screening_session=session,
            defaults={
                "anxiety_score": safe_score(fusion_response, "anxiety_score", "anxiety"),
                "depression_score": safe_score(fusion_response, "depression_score", "depression"),
                "stress_score": safe_score(fusion_response, "stress_score", "stress"),
                "bipolar_score": safe_score(fusion_response, "bipolar_score", "bipolar"),
                "suicidal_score": safe_score(fusion_response, "suicidal_score", "suicidal"),
                "overall_risk": overall_risk,
                "confidence_score": safe_confidence(fusion_response),
                "final_prediction_json": {
                    "combined_features_count": {
                        "face": len(combined_features["face_features"]) if isinstance(combined_features["face_features"], dict) else 0,
                        "voice": len(combined_features["voice_features"]) if isinstance(combined_features["voice_features"], (dict, list)) else 0,
                        "text": len(combined_features["text_features"]) if isinstance(combined_features["text_features"], dict) else 0,
                    },
                    "score_response": fusion_response,
                    "latency": {"fusion_post_s": fusion_latency},
                },
            },
        )

        session.overall_risk = overall_risk
        session.session_status = "completed"
        session.current_activity = "completed"
        session.completed_activities_count = 3
        session.workflow_stage = 4
        session.completed_at = timezone.now()
        session.save(update_fields=[
            "overall_risk",
            "session_status",
            "current_activity",
            "completed_activities_count",
            "workflow_stage",
            "completed_at",
        ])

        return JsonResponse({
            "ok": True,
            "message": "Multimodal fusion completed successfully.",
            "session_id": str(session.screening_session_id),
            "prediction_id": str(prediction.prediction_id),
            "overall_risk": prediction.overall_risk,
            "confidence_score": prediction.confidence_score,
            "fusion_result": fusion_response,
            "redirect_url": "/assessments/activity-complete/",
        })

    except Exception as exc:
        mark_session_failed(session, exc)
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


# ============================================================
# OPTIONAL: CHECK SESSION STATUS
# ============================================================

@login_required
def multimodal_session_status(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    face_done = ModalityResult.objects.filter(screening_session=session, modality="face").exists()
    voice_done = ModalityResult.objects.filter(screening_session=session, modality="voice").exists()
    text_done = ModalityResult.objects.filter(screening_session=session, modality="text").exists()
    fusion = FusionPrediction.objects.filter(screening_session=session).first()

    return JsonResponse({
        "ok": True,
        "session_id": str(session.screening_session_id),
        "status": session.session_status,
        "current_activity": session.current_activity,
        "workflow_stage": session.workflow_stage,
        "completed_activities_count": session.completed_activities_count,
        "face_done": face_done,
        "voice_done": voice_done,
        "text_done": text_done,
        "fusion_done": bool(fusion),
        "overall_risk": session.overall_risk,
        "final_confidence": fusion.confidence_score if fusion else None,
        "error_message": "" if session.session_status != "failed" else "Session failed. Check server logs.",
    })
