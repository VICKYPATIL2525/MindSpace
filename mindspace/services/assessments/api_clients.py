"""
External API clients for MindSpace assessment pipeline.
No request/response view logic should live here.
"""

import os
import time
import tempfile
import requests

from django.conf import settings

from mindspace.services.assessments.media_processing import convert_audio_to_wav
from mindspace.services.assessments.fusion_builder import validate_fusion_features
from mindspace.services.assessments.result_savers import sort_pca_component_keys

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

def post_voice_extract(audio_file, filename=None, content_type=None, force_convert=False):
    """
    Send audio to Voice Feature Extraction API.

    Browser recordings are usually WebM/Opus, so they are converted to WAV first.
    If the input is already a WAV file, it is sent directly to avoid double conversion.

    Supports:
      post_voice_extract(uploaded_webm_file)
      post_voice_extract(open("combined.wav", "rb"), filename="combined-phonation.wav", content_type="audio/wav")
    """
    url = normalize_endpoint_url(
        env_value("VOICE_EXTRACT_URL", "http://88.222.12.15:5800/extract"),
        "/extract",
    )

    api_key = env_value("VOICE_FEATURE_EXTRACT_API_KEY") or env_value("AUDIO_API_KEY")

    if not url:
        raise RuntimeError("VOICE_EXTRACT_URL missing in settings.py/.env")

    if not api_key:
        raise RuntimeError("VOICE_FEATURE_EXTRACT_API_KEY missing in settings.py/.env")

    headers = build_api_headers(api_key)

    upload_filename = filename or getattr(audio_file, "name", "phonation.wav") or "phonation.wav"
    upload_filename = os.path.basename(str(upload_filename))

    upload_content_type = content_type or getattr(audio_file, "content_type", None) or "application/octet-stream"

    is_wav = (
        upload_content_type == "audio/wav"
        or upload_filename.lower().endswith(".wav")
    )

    wav_path = ""
    close_file_after = False

    try:
        if is_wav and not force_convert:
            audio_file.seek(0)
            send_file = audio_file
            send_filename = upload_filename if upload_filename.lower().endswith(".wav") else "phonation.wav"
            send_content_type = "audio/wav"
        else:
            wav_path = convert_audio_to_wav(audio_file)
            send_file = open(wav_path, "rb")
            close_file_after = True
            send_filename = "phonation.wav"
            send_content_type = "audio/wav"

        files = {
            "file": (
                send_filename,
                send_file,
                send_content_type,
            )
        }

        start = time.time()

        try:
            resp = requests.post(
                url,
                headers=headers,
                files=files,
                # combined phonation can take longer; keep read timeout generous
                timeout=(60, 1800),
            )
        except requests.exceptions.ConnectTimeout:
            raise RuntimeError(f"Voice Feature Extract API connection timed out: {url}")
        except requests.exceptions.ReadTimeout:
            raise RuntimeError(f"Voice Feature Extract API processing timed out: {url}")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Voice Feature Extract API connection aborted. URL: {url}. Error: {exc}"
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Voice Feature Extract API request failed. URL: {url}. Error: {exc}"
            )

        latency = seconds(start)
        api_raise(resp, "Voice feature extraction")
        return resp.json(), latency

    finally:
        if close_file_after:
            try:
                send_file.close()
            except Exception:
                pass

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
    """
    Send exact flat feature schema to Fusion API.

    Tries both common FastAPI request shapes:
      1. {"features": {PC1..PC24 + face + text}}
      2. {PC1..PC24 + face + text}
    """
    url = normalize_endpoint_url(
        env_value("FUSION_SCORE_URL", "http://88.222.12.15:8000/predict"),
        "/predict",
    )
    api_key = env_value("MODEL_API_KEY")

    if not api_key:
        raise RuntimeError("MODEL_API_KEY missing")

    validate_fusion_features(combined_features)

    headers = build_api_headers(api_key)
    headers["Content-Type"] = "application/json"
    headers["accept"] = "application/json"

    payloads = [
        {"features": combined_features},
        combined_features,
    ]

    start = time.time()
    last_error = None

    for payload in payloads:
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(30, 900),
            )
            latency = seconds(start)

            if resp.ok:
                return resp.json(), latency

            try:
                last_error = resp.json()
            except Exception:
                last_error = resp.text[:500]

        except requests.exceptions.RequestException as exc:
            last_error = str(exc)

    raise RuntimeError(f"Fusion scoring failed. Last error: {last_error}")

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