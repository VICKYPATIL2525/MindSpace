"""
Django-Q2 background tasks for MindSpace assessment pipeline.
Run workers with: python manage.py qcluster
"""

import logging
import os

from django.utils import timezone
from django_q.tasks import async_task

from mindspace.models import (
    AudioExtractionResult,
    FaceFeatureVector,
    FacialAnalysisResult,
    FusionPrediction,
    MediaAsset,
    ModalityResult,
    PhonationAttempt,
    PhonationFeature,
    PhonationSession,
    PlatformScreeningSession,
    ScenarioSession,
    TextAnalysisResult,
    TextParameterResult,
    Transcript,
    VideoSession,
    VoiceAnalysisResult,
)

from mindspace.services.assessments.api_clients import (
    get_face_vector,
    post_face_extract,
    post_face_score,
    post_fusion_score,
    post_text_extract,
    post_text_score,
    post_voice_extract,
    post_voice_pca,
    post_voice_score,
    transcribe_with_sarvam,
)

from mindspace.services.assessments.fusion_builder import build_fusion_feature_payload

from mindspace.services.assessments.media_processing import (
    cleanup_temp_file,
    combine_audio_files_to_wav,
    compress_video_for_face_api,
)

from mindspace.services.assessments.result_savers import (
    align_features,
    create_analysis_defaults,
    create_modality_result,
    create_pca_pipeline_result_safe,
    get_or_create_audio_scenario,
    get_or_create_phonation_sound,
    make_json_safe,
    mark_session_failed,
    pick_feature_payload,
    pick_final_risk,
    pick_pca_components,
    pick_pca_features,
    update_session_progress,
)

from mindspace.services.assessments.storage import (
    get_local_media_absolute_path,
    save_uploaded_activity_file,
)

logger = logging.getLogger(__name__)


def _open_local_media(media: MediaAsset):
    path = get_local_media_absolute_path(media)
    if not path or not os.path.exists(path):
        raise RuntimeError(f"Local media file not found for media_id={media.media_id}: {path}")
    return open(path, "rb")


def process_face_video_task(screening_session_id, video_session_id):
    compressed_video_path = ""

    try:
        session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
        video_session = VideoSession.objects.select_related("media").get(video_session_id=video_session_id)
        media = video_session.media

        if media.storage_provider != "local":
            raise RuntimeError("Face task currently supports local storage only. Use USE_GCP_STORAGE=False while testing.")

        original_video_path = get_local_media_absolute_path(media)
        compressed_video_path = compress_video_for_face_api(original_video_path)
        compressed_size = os.path.getsize(compressed_video_path)

        with open(compressed_video_path, "rb") as api_file:
            extract_response, extract_latency = post_face_extract(
                api_file,
                filename="compressed_face_video.mp4",
                content_type="video/mp4",
            )

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
            feature_json=aligned_vector,
            raw_response_json=vector_response,
            feature_schema_version="face_63_features_v1",
            api_processed_at=timezone.now(),
        )

        facial_result = FacialAnalysisResult.objects.create(
            feature=face_feature,
            **create_analysis_defaults(FacialAnalysisResult, score_response),
        )

        payload = {
            "media_id": str(media.media_id),
            "file_url": media.cdn_url,
            "storage_provider": media.storage_provider,
            "extract_response": extract_response,
            "vector_response": vector_response,
            "aligned_features": aligned_vector,
            "score_response": score_response,
            "latency": {
                "face_extract_post_s": extract_latency,
                "face_vector_get_s": vector_latency,
                "face_score_post_s": score_latency,
                "compressed_file_size": compressed_size,
            },
        }

        create_modality_result(
            session=session,
            modality="face",
            result_obj=facial_result,
            payload=payload,
            confidence=getattr(facial_result, "confidence_score", None),
        )

        video_session.extraction_status = "completed"
        video_session.analysis_status = "completed"
        video_session.session_status = "completed"
        video_session.processing_completed_at = timezone.now()
        video_session.completed_at = timezone.now()
        video_session.save(update_fields=[
            "extraction_status", "analysis_status", "session_status",
            "processing_completed_at", "completed_at",
        ])

        update_session_progress(session, current_activity="voice_phonation", completed_count=1, status="processing")
        return {"ok": True, "next_url": "/assessments/voice-phonation/"}

    except Exception as exc:
        logger.exception("Face video task failed")
        try:
            session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
            mark_session_failed(session, exc)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}

    finally:
        cleanup_temp_file(compressed_video_path)


def process_combined_voice_phonation_task(screening_session_id):
    """
    Combine 7 recorded phonation audios into one WAV, then run:
    Voice Extract API → PCA API → Voice Score API.
    """

    combined_path = ""

    try:
        session = PlatformScreeningSession.objects.get(
            screening_session_id=screening_session_id
        )

        phonation_session = PhonationSession.objects.get(
            screening_session=session
        )

        attempts = (
            PhonationAttempt.objects
            .filter(phonation_session=phonation_session)
            .exclude(sound__sound_character="combined_7")
            .select_related("media", "sound")
            .order_by("sound__sound_order", "created_at")
        )

        attempt_count = attempts.count()
        if attempt_count < 7:
            raise RuntimeError(
                f"Need 7 phonation sounds before combined analysis. Found {attempt_count}."
            )

        selected_attempts = list(attempts[:7])
        audio_paths = []

        for attempt in selected_attempts:
            media = attempt.media

            if not media:
                raise RuntimeError("One phonation attempt has no media attached.")

            if media.storage_provider != "local":
                raise RuntimeError(
                    "Combined voice task currently supports local storage only. "
                    "Set USE_GCP_STORAGE=False while testing."
                )

            audio_paths.append(get_local_media_absolute_path(media))

        combined_path = combine_audio_files_to_wav(audio_paths, silence_seconds=0.7)

        # Save combined audio as a new MediaAsset.
        # Do NOT assign .name or .content_type to a normal Python file object;
        # those attributes can be read-only and will crash inside qcluster.
        with open(combined_path, "rb") as combined_file:
            storage_data = save_uploaded_activity_file(
                file_obj=combined_file,
                user_id=session.user_id,
                activity_type="voice-phonation-combined",
                original_filename="combined-phonation.wav",
                content_type="audio/wav",
            )

        combined_media = MediaAsset.objects.create(
            user=session.user,
            media_type="phonation_audio",
            file_name="combined-phonation.wav",
            content_type="audio/wav",
            size_bytes=os.path.getsize(combined_path),
            storage_provider=storage_data["storage_provider"],
            bucket_name=storage_data.get("bucket_name") or "",
            object_key=storage_data["object_key"],
            cdn_url=storage_data.get("file_url") or "",
            upload_status="completed",
            metadata_json={
                "combined": True,
                "source_attempt_count": len(selected_attempts),
                "source_attempt_ids": [str(item.pk) for item in selected_attempts],
                "activity_type": "voice-phonation-combined",
            },
        )

        combined_sound = get_or_create_phonation_sound(
            expected_label="combined_7",
            expected_prompt="Combined 7 phonation sounds",
        )

        combined_attempt, _ = PhonationAttempt.objects.update_or_create(
            phonation_session=phonation_session,
            sound=combined_sound,
            defaults={
                "media": combined_media,
                "pronunciation_detected": True,
                "character_accuracy_score": 100,
                "silence_duration_ms": 0,
                "response_time_ms": 0,
            },
        )

        with open(combined_path, "rb") as api_audio:
            extract_response, extract_latency = post_voice_extract(
                api_audio,
                filename="combined-phonation.wav",
                content_type="audio/wav",
            )

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

        if not pca_features and isinstance(pca_components, dict):
            pca_features = [pca_components.get(f"PC{i}") for i in range(1, 25)]

        if len(pca_components) != 24:
            raise RuntimeError(
                f"PCA API returned {len(pca_components)} components. Expected exactly 24."
            )

        if len(pca_features) != 24 or any(value is None for value in pca_features):
            raise RuntimeError(
                f"PCA API returned invalid PCA feature list. Expected PC1-PC24 numeric values."
            )

        score_response, score_latency = post_voice_score(pca_components)

        audio_extract, _ = AudioExtractionResult.objects.update_or_create(
            attempt=combined_attempt,
            defaults={
                "raw_wave_features": extract_response,
                "noise_profile": {
                    "combined_phonation": True,
                    "source_attempt_count": len(selected_attempts),
                },
                "frequency_profile": aligned_features,
                "extraction_status": "completed",
                "processed_at": timezone.now(),
            },
        )

        phonation_feature, _ = PhonationFeature.objects.update_or_create(
            audio_extraction=audio_extract,
            defaults={
                "voice_features_json": aligned_features,
                "raw_response_json": extract_response,
                "feature_count": len(aligned_features),
                "feature_schema_version": "voice_6373_features_v1_combined",
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
            defaults=create_analysis_defaults(
                VoiceAnalysisResult,
                score_response,
                include_speech_impairment=True,
            ),
        )

        payload = {
            "media_id": str(combined_media.media_id),
            "file_url": combined_media.cdn_url,
            "storage_provider": combined_media.storage_provider,
            "combined_phonation": True,
            "source_attempt_count": len(selected_attempts),
            "extract_response": extract_response,
            "raw_feature_count": len(aligned_features),
            "aligned_features": aligned_features,
            "pca_response": pca_response,
            "pca_components": pca_components,
            "pca_feature_count": len(pca_features),
            "pca_features": pca_features,
            "pca_result_id": str(getattr(pca_result, "pk", "")),
            "score_response": score_response,
            "summary": {
                "normal_score": getattr(voice_result, "normal_score", None),
                "bipolar_score": getattr(voice_result, "bipolar_score", None),
                "anxiety_score": getattr(voice_result, "anxiety_score", None),
                "suicidal_tendency_score": getattr(voice_result, "suicidal_tendency_score", None),
                "stress_score": getattr(voice_result, "stress_score", None),
                "depression_score": getattr(voice_result, "depression_score", None),
                "prediction_label": getattr(voice_result, "prediction_label", None),
                "confidence_score": getattr(voice_result, "confidence_score", None),
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

        phonation_session.session_status = "completed"
        phonation_session.completed_at = timezone.now()
        phonation_session.save(update_fields=["session_status", "completed_at"])

        update_session_progress(
            session,
            current_activity="scenario_voice_response",
            completed_count=2,
            status="processing",
        )

        return {
            "ok": True,
            "next_url": "/assessments/scenario-voice-response/",
        }

    except Exception as exc:
        logger.exception("Combined voice phonation task failed")
        try:
            session = PlatformScreeningSession.objects.get(
                screening_session_id=screening_session_id
            )
            mark_session_failed(session, exc)
        except Exception:
            pass

        return {
            "ok": False,
            "error": str(exc),
        }

    finally:
        cleanup_temp_file(combined_path)

def process_voice_phonation_task(screening_session_id, phonation_attempt_id, media_id, expected_label="", expected_prompt=""):
    try:
        session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
        attempt = PhonationAttempt.objects.select_related("phonation_session", "sound").get(attempt_id=phonation_attempt_id)
        media = MediaAsset.objects.get(media_id=media_id)

        with _open_local_media(media) as audio_file:
            extract_response, extract_latency = post_voice_extract(audio_file)

        raw_features = pick_feature_payload(extract_response)
        aligned_features = align_features(raw_features)

        if len(aligned_features) != 6373:
            raise RuntimeError(f"Voice Feature Extract API returned {len(aligned_features)} features. Expected 6373.")

        pca_response, pca_latency = post_voice_pca(aligned_features)
        pca_components = pick_pca_components(pca_response)
        pca_features = pick_pca_features(pca_response)

        if len(pca_components) != 24:
            raise RuntimeError(f"PCA API returned {len(pca_components)} components. Expected 24.")

        score_response, score_latency = post_voice_score(pca_components)

        audio_extract, _ = AudioExtractionResult.objects.update_or_create(
            attempt=attempt,
            defaults={
                "raw_wave_features": extract_response,
                "noise_profile": (media.metadata_json or {}),
                "frequency_profile": aligned_features,
                "extraction_status": "completed",
                "processed_at": timezone.now(),
            },
        )

        phonation_feature, _ = PhonationFeature.objects.update_or_create(
            audio_extraction=audio_extract,
            defaults={
                "voice_features_json": aligned_features,
                "raw_response_json": extract_response,
                "feature_count": len(aligned_features),
                "feature_schema_version": "voice_6373_features_v1",
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
            defaults=create_analysis_defaults(
                VoiceAnalysisResult,
                score_response,
                include_speech_impairment=True,
            ),
        )

        payload = {
            "media_id": str(media.media_id),
            "expected_label": expected_label,
            "expected_prompt": expected_prompt,
            "extract_response": extract_response,
            "raw_feature_count": len(aligned_features),
            "aligned_features": aligned_features,
            "pca_response": pca_response,
            "pca_components": pca_components,
            "pca_features": pca_features,
            "pca_feature_count": len(pca_features),
            "pca_result_id": str(getattr(pca_result, "pk", "")),
            "score_response": score_response,
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
            confidence=getattr(voice_result, "confidence_score", None),
        )

        attempt.phonation_session.session_status = "processing"
        attempt.phonation_session.save(update_fields=["session_status"])

        return {"ok": True, "passed": True, "pca_feature_count": len(pca_features)}

    except Exception as exc:
        logger.exception("Voice phonation task failed")
        try:
            session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
            mark_session_failed(session, exc)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}


def process_scenario_voice_task(screening_session_id, scenario_session_id, media_id):
    try:
        session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
        scenario_session = ScenarioSession.objects.select_related("audio_scenario").get(scenario_session_id=scenario_session_id)
        media = MediaAsset.objects.get(media_id=media_id)

        suffix = ".webm"
        if media.file_name and "." in media.file_name:
            suffix = "." + media.file_name.split(".")[-1].lower()

        with _open_local_media(media) as audio_file:
            transcription = transcribe_with_sarvam(audio_file, suffix=suffix, language_code="unknown")

        transcript_text = transcription.get("transcript", "")
        language_code = transcription.get("language_code", "unknown")

        transcript = Transcript.objects.create(
            scenario_session=scenario_session,
            transcript_text=transcript_text,
            language_code=language_code,
            stt_provider="sarvam",
            stt_model=transcription.get("model", ""),
            transcript_json=transcription,
        )

        extract_response, extract_latency = post_text_extract(transcript_text)
        raw_features = pick_feature_payload(extract_response)
        aligned_features = align_features(raw_features)
        score_response, score_latency = post_text_score(aligned_features)

        text_parameter = TextParameterResult.objects.create(
            transcript=transcript,
            linguistic_features=aligned_features,
            raw_response_json=extract_response,
            feature_schema_version="text_features_v1",
            api_version=str(extract_response.get("api_version", "")) if isinstance(extract_response, dict) else "",
            processed_at=timezone.now(),
        )

        text_result = TextAnalysisResult.objects.create(
            text_parameter=text_parameter,
            **create_analysis_defaults(TextAnalysisResult, score_response),
        )

        payload = {
            "media_id": str(media.media_id),
            "scenario_id": scenario_session.audio_scenario.scenario_code,
            "transcript": transcript_text,
            "transcript_language": language_code,
            "extract_response": extract_response,
            "aligned_features": aligned_features,
            "score_response": score_response,
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
            confidence=getattr(text_result, "confidence_score", None),
        )

        scenario_session.session_status = "completed"
        scenario_session.completed_at = timezone.now()
        scenario_session.save(update_fields=["session_status", "completed_at"])

        # Text result is now saved, so start fusion safely in background.
        # Frontend should not call run_multimodal_fusion immediately after upload.
        update_session_progress(
            session,
            current_activity="fusion_processing",
            completed_count=3,
            status="processing",
        )

        fusion_task_id = async_task(
            "mindspace.tasks.assessments.process_fusion_task",
            str(session.screening_session_id),
        )

        return {
            "ok": True,
            "message": "Scenario analysis completed. Fusion started in background.",
            "fusion_task_id": fusion_task_id,
            "next_url": "/assessments/activity-complete/",
        }

    except Exception as exc:
        logger.exception("Scenario voice task failed")
        try:
            session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
            mark_session_failed(session, exc)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}


def process_fusion_task(screening_session_id):
    try:
        session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)

        face_result = ModalityResult.objects.filter(screening_session=session, modality="face").order_by("-created_at").first()
        voice_result = ModalityResult.objects.filter(screening_session=session, modality="voice").order_by("-created_at").first()
        text_result = ModalityResult.objects.filter(screening_session=session, modality="text").order_by("-created_at").first()

        if not face_result:
            raise RuntimeError("Face result missing. Complete Activity 1 first.")
        if not voice_result:
            raise RuntimeError("Voice result missing. Complete Activity 2 first.")
        if not text_result:
            raise RuntimeError("Text result missing. Complete Activity 3 first.")

        combined_features = build_fusion_feature_payload(
            face_result.result_payload or {},
            voice_result.result_payload or {},
            text_result.result_payload or {},
        )

        fusion_response, fusion_latency = post_fusion_score(combined_features)
        overall_risk = pick_final_risk(fusion_response)

        prediction, _ = FusionPrediction.objects.update_or_create(
            screening_session=session,
            defaults={
                **create_analysis_defaults(FusionPrediction, fusion_response),
                "overall_risk": overall_risk,
                "final_prediction_json": {
                    "combined_features_count": len(combined_features),
                    "score_response": make_json_safe(fusion_response),
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
            "overall_risk", "session_status", "current_activity",
            "completed_activities_count", "workflow_stage", "completed_at",
        ])

        return {"ok": True, "prediction_id": str(prediction.prediction_id), "next_url": "/assessments/activity-complete/"}

    except Exception as exc:
        logger.exception("Fusion task failed")
        try:
            session = PlatformScreeningSession.objects.get(screening_session_id=screening_session_id)
            mark_session_failed(session, exc)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}