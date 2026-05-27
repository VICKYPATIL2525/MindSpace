"""
MindSpace assessment views.

This file is intentionally thin:
- page views render templates
- upload views validate basic request data and save initial DB/media rows
- heavy processing is delegated to Django-Q2 tasks in mindspace.tasks.assessments
"""

import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from mindspace.models import (
    FusionPrediction,
    MediaAsset,
    ModalityResult,
    PhonationAttempt,
    PhonationSession,
    PlatformScreeningSession,
    ScenarioSession,
    VideoSession,
)

from mindspace.services.assessments.result_savers import (
    get_or_create_audio_scenario,
    get_or_create_default_video_activity,
    get_or_create_phonation_sound,
    safe_decimal,
)

from mindspace.services.assessments.storage import (
    create_media_asset,
    save_uploaded_activity_file,
)


# ============================================================
# CONSTANTS
# ============================================================

MIN_FACE_VIDEO_SECONDS = 150
MIN_VOICE_HOLD_MS = 900
MIN_VOICE_VOLUME_SCORE = 30


# ============================================================
# ONBOARDING / ACCESS HELPERS
# ============================================================

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
    Redirect users to the correct onboarding step before assessment pages.
    """
    profile = get_user_profile(request.user)

    if not profile.consented:
        return redirect("consent")

    if not profile.profile_completed:
        return redirect("complete_profile")

    return None


def assessment_api_guard(request):
    """
    JSON guard for AJAX/API upload endpoints.
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
# SESSION HELPERS
# ============================================================

def get_active_screening_session(request):
    """
    Return the active PlatformScreeningSession stored in browser session.
    If missing, create a new assessment session.
    """
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


# Backward-compatible alias
get_active_multimodal_session = get_active_screening_session


def _mark_session_processing(session, current_activity, workflow_stage=None):
    session.session_status = "processing"
    session.current_activity = current_activity

    update_fields = ["session_status", "current_activity"]

    if workflow_stage is not None:
        session.workflow_stage = workflow_stage
        update_fields.append("workflow_stage")

    session.save(update_fields=update_fields)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


# ============================================================
# PAGE RENDER VIEWS
# ============================================================

@login_required
def check_in_view(request):
    """
    Wellness check-in page.
    POST starts a new PlatformScreeningSession and redirects to Activity 1.
    """
    guard = assessment_page_guard(request)
    if guard:
        return guard

    if request.method == "POST":
        mood = request.POST.get("mood", "").strip()
        note = request.POST.get("note", "").strip()

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
        "fusion_done": bool(fusion),
        "is_processing": session.current_activity in [
            "scenario_voice_processing",
            "fusion_processing",
            "fusion",
        ],
    })


# ============================================================
# SESSION START
# ============================================================

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
# ACTIVITY 1: FACE VIDEO UPLOAD
# Heavy processing runs in process_face_video_task()
# ============================================================

@login_required
@require_POST
@csrf_protect
def upload_face_video(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    video_file = request.FILES.get("video")
    if not video_file:
        return JsonResponse({
            "ok": False,
            "error": "No video file received. Send file using form field name: video.",
        }, status=400)

    duration_seconds = _safe_float(request.POST.get("duration_seconds", "0"), 0.0)

    if duration_seconds < MIN_FACE_VIDEO_SECONDS:
        return JsonResponse({
            "ok": False,
            "error": f"Face video must be at least {MIN_FACE_VIDEO_SECONDS} seconds.",
            "required_seconds": MIN_FACE_VIDEO_SECONDS,
            "received_seconds": duration_seconds,
        }, status=400)

    activity_id = request.POST.get("activity_id", "").strip()
    activity_title = request.POST.get("activity_title", "").strip()
    activity_prompt = request.POST.get("activity_prompt", "").strip()

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
            duration_seconds=duration_seconds,
        )

        activity = get_or_create_default_video_activity(
            activity_id,
            activity_title,
            activity_prompt,
        )

        video_session = VideoSession.objects.create(
            screening_session=session,
            video_activity=activity,
            media=media,
            extraction_status="pending",
            analysis_status="pending",
            session_status="processing",
            processing_started_at=timezone.now(),
        )

        task_id = async_task(
            "mindspace.tasks.assessments.process_face_video_task",
            str(session.screening_session_id),
            str(video_session.video_session_id),
        )

        _mark_session_processing(
            session,
            current_activity="face_video_processing",
            workflow_stage=1,
        )

        return JsonResponse({
            "ok": True,
            "message": "Face video uploaded. Processing started in background.",
            "task_id": task_id,
            "session_id": str(session.screening_session_id),
            "media_id": str(media.media_id),
            "video_session_id": str(video_session.video_session_id),
            "status_url": "/assessments/multimodal/status/",
        })

    except Exception as exc:
        session.session_status = "failed"
        session.current_activity = "error"
        session.save(update_fields=["session_status", "current_activity"])

        return JsonResponse({
            "ok": False,
            "error": str(exc),
        }, status=500)


# ============================================================
# ACTIVITY 2: VOICE PHONATION UPLOAD
# Saves each sound only. Combined processing starts in complete_voice_phonation().
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
            "error": "No audio file received. Send file using form field name: audio.",
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

    volume_score = _safe_float(request.POST.get("volume_score", 0), 0.0)
    hold_ms = _safe_int(request.POST.get("hold_ms", 0), 0)
    baseline_noise_level = _safe_float(request.POST.get("baseline_noise_level", 0), 0.0)

    if volume_score < MIN_VOICE_VOLUME_SCORE:
        return JsonResponse({
            "ok": False,
            "passed": False,
            "reason": "Voice strength too low. Please speak a little louder and try again.",
        }, status=400)

    if hold_ms < MIN_VOICE_HOLD_MS:
        return JsonResponse({
            "ok": False,
            "passed": False,
            "reason": "Sound was not held long enough.",
        }, status=400)

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

        if phonation_session.session_status != "processing":
            phonation_session.session_status = "processing"
            phonation_session.save(update_fields=["session_status"])

        sound = get_or_create_phonation_sound(expected_label, expected_prompt)

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

        completed_sound_count = PhonationAttempt.objects.filter(
            phonation_session=phonation_session
        ).exclude(
            sound__sound_character="combined_7"
        ).count()

        return JsonResponse({
            "ok": True,
            "passed": True,
            "message": "Sound saved.",
            "session_id": str(session.screening_session_id),
            "media_id": str(media.media_id),
            "attempt_id": str(attempt.pk),
            "completed_sound_count": completed_sound_count,
            "ready_for_combined_processing": completed_sound_count >= 7,
        })

    except Exception as exc:
        session.session_status = "failed"
        session.current_activity = "error"
        session.save(update_fields=["session_status", "current_activity"])

        return JsonResponse({
            "ok": False,
            "error": str(exc),
        }, status=500)


# ============================================================
# USER FINISHED ALL PHONATION SOUNDS
# Frontend should call this after all 7 separate sound tasks are submitted.
# ============================================================

@login_required
@require_POST
@csrf_protect
def complete_voice_phonation(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    phonation_session = PhonationSession.objects.filter(
        screening_session=session
    ).first()

    if not phonation_session:
        return JsonResponse({
            "ok": False,
            "error": "Phonation session not found.",
        }, status=400)

    completed_sound_count = PhonationAttempt.objects.filter(
        phonation_session=phonation_session
    ).exclude(
        sound__sound_character="combined_7"
    ).count()

    if completed_sound_count < 7:
        return JsonResponse({
            "ok": False,
            "error": f"Complete all 7 phonation sounds first. Found {completed_sound_count}/7.",
        }, status=400)

    task_id = async_task(
        "mindspace.tasks.assessments.process_combined_voice_phonation_task",
        str(session.screening_session_id),
    )

    session.session_status = "processing"
    session.current_activity = "voice_phonation_processing"
    session.save(update_fields=["session_status", "current_activity"])

    return JsonResponse({
        "ok": True,
        "message": "Combined voice phonation processing started.",
        "task_id": task_id,
        "status_url": "/assessments/multimodal/status/",
    })


# ============================================================
# ACTIVITY 3: SCENARIO VOICE RESPONSE UPLOAD
# Heavy processing runs in process_scenario_voice_task()
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
            "error": "No scenario audio file received. Send file using form field name: audio.",
        }, status=400)

    scenario_id = request.POST.get("scenario_id", "").strip()
    scenario_prompt = request.POST.get("scenario_prompt", "").strip()

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
            extra_metadata={
                "scenario_id": scenario_id,
                "scenario_prompt": scenario_prompt,
            },
        )

        scenario = get_or_create_audio_scenario(
            scenario_id=scenario_id,
            prompt_text=scenario_prompt,
        )

        scenario_session = ScenarioSession.objects.create(
            screening_session=session,
            audio_scenario=scenario,
            media=media,
            session_status="processing",
        )

        task_id = async_task(
            "mindspace.tasks.assessments.process_scenario_voice_task",
            str(session.screening_session_id),
            str(scenario_session.scenario_session_id),
            str(media.media_id),
        )

        _mark_session_processing(
            session,
            current_activity="scenario_voice_processing",
            workflow_stage=3,
        )

        return JsonResponse({
            "ok": True,
            "message": "Scenario audio uploaded. Processing started in background.",
            "task_id": task_id,
            "session_id": str(session.screening_session_id),
            "media_id": str(media.media_id),
            "scenario_session_id": str(scenario_session.scenario_session_id),
            "status_url": "/assessments/multimodal/status/",
        })

    except Exception as exc:
        session.session_status = "failed"
        session.current_activity = "error"
        session.save(update_fields=["session_status", "current_activity"])

        return JsonResponse({
            "ok": False,
            "error": str(exc),
        }, status=500)


# ============================================================
# FINAL STEP: MULTIMODAL FUSION
# Heavy processing runs in process_fusion_task()
# ============================================================

@login_required
@require_POST
@csrf_protect
def run_multimodal_fusion(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    face_done = ModalityResult.objects.filter(
        screening_session=session,
        modality="face",
    ).exists()

    voice_done = ModalityResult.objects.filter(
        screening_session=session,
        modality="voice",
    ).exists()

    text_done = ModalityResult.objects.filter(
        screening_session=session,
        modality="text",
    ).exists()

    if not face_done:
        return JsonResponse({
            "ok": False,
            "error": "Face result missing. Complete Activity 1 first.",
        }, status=400)

    if not voice_done:
        return JsonResponse({
            "ok": False,
            "error": "Voice result missing. Complete Activity 2 first.",
        }, status=400)

    if not text_done:
        return JsonResponse({
            "ok": False,
            "error": "Text result missing. Complete Activity 3 first.",
        }, status=400)

    try:
        task_id = async_task(
            "mindspace.tasks.assessments.process_fusion_task",
            str(session.screening_session_id),
        )

        _mark_session_processing(
            session,
            current_activity="fusion_processing",
            workflow_stage=4,
        )

        return JsonResponse({
            "ok": True,
            "message": "Fusion processing started in background.",
            "task_id": task_id,
            "session_id": str(session.screening_session_id),
            "status_url": "/assessments/multimodal/status/",
        })

    except Exception as exc:
        session.session_status = "failed"
        session.current_activity = "error"
        session.save(update_fields=["session_status", "current_activity"])

        return JsonResponse({
            "ok": False,
            "error": str(exc),
        }, status=500)


# ============================================================
# SESSION STATUS / FRONTEND POLLING
# ============================================================

@login_required
def multimodal_session_status(request):
    guard = assessment_api_guard(request)
    if guard:
        return guard

    session = get_active_screening_session(request)

    face_done = ModalityResult.objects.filter(
        screening_session=session,
        modality="face",
    ).exists()

    voice_done = ModalityResult.objects.filter(
        screening_session=session,
        modality="voice",
    ).exists()

    text_done = ModalityResult.objects.filter(
        screening_session=session,
        modality="text",
    ).exists()

    fusion = FusionPrediction.objects.filter(
        screening_session=session,
    ).first()

    next_url = ""
    if session.current_activity == "voice_phonation":
        next_url = "/assessments/voice-phonation/"
    elif session.current_activity == "scenario_voice_response":
        next_url = "/assessments/scenario-voice-response/"
    elif session.current_activity == "fusion":
        next_url = ""
    elif session.current_activity == "completed":
        next_url = "/assessments/activity-complete/"

    error_message = ""
    if session.session_status == "failed":
        metadata = getattr(session, "metadata_json", None) or {}
        error_message = (
            metadata.get("last_error")
            or metadata.get("error")
            or "Session failed. Check qcluster/server logs."
        )

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
        "next_url": next_url,
        "redirect_url": next_url,
        "error_message": error_message,
    })