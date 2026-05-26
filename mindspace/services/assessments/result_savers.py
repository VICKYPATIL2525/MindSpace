"""
Database/result helper services for MindSpace assessments.
Move these out of views.py so views stay small and background tasks can reuse the same save logic.
"""

import re
import uuid
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from mindspace.models import (
    AudioScenario,
    ModalityResult,
    PcaPipelineResult,
    PhonationSound,
    VideoActivity,
)

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

def probability_to_percent(value, default=None):
    """
    Convert model probability into 0-100 score column value.

    Examples:
      0.6785 -> 67.85
      0.9985 -> 99.85
      67.85  -> 67.85
    """
    number = safe_decimal(value, default=default)

    if number is None:
        return default

    if number <= Decimal("1"):
        number = number * Decimal("100")

    if number > Decimal("100"):
        number = Decimal("100")

    if number < Decimal("0"):
        number = Decimal("0")

    return number

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

def normalize_prediction_label(value):
    """
    Normalize external model labels to MentalHealthLabel values stored in DB.
    """
    label = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "normal": "normal", "healthy": "normal", "control": "normal",
        "bipolar": "bipolar", "bipolar_disorder": "bipolar",
        "anxiety": "anxiety", "anxious": "anxiety",
        "suicidal": "suicidal_tendency", "suicidal_tendency": "suicidal_tendency",
        "suicide": "suicidal_tendency", "suicide_risk": "suicidal_tendency",
        "stress": "stress", "stressed": "stress",
        "depression": "depression", "depressed": "depression",
    }
    return aliases.get(label, "unknown")

def pick_prediction_label(payload):
    """
    Pick class/prediction label from API response.
    """
    if not isinstance(payload, dict):
        return "unknown"

    for key in ["prediction", "label", "class", "mental_health_label"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_prediction_label(value)

    for key in ["data", "output", "result", "model_output", "score_response"]:
        nested = payload.get(key)
        if isinstance(nested, dict):
            label = pick_prediction_label(nested)
            if label != "unknown":
                return label

    return "unknown"

def pick_probabilities(payload):
    """
    Extract probability/class distribution dictionary from API response.
    """
    if not isinstance(payload, dict):
        return None

    for key in [
        "probabilities",
        "class_probabilities",
        "risk_probabilities",
        "prediction_probabilities",
        "label_probabilities",
    ]:
        value = payload.get(key)
        if isinstance(value, dict):
            return make_json_safe(value)

    for key in ["data", "output", "result", "model_output", "score_response"]:
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = pick_probabilities(nested)
            if found is not None:
                return found

    return None

def probability_score(payload, label_name):
    """
    Read a label probability and convert it to 0-100 score for DB score fields.
    """
    probabilities = pick_probabilities(payload) or {}
    wanted = normalize_prediction_label(label_name)

    for key, value in probabilities.items():
        if normalize_prediction_label(key) == wanted:
            score = safe_decimal(value, default=None)
            if score is None:
                return None
            if score <= Decimal("1"):
                score = score * Decimal("100")
            return min(score, Decimal("100"))

    return None

def score_or_probability(payload, label_name, *keys):
    """
    First try direct score keys. If missing, use probabilities[label_name].
    """
    direct = safe_score(payload, *keys, max_value=100)
    if direct is not None:
        return direct
    return probability_score(payload, label_name)

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

def safe_float(value):
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0

def pick_feature_payload(payload):
    """
    Extract a flat feature dictionary from common external API response shapes.

    Supported:
      {"features": {...}}
      {"vector": {...}}
      {"data": {"features": {...}}}
      {"data": {"vector": {...}}}
      {"result": {"features": {...}}}
      direct feature dictionary
    """
    if not isinstance(payload, dict):
        return {}

    for key in ["features", "vector", "aligned_features", "linguistic_features"]:
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    for wrapper_key in ["data", "result", "output", "model_output", "response"]:
        nested = payload.get(wrapper_key)
        if isinstance(nested, dict):
            nested_features = pick_feature_payload(nested)
            if nested_features:
                return nested_features

    # If this dict itself looks like a feature dictionary, return it.
    scalar_items = {
        key: value
        for key, value in payload.items()
        if not isinstance(value, (dict, list))
    }

    return scalar_items

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
    Return PCA components as a dict in PC1..PC24 order.

    Supports:
      {"components": {"PC1": ...}}
      {"data": {"components": {"PC1": ...}}}
      {"PC1": ..., "PC2": ..., ..., "PC24": ...}
    """
    if not isinstance(payload, dict):
        return {}

    components = payload.get("components")

    if not isinstance(components, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            components = data.get("components") or data.get("pca_components")

    if not isinstance(components, dict):
        # Some PCA APIs return PC1..PC24 directly at top level.
        if all(f"PC{i}" in payload for i in range(1, 25)):
            components = {f"PC{i}": payload.get(f"PC{i}") for i in range(1, 25)}

    if not isinstance(components, dict):
        return {}

    ordered = {}
    for key in sort_pca_component_keys(components):
        try:
            ordered[str(key).upper()] = float(components[key])
        except Exception:
            return {}

    # Ensure exactly PC1..PC24 are present.
    if not all(f"PC{i}" in ordered for i in range(1, 25)):
        return {}

    return {f"PC{i}": ordered[f"PC{i}"] for i in range(1, 25)}

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

def get_or_create_audio_scenario(scenario_id="", prompt_text=""):
    """
    Create/get scenario safely.

    scenario_code must be short because AudioScenario.scenario_code is max_length=50.
    Do not store the full prompt inside scenario_code.
    """

    raw_code = str(scenario_id or "").strip()

    if not raw_code:
        raw_code = "friend_stress_support"

    # Keep only safe short code characters
    safe_code = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_code.lower())

    # Prevent varchar(50) database error
    safe_code = safe_code[:45]

    if not safe_code:
        safe_code = "default_scenario"

    scenario, _ = AudioScenario.objects.get_or_create(
        scenario_code=safe_code,
        defaults={
            "title": "Scenario Voice Response",
            "prompt_text": prompt_text or "Respond to the scenario in your own words.",
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

def extract_model_score_payload(raw_response):
    """
    Extract model scores from the current API response format and keep
    compatibility with older response formats.

    Current API format supported:
    {
        "other_risks": [
            {"label": "bipolar", "probability": 0.0005},
            {"label": "normal", "probability": 0.0002}
        ],
        "dominant_risk": {
            "label": "stress",
            "probability": 0.9985
        }
    }
    """
    result = {
        "normal_score": None,
        "bipolar_score": None,
        "anxiety_score": None,
        "suicidal_tendency_score": None,
        "stress_score": None,
        "depression_score": None,
        "prediction_label": "unknown",
        "probabilities_json": {},
        "confidence_score": None,
    }

    if not isinstance(raw_response, dict):
        return result

    probabilities = {}

    # New API format: dominant_risk + other_risks
    dominant = raw_response.get("dominant_risk")
    if isinstance(dominant, dict):
        label = normalize_prediction_label(dominant.get("label"))
        probability = dominant.get("probability")

        if label != "unknown":
            result["prediction_label"] = label
            probabilities[label] = probability

            field_name = f"{label}_score"
            if field_name in result:
                result[field_name] = probability_to_percent(probability, default=None)

            result["confidence_score"] = normalize_confidence_value(probability)

    other_risks = raw_response.get("other_risks")
    if isinstance(other_risks, list):
        for item in other_risks:
            if not isinstance(item, dict):
                continue

            label = normalize_prediction_label(item.get("label"))
            probability = item.get("probability")

            if label == "unknown":
                continue

            probabilities[label] = probability

            field_name = f"{label}_score"
            if field_name in result:
                result[field_name] = probability_to_percent(probability, default=None)

    # Old API fallback formats: probabilities / class_probabilities / scores / direct keys
    if not probabilities:
        fallback_probabilities = pick_probabilities(raw_response) or {}
        probabilities = fallback_probabilities if isinstance(fallback_probabilities, dict) else {}

        for label in ["normal", "bipolar", "anxiety", "suicidal_tendency", "stress", "depression"]:
            field_name = f"{label}_score"
            result[field_name] = score_or_probability(raw_response, label, field_name, label)

        result["prediction_label"] = pick_prediction_label(raw_response)
        result["confidence_score"] = safe_confidence(raw_response)

    result["probabilities_json"] = make_json_safe(probabilities)

    if result["confidence_score"] is None:
        result["confidence_score"] = safe_confidence(raw_response)

    return result

def model_field_names(model_class):
    """Return concrete Django model field names for safe dynamic defaults."""
    return {field.name for field in model_class._meta.fields}

def create_analysis_defaults(model_class, score_response, *, include_speech_impairment=False):
    """
    Build safe defaults for FacialAnalysisResult, VoiceAnalysisResult,
    and TextAnalysisResult from raw score_response.
    """
    score_data = extract_model_score_payload(score_response)
    fields = model_field_names(model_class)

    defaults = {
        "normal_score": score_data["normal_score"],
        "bipolar_score": score_data["bipolar_score"],
        "anxiety_score": score_data["anxiety_score"],
        "suicidal_tendency_score": score_data["suicidal_tendency_score"],
        "stress_score": score_data["stress_score"],
        "depression_score": score_data["depression_score"],
        "prediction_label": score_data["prediction_label"],
        "probabilities_json": score_data["probabilities_json"],
        "raw_response_json": make_json_safe(score_response),
        "confidence_score": score_data["confidence_score"],
        "api_version": str(score_response.get("api_version", "")) if isinstance(score_response, dict) else "",
        "processed_at": timezone.now(),
    }

    if "risk_label" in fields:
        defaults["risk_label"] = score_data["prediction_label"]

    if include_speech_impairment and "speech_impairment_score" in fields:
        defaults["speech_impairment_score"] = safe_score(
            score_response,
            "speech_impairment_score",
            "speech_score",
        )

    return {key: value for key, value in defaults.items() if key in fields}

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

    pca_result, _ = PcaPipelineResult.objects.update_or_create(
        screening_session=screening_session,
        phonation_feature=phonation_feature,
        defaults=data,
    )

    return pca_result

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
        "normal_score",
        "bipolar_score",
        "anxiety_score",
        "suicidal_tendency_score",
        "suicidal_score",
        "stress_score",
        "depression_score",
        "speech_impairment_score",
        "prediction_label",
        "probabilities_json",
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

    modality_model_fields = {field.name for field in ModalityResult._meta.fields}
    if "fusion_feature_payload" in modality_model_fields:
        if modality == "face":
            defaults["fusion_feature_payload"] = safe_payload.get("aligned_features") or {}
        elif modality == "voice":
            defaults["fusion_feature_payload"] = safe_payload.get("pca_components") or {}
        elif modality == "text":
            defaults["fusion_feature_payload"] = safe_payload.get("aligned_features") or {}

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