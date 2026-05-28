ACTIVITY_RECOMMENDATIONS = {
    "normal": {
        "title": "Daily Balance Activities",
        "subtitle": "Keep your routine steady and maintain your wellbeing.",
        "primary": {
            "name": "Resonance Breathing",
            "description": "5s inhale → 5s exhale. Good for daily nervous-system balance.",
            "url_name": "breath_resonance",
            "time": "5 min",
        },
        "activities": [
            {"name": "Resonance Breathing", "url_name": "breath_resonance", "time": "5 min"},
            {"name": "Full Body Grounding Flow", "url_name": "activity_grounding_flow", "time": "5 min"},
            {"name": "Stillness Stretch Flow", "url_name": "activity_stillness_stretch", "time": "4 min"},
            {"name": "Mindful Walk", "url_name": "#", "time": "5 min"},
        ],
    },

    "stress": {
        "title": "Stress Reset Activities",
        "subtitle": "Reduce pressure, body tension, and mental overload.",
        "primary": {
            "name": "Extended Exhale Breathing",
            "description": "Longer exhale breathing to calm stress response.",
            "url_name": "breath_extended_exhale",
            "time": "5 min",
        },
        "activities": [
            {"name": "Extended Exhale Breathing", "url_name": "breath_extended_exhale", "time": "5 min"},
            {"name": "Box Breathing", "url_name": "breath_box", "time": "4 min"},
            {"name": "Neck Release Sequence", "url_name": "activity_neck_release", "time": "2 min"},
            {"name": "Shoulder Unlock Sequence", "url_name": "activity_shoulder_unlock", "time": "3 min"},
        ],
    },

    "anxiety": {
        "title": "Anxiety Grounding Activities",
        "subtitle": "Slow racing thoughts and bring attention back to the present.",
        "primary": {
            "name": "Paced Recovery Breathing",
            "description": "3s inhale → 3s exhale. Easy breathing for high distress.",
            "url_name": "breath_paced_recovery",
            "time": "3 min",
        },
        "activities": [
            {"name": "Paced Recovery Breathing", "url_name": "breath_paced_recovery", "time": "3 min"},
            {"name": "4-7-8 Breathing", "url_name": "breath_478", "time": "5 min"},
            {"name": "Full Body Grounding Flow", "url_name": "activity_grounding_flow", "time": "5 min"},
            {"name": "Stillness Stretch Flow", "url_name": "activity_stillness_stretch", "time": "4 min"},
        ],
    },

    "depression": {
        "title": "Mood Activation Activities",
        "subtitle": "Start with small actions that create movement and a sense of progress.",
        "primary": {
            "name": "Full Body Grounding Flow",
            "description": "A gentle movement flow to reconnect with your body.",
            "url_name": "activity_grounding_flow",
            "time": "5 min",
        },
        "activities": [
            {"name": "Full Body Grounding Flow", "url_name": "activity_grounding_flow", "time": "5 min"},
            {"name": "Spine Wake-Up Sequence", "url_name": "activity_spine_wakeup", "time": "3–4 min"},
            {"name": "Stillness Stretch Flow", "url_name": "activity_stillness_stretch", "time": "4 min"},
            {"name": "Mood Journal", "url_name": "#", "time": "4 min"},
        ],
    },

    "bipolar": {
        "title": "Stability Routine Activities",
        "subtitle": "Focus on calm, sleep, routine, and low-intensity regulation.",
        "primary": {
            "name": "Resonance Breathing",
            "description": "A calm daily breathing routine for steady regulation.",
            "url_name": "breath_resonance",
            "time": "5 min",
        },
        "activities": [
            {"name": "Resonance Breathing", "url_name": "breath_resonance", "time": "5 min"},
            {"name": "Stillness Stretch Flow", "url_name": "activity_stillness_stretch", "time": "4 min"},
            {"name": "Gentle Walking", "url_name": "#", "time": "5 min"},
            {"name": "Sleep Routine Planner", "url_name": "#", "time": "5 min"},
        ],
    },

    "suicidal_tendency": {
        "title": "Safety Support Activities",
        "subtitle": "Focus on immediate safety and human support.",
        "primary": {
            "name": "Contact Support",
            "description": "Reach a counselor, trusted person, or emergency support.",
            "url_name": "counselor_support",
            "time": "Now",
        },
        "activities": [
            {"name": "Contact Counselor", "url_name": "counselor", "time": "Now"},
            {"name": "Paced Recovery Breathing", "url_name": "breath_paced_recovery", "time": "3 min"},
            {"name": "5-4-3-2-1 Grounding", "url_name": "#", "time": "4 min"},
            {"name": "Safety Plan", "url_name": "#", "time": "5 min"},
        ],
    },
}


def get_recommendation_for_label(label):
    clean_label = str(label or "normal").strip().lower()

    # normalize possible DB labels
    label_map = {
        "suicidal": "suicidal_tendency",
        "suicidal tendency": "suicidal_tendency",
        "suicidal_tendency": "suicidal_tendency",
        "normal": "normal",
        "stress": "stress",
        "anxiety": "anxiety",
        "depression": "depression",
        "bipolar": "bipolar",
    }

    clean_label = label_map.get(clean_label, clean_label)

    if clean_label not in ACTIVITY_RECOMMENDATIONS:
        clean_label = "normal"

    return ACTIVITY_RECOMMENDATIONS[clean_label]