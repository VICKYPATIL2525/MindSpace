"""
Fusion feature schema builder for MindSpace.
Builds the exact flat payload expected by the Fusion API.
"""

FUSION_PC_KEYS = [f"PC{i}" for i in range(1, 25)]

FUSION_FACE_KEYS = [
    "au12_activation_frequency",
    "au12_mean_amplitude",
    "au12_variance",
    "au15_mean_amplitude",
    "au1_au2_peak_intensity",
    "au20_activation_rate",
    "au4_duration_ratio",
    "au4_mean_activation",
    "baseline_eye_openness",
    "blink_cluster_density",
    "blink_duration",
    "blink_rate",
    "downward_gaze_frequency",
    "extended_silence_ratio",
    "eye_contact_ratio",
    "facial_emotional_range",
    "facial_transition_frequency",
    "gaze_shift_frequency",
    "gesture_frequency",
    "head_motion_energy",
    "head_velocity_peak",
    "landmark_displacement_mean",
    "lip_compression_frequency",
    "mean_head_velocity",
    "micro_motion_energy",
    "motion_energy_floor_score",
    "near_zero_au_activation_ratio",
    "nod_onset_latency",
    "overall_au_variance",
    "pause_duration_mean",
    "posture_rigidity_index",
    "reaction_time_instability_index",
    "response_latency_mean",
    "speech_onset_delay",
]

FUSION_TEXT_KEYS = [
    "absolutist_word_frequency",
    "adjective_ratio",
    "adverb_ratio",
    "anger_word_frequency",
    "average_sentence_length",
    "avg_dependency_length",
    "avoidance_language_frequency",
    "catastrophizing_indicators",
    "clause_count",
    "cognitive_load_score",
    "disgust_frequency",
    "emotional_intensity_ratio",
    "emotional_volatility_score",
    "external_locus_of_control_score",
    "fear_word_frequency",
    "filler_word_frequency",
    "first_last_sentence_similarity",
    "first_person_singular_pronoun_frequency",
    "future_focused_word_ratio",
    "hapax_legoman_ratio",
    "helplessness_phrase_frequency",
    "joy_frequency",
    "max_negative_emotion",
    "max_sentence_similarity",
    "modal_verb_frequency",
    "moving_average_ttr",
    "negative_emotion_spike_count",
    "negative_emotion_word_ratio",
    "negative_frequency",
    "noun_ratio",
    "overall_sentiment_score",
    "parse_tree_depth",
    "past_focused_word_ratio",
    "positive_emotion_word_ratio",
    "present_focused_word_ratio",
    "repetition_rate",
    "rumination_phrase_frequency",
    "sadness_word_frequency",
    "self_reference_density",
    "semantic_coherence_score",
    "topic_shift_frequency",
    "sentence_count",
    "sentiment_trajectory_slope",
    "sentiment_variance",
    "subordinate_clause_ratio",
    "surprise_frequency",
    "threat_anticipation_language",
    "total_word_count",
    "type_token_ratio_ttr",
    "uncertainty_word_frequency",
    "unique_word_count",
    "verb_ratio",
]

FUSION_EXPECTED_FEATURES = FUSION_PC_KEYS + FUSION_FACE_KEYS + FUSION_TEXT_KEYS

def safe_float_or_zero(value):
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0

def first_numeric_from_prefixed_features(features, base_key):
    """
    Face API often returns statistical feature names such as:
      blink_rate__mean, blink_rate__std, blink_rate__slope

    Fusion API expects:
      blink_rate

    Priority:
      exact key -> __mean -> __max -> __min -> __std -> __range -> __slope -> first prefix match
    """
    if not isinstance(features, dict):
        return 0.0

    if base_key in features:
        return safe_float_or_zero(features.get(base_key))

    suffix_priority = ["__mean", "__max", "__min", "__std", "__range", "__slope"]

    for suffix in suffix_priority:
        key = f"{base_key}{suffix}"
        if key in features:
            return safe_float_or_zero(features.get(key))

    prefix = f"{base_key}__"
    for key, value in features.items():
        if str(key).startswith(prefix):
            return safe_float_or_zero(value)

    return 0.0

def get_text_feature_value(text_features, feature_name):
    """
    Normalize small name differences between Text API and Fusion API.
    """
    if not isinstance(text_features, dict):
        return 0.0

    aliases = {
        "hapax_legoman_ratio": ["hapax_legoman_ratio", "hapax_legomena_ratio"],
        "type_token_ratio_ttr": ["type_token_ratio_ttr", "type_token_ratio"],
        "repetition_rate": ["repetition_rate", "repetition_ratio"],
    }

    for key in aliases.get(feature_name, [feature_name]):
        if key in text_features:
            return safe_float_or_zero(text_features.get(key))

    return 0.0

def build_fusion_feature_payload(face_payload, voice_payload, text_payload):
    """
    Build the exact flat feature schema expected by Fusion API:
      PC1..PC24 + face feature names + text feature names

    It does not send nested keys like:
      face_features, voice_features, text_features
    """
    face_features = {}
    voice_components = {}
    text_features = {}

    if isinstance(face_payload, dict):
        face_features = (
            face_payload.get("fusion_feature_payload")
            or face_payload.get("aligned_features")
            or {}
        )

    if isinstance(voice_payload, dict):
        voice_components = (
            voice_payload.get("fusion_feature_payload")
            or voice_payload.get("pca_components")
            or (voice_payload.get("pca_response") or {}).get("components")
            or {}
        )

    if isinstance(text_payload, dict):
        text_features = (
            text_payload.get("fusion_feature_payload")
            or text_payload.get("aligned_features")
            or {}
        )

    combined = {}

    for pc_key in FUSION_PC_KEYS:
        combined[pc_key] = safe_float_or_zero(voice_components.get(pc_key))

    for face_key in FUSION_FACE_KEYS:
        combined[face_key] = first_numeric_from_prefixed_features(face_features, face_key)

    for text_key in FUSION_TEXT_KEYS:
        combined[text_key] = get_text_feature_value(text_features, text_key)

    return combined

def validate_fusion_features(features):
    missing = [key for key in FUSION_EXPECTED_FEATURES if key not in features]
    if missing:
        raise RuntimeError(f"Fusion feature payload missing keys: {missing}")

    bad = [
        key for key, value in features.items()
        if not isinstance(value, (int, float))
    ]

    if bad:
        raise RuntimeError(f"Fusion feature payload has non-numeric values: {bad}")

    return True