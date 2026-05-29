"""
MindSpace Django models generated from mindspace_django_schema.sql.

Important setup:
1. Do NOT create Django auth tables manually in models.py.
   Django creates auth_user, auth_group, django_session, django_content_type,
   and django_migrations automatically.

2. These models use Django's built-in user model through settings.AUTH_USER_MODEL.

3. Because the SQL schema uses PostgreSQL VECTOR fields, install pgvector:
      pip install pgvector
   and add this migration operation before using VectorField:
      VectorExtension()

4. If you already created the database tables manually using SQL, keep
   managed = False in Meta. If you want Django migrations to create/manage
   these tables, change MANAGED_BY_DJANGO to True below.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from decimal import Decimal, InvalidOperation
import re


# Set this to False if tables already exist from raw SQL/imported schema.
# Set this to True if you want Django migrations to create these tables.
MANAGED_BY_DJANGO = True


# ============================================================
# APPLICATION-LEVEL INPUT VALIDATION HELPERS
# ============================================================
# Database CheckConstraints protect the database. These helpers protect
# forms/views/serializers before unsafe or malformed data is saved.

NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s.'-]{2,100}$")
PHONE_RE = re.compile(r"^\+?[0-9]{10,15}$")
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_:-]{1,79}$")
LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
AVATAR_RE = re.compile(r"^avatar_[1-8]\.(png|jpg|jpeg|webp)$", re.IGNORECASE)
SAFE_FILENAME_RE = re.compile(r"^[\w\s().,\-]+\.[A-Za-z0-9]{1,10}$")
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
GENDER_VALUES = {"male", "female", "other", "prefer_not_to_say"}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska"}
AUDIO_CONTENT_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/webm", "audio/ogg", "audio/mp4", "audio/m4a"}


def _to_decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field_name: "Enter a valid numeric value."})


def _validate_range(value, field_name, minimum=None, maximum=None):
    if value is None or value == "":
        return
    number = _to_decimal(value, field_name)
    if minimum is not None and number < Decimal(str(minimum)):
        raise ValidationError({field_name: f"Value must be at least {minimum}."})
    if maximum is not None and number > Decimal(str(maximum)):
        raise ValidationError({field_name: f"Value must be at most {maximum}."})


def _reject_dangerous_text(value, field_name):
    """Basic anti-XSS / path traversal guard for text stored from users or APIs."""
    if value is None:
        return
    lowered = str(value).lower()
    blocked = ("<script", "</script", "javascript:", "onerror=", "onload=", "\x00")
    if any(token in lowered for token in blocked):
        raise ValidationError({field_name: "Unsafe text content is not allowed."})


def _validate_name(value, field_name):
    if value and not NAME_RE.fullmatch(value.strip()):
        raise ValidationError({
            field_name: "Use 2-100 letters only. Spaces, dot, apostrophe and hyphen are allowed."
        })


def _validate_phone(value, field_name):
    if value and not PHONE_RE.fullmatch(value.strip()):
        raise ValidationError({
            field_name: "Enter a valid phone number with 10-15 digits. Country code is allowed."
        })


def _validate_code(value, field_name):
    if value and not CODE_RE.fullmatch(value.strip().lower()):
        raise ValidationError({
            field_name: "Use lowercase letters, numbers, underscore, colon or hyphen only."
        })


def _validate_language_code(value, field_name):
    if value and not LANGUAGE_CODE_RE.fullmatch(value.strip()):
        raise ValidationError({field_name: "Use language format like hi, en, or en-US."})


def _validate_json_container(value, field_name, allowed=(dict, list)):
    if value is not None and not isinstance(value, allowed):
        names = ", ".join(t.__name__ for t in allowed)
        raise ValidationError({field_name: f"JSON value must be {names}."})


def _validate_url(value, field_name):
    if not value:
        return
    validator = URLValidator(schemes=["http", "https"])
    try:
        validator(value)
    except ValidationError:
        raise ValidationError({field_name: "Enter a valid http/https URL."})


def _validate_file_name(value, field_name):
    if not value:
        return
    if "/" in value or "\\" in value or ".." in value:
        raise ValidationError({field_name: "File name cannot contain path separators or '..'."})
    if not SAFE_FILENAME_RE.fullmatch(value.strip()):
        raise ValidationError({field_name: "Enter a safe file name with a valid extension."})


def _validate_object_key(value, field_name):
    if not value:
        return
    if value.startswith("/") or ".." in value or "\\" in value or "\x00" in value:
        raise ValidationError({field_name: "Storage object key is not safe."})


class ValidatedModelMixin:
    """
    Reusable model validation.
    Use `instance.full_clean()` before saving from custom views/tasks.
    ModelForms and DRF serializers can call this through normal validation flows.
    """

    def clean(self):
        super_clean = getattr(super(), "clean", None)
        if callable(super_clean):
            super_clean()

        # Strip strings and reject obvious unsafe text payloads.
        for field in self._meta.fields:
            value = getattr(self, field.name, None)

            if isinstance(field, (models.CharField, models.TextField)) and isinstance(value, str):
                value = value.strip()
                setattr(self, field.name, value)
                _reject_dangerous_text(value, field.name)

            if field.name.endswith("_json"):
                _validate_json_container(value, field.name)

            if field.name.endswith("_score"):
                if "confidence" in field.name:
                    _validate_range(value, field.name, 0, 1)
                else:
                    _validate_range(value, field.name, 0, 100)

            if field.name in {"size_bytes", "request_size_bytes", "response_size_bytes",
                              "processing_time_ms", "silence_duration_ms", "response_time_ms",
                              "workflow_stage", "completed_activities_count", "feature_count",
                              "input_feature_count", "output_feature_count", "analysis_count"}:
                _validate_range(value, field.name, 0, None)

            if field.name in {"timeout_seconds"}:
                _validate_range(value, field.name, 1, None)

            if field.name in {"retry_count"}:
                _validate_range(value, field.name, 0, None)

            if field.name == "port":
                _validate_range(value, field.name, 1, 65535)

            if field.name in {"base_url", "cdn_url", "endpoint_url"}:
                _validate_url(value, field.name)

            if field.name in {"file_name"}:
                _validate_file_name(value, field.name)

            if field.name in {"object_key"}:
                _validate_object_key(value, field.name)

            if field.name in {"activity_code", "scenario_code", "service_type", "event_type"}:
                _validate_code(value, field.name)

            if field.name == "language_code":
                _validate_language_code(value, field.name)

        # Generic date-order checks used by multiple models.
        for start_field, end_field in [
            ("started_at", "completed_at"),
            ("processing_started_at", "processing_completed_at"),
            ("created_at", "deleted_at"),
        ]:
            start_value = getattr(self, start_field, None)
            end_value = getattr(self, end_field, None)
            if start_value and end_value and end_value < start_value:
                raise ValidationError({end_field: f"{end_field} cannot be before {start_field}."})



class UserRole(models.TextChoices):
    USER = "user", "User"
    ADMIN = "admin", "Admin"
    COUNSELOR = "counselor", "Counselor"
    RESEARCHER = "researcher", "Researcher"


class AccountStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DELETED = "deleted", "Deleted"


class SessionStatus(models.TextChoices):
    STARTED = "started", "Started"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class RiskLevel(models.TextChoices):
    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class Modality(models.TextChoices):
    FACE = "face", "Face"
    VOICE = "voice", "Voice"
    TEXT = "text", "Text"


class MediaType(models.TextChoices):
    ACTIVITY_VIDEO = "activity_video", "Activity Video"
    PHONATION_AUDIO = "phonation_audio", "Phonation Audio"
    SCENARIO_AUDIO = "scenario_audio", "Scenario Audio"
    IMAGE = "image", "Image"


class UploadStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UPLOADING = "uploading", "Uploading"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    DELETED = "deleted", "Deleted"


class ProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ActivityStage(models.TextChoices):
    CHECK_IN = "check_in", "Check In"
    FACE_VIDEO = "face_video", "Face Video"
    VOICE_PHONATION = "voice_phonation", "Voice Phonation"
    SCENARIO_VOICE_RESPONSE = "scenario_voice_response", "Scenario Voice Response"
    FUSION = "fusion", "Fusion"
    COMPLETED = "completed", "Completed"
    ERROR = "error", "Error"
    ABANDONED = "abandoned", "Abandoned"


class ApiHealthStatus(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    DEGRADED = "degraded", "Degraded"
    DOWN = "down", "Down"
    UNKNOWN = "unknown", "Unknown"


class SeverityLevel(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class MentalHealthLabel(models.TextChoices):
    NORMAL = "normal", "Normal"
    BIPOLAR = "bipolar", "Bipolar"
    ANXIETY = "anxiety", "Anxiety"
    SUICIDAL_TENDENCY = "suicidal_tendency", "Suicidal Tendency"
    STRESS = "stress", "Stress"
    DEPRESSION = "depression", "Depression"
    UNKNOWN = "unknown", "Unknown"


class TimeStampedModel(ValidatedModelMixin, models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PendingSignup(ValidatedModelMixin, models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("counselor", "Counselor"),
    ]

    pending_signup_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default="user")

    password_hash = models.CharField(max_length=255)

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    terms_accepted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


    def clean(self):
        super().clean()
        _validate_name(self.name, "name")
        if not self.terms_accepted:
            raise ValidationError({"terms_accepted": "Terms must be accepted before signup."})
        if self.password_hash and len(self.password_hash) < 20:
            raise ValidationError({"password_hash": "Password hash looks invalid or too short."})
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        if self.expires_at <= timezone.now() and self._state.adding:
            raise ValidationError({"expires_at": "Expiry time must be in the future."})

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.email} pending verification"


class UserProfile(TimeStampedModel):
    """
    Custom profile table connected to Django's built-in auth user.
    This replaces the custom SQL users table.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="profile",
        db_column="user_id",
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.USER)
    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
    )
    is_email_verified = models.BooleanField(default=False)

    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)

    avatar = models.CharField(
        max_length=100,
        default="avatar_1.png",
        blank=True,
        null=True,
    )
    
    mobile_number = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    profile_completed = models.BooleanField(default=False)
    consented = models.BooleanField(default=False)
    consent_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        super().clean()
        _validate_name(self.name, "name")
        if not self.terms_accepted:
            raise ValidationError({"terms_accepted": "Terms must be accepted before signup."})
        if self.password_hash and len(self.password_hash) < 20:
            raise ValidationError({"password_hash": "Password hash looks invalid or too short."})
        if self.expires_at and self.expires_at <= timezone.now() and self._state.adding:
            raise ValidationError({"expires_at": "Expiry time must be in the future."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "user_profiles"
        indexes = [
            models.Index(fields=["role"], name="idx_user_profiles_role"),
            models.Index(fields=["account_status"], name="idx_user_profiles_status"),
        ]

    def __str__(self):
        return f"{self.user} - {self.role}"


class PlatformScreeningSession(ValidatedModelMixin, models.Model):
    screening_session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="screening_sessions",
        db_column="user_id",
    )
    session_status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.STARTED,
    )
    current_activity = models.CharField(max_length=50, choices=ActivityStage.choices, blank=True, null=True)
    workflow_stage = models.PositiveIntegerField(default=1)
    completed_activities_count = models.PositiveIntegerField(default=0)
    overall_risk = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        blank=True,
        null=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        super().clean()
        if self.session_status == SessionStatus.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        if self.completed_activities_count > 10:
            raise ValidationError({"completed_activities_count": "Completed activity count is too high."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "platform_screening_sessions"
        indexes = [
            models.Index(fields=["user", "-started_at"], name="idx_screening_user_created"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(workflow_stage__gte=1), name="screening_workflow_stage_gte_1"),
            models.CheckConstraint(condition=Q(completed_activities_count__gte=0), name="screening_completed_count_gte_0"),
        ]

    def __str__(self):
        return f"Session {self.screening_session_id} - {self.user}"


class MediaAsset(TimeStampedModel):
    media_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="media_assets",
        db_column="user_id",
    )
    media_type = models.CharField(max_length=30, choices=MediaType.choices)
    file_name = models.CharField(max_length=500)
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    duration_seconds = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    storage_provider = models.CharField(max_length=50, default="gcp")
    bucket_name = models.CharField(max_length=255, blank=True, null=True)
    bucket_region = models.CharField(max_length=100, blank=True, null=True)
    storage_class = models.CharField(max_length=100, blank=True, null=True)
    object_key = models.TextField()
    cdn_url = models.TextField(blank=True, null=True)
    is_public = models.BooleanField(default=False)
    retention_delete_at = models.DateTimeField(blank=True, null=True)
    checksum_hash = models.CharField(max_length=255, blank=True, null=True)
    upload_status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.PENDING,
    )
    metadata_json = models.JSONField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        super().clean()
        if self.media_type == MediaType.IMAGE and self.content_type not in IMAGE_CONTENT_TYPES:
            raise ValidationError({"content_type": "Image media must use jpeg, png, or webp."})
        if self.media_type == MediaType.ACTIVITY_VIDEO and self.content_type not in VIDEO_CONTENT_TYPES:
            raise ValidationError({"content_type": "Activity video must use mp4, webm, mov, or mkv."})
        if self.media_type in {MediaType.PHONATION_AUDIO, MediaType.SCENARIO_AUDIO} and self.content_type not in AUDIO_CONTENT_TYPES:
            raise ValidationError({"content_type": "Audio media must use mp3, wav, webm, ogg, mp4, or m4a."})
        _validate_range(self.duration_seconds, "duration_seconds", 0, 3600)
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "media_assets"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_media_assets_user_created"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(size_bytes__gte=0), name="media_size_bytes_gte_0"),
            models.CheckConstraint(condition=Q(duration_seconds__gte=0) | Q(duration_seconds__isnull=True),
                name="media_duration_seconds_gte_0",
            ),
        ]

    def __str__(self):
        return self.file_name


class VideoActivity(ValidatedModelMixin, models.Model):
    video_activity_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    instruction_text = models.TextField()
    image_set_json = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        _validate_code(self.activity_code, "activity_code")
        if len(self.title.strip()) < 3:
            raise ValidationError({"title": "Title must be at least 3 characters."})
        if len(self.instruction_text.strip()) < 10:
            raise ValidationError({"instruction_text": "Instruction text must be at least 10 characters."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "video_activities"

    def __str__(self):
        return self.title


class VideoSession(ValidatedModelMixin, models.Model):
    video_session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screening_session = models.ForeignKey(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="video_sessions",
        db_column="screening_session_id",
    )
    video_activity = models.ForeignKey(
        VideoActivity,
        on_delete=models.PROTECT,
        related_name="video_sessions",
        db_column="video_activity_id",
    )
    media = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        related_name="video_sessions",
        db_column="media_id",
        blank=True,
        null=True,
    )
    extraction_status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING)
    analysis_status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING)
    session_status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.STARTED)
    processing_started_at = models.DateTimeField(blank=True, null=True)
    processing_completed_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        super().clean()
        if self.completed_at and self.session_status != SessionStatus.COMPLETED:
            raise ValidationError({"session_status": "Completed time requires completed session status."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "video_sessions"

    def __str__(self):
        return f"Video session {self.video_session_id}"


class FaceFeatureVector(ValidatedModelMixin, models.Model):
    feature_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    video_session = models.ForeignKey(
        VideoSession,
        on_delete=models.CASCADE,
        related_name="face_feature_vectors",
        db_column="video_session_id",
    )

    # Store all face feature extraction attributes here
    # Example:
    # {
    #   "nod_onset_latency__mean": 0.056,
    #   "reaction_time_instability_index__range": 0.0,
    #   "speech_onset_delay__min": 0.0,
    #   ...
    # }
    feature_json = models.JSONField(blank=True, null=True)

    # Store complete raw API response if needed
    raw_response_json = models.JSONField(blank=True, null=True)

    feature_schema_version = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="face_63_features_v1",
    )

    api_processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.feature_json, "feature_json", allowed=(dict,))
        _validate_json_container(self.raw_response_json, "raw_response_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "face_feature_vectors"
        indexes = [
            models.Index(
                fields=["video_session", "-created_at"],
                name="idx_face_feature_video_created",
            ),
        ]

    def __str__(self):
        return f"Face features - {self.feature_id}"
    

class FacialAnalysisResult(ValidatedModelMixin, models.Model):
    facial_analysis_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature = models.OneToOneField(
        FaceFeatureVector,
        on_delete=models.CASCADE,
        related_name="facial_analysis_result",
        db_column="feature_id",
    )
    normal_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    bipolar_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    anxiety_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    suicidal_tendency_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    stress_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    depression_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    prediction_label = models.CharField(max_length=50, choices=MentalHealthLabel.choices, blank=True, null=True)
    probabilities_json = models.JSONField(blank=True, null=True)
    raw_response_json = models.JSONField(blank=True, null=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    risk_label = models.CharField(max_length=100, blank=True, null=True)
    api_version = models.CharField(max_length=100, blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.probabilities_json, "probabilities_json", allowed=(dict,))
        _validate_json_container(self.raw_response_json, "raw_response_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "facial_analysis_results"
        constraints = [
            models.CheckConstraint(condition=Q(stress_score__gte=0, stress_score__lte=100) | Q(stress_score__isnull=True), name="face_stress_score_0_100"),
            models.CheckConstraint(condition=Q(depression_score__gte=0, depression_score__lte=100) | Q(depression_score__isnull=True), name="face_depression_score_0_100"),
            models.CheckConstraint(condition=Q(anxiety_score__gte=0, anxiety_score__lte=100) | Q(anxiety_score__isnull=True), name="face_anxiety_score_0_100"),
            models.CheckConstraint(condition=Q(confidence_score__gte=0, confidence_score__lte=1) | Q(confidence_score__isnull=True), name="face_confidence_score_0_1"),
        ]


class PhonationSound(ValidatedModelMixin, models.Model):
    sound_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    language_code = models.CharField(max_length=10)
    sound_character = models.CharField(max_length=50)
    sound_name = models.CharField(max_length=255)
    sound_order = models.IntegerField()

    def clean(self):
        super().clean()
        _validate_language_code(self.language_code, "language_code")
        if self.sound_order < 1:
            raise ValidationError({"sound_order": "Sound order must be 1 or greater."})
        if not self.sound_character.strip():
            raise ValidationError({"sound_character": "Sound character is required."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "phonation_sounds"
        ordering = ["sound_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["language_code", "sound_character"],
                name="unique_language_sound_character",
            ),
        ]

    def __str__(self):
        return f"{self.sound_character} - {self.sound_name}"


class PhonationSession(ValidatedModelMixin, models.Model):
    phonation_session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screening_session = models.OneToOneField(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="phonation_session",
        db_column="screening_session_id",
    )
    session_status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.STARTED)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "phonation_sessions"


class PhonationAttempt(ValidatedModelMixin, models.Model):
    attempt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phonation_session = models.ForeignKey(
        PhonationSession,
        on_delete=models.CASCADE,
        related_name="attempts",
        db_column="phonation_session_id",
    )
    sound = models.ForeignKey(
        PhonationSound,
        on_delete=models.PROTECT,
        related_name="attempts",
        db_column="sound_id",
    )
    media = models.ForeignKey(
        MediaAsset,
        on_delete=models.PROTECT,
        related_name="phonation_attempts",
        db_column="media_id",
    )
    pronunciation_detected = models.BooleanField(blank=True, null=True)
    character_accuracy_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    noise_level = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    silence_duration_ms = models.PositiveIntegerField(blank=True, null=True)
    response_time_ms = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_range(self.noise_level, "noise_level", 0, None)
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "phonation_attempts"
        constraints = [
            models.UniqueConstraint(fields=["phonation_session", "sound"], name="unique_phonation_session_sound"),
            models.CheckConstraint(condition=Q(character_accuracy_score__gte=0, character_accuracy_score__lte=100) | Q(character_accuracy_score__isnull=True),
                name="phonation_accuracy_score_0_100",
            ),
            models.CheckConstraint(condition=Q(silence_duration_ms__gte=0) | Q(silence_duration_ms__isnull=True), name="phonation_silence_duration_gte_0"),
            models.CheckConstraint(condition=Q(response_time_ms__gte=0) | Q(response_time_ms__isnull=True), name="phonation_response_time_gte_0"),
        ]


class AudioExtractionResult(ValidatedModelMixin, models.Model):
    audio_extraction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.OneToOneField(
        PhonationAttempt,
        on_delete=models.CASCADE,
        related_name="audio_extraction_result",
        db_column="attempt_id",
    )
    raw_wave_features = models.JSONField(blank=True, null=True)
    noise_profile = models.JSONField(blank=True, null=True)
    frequency_profile = models.JSONField(blank=True, null=True)
    extraction_status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING)
    processed_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.raw_wave_features, "raw_wave_features", allowed=(dict,))
        _validate_json_container(self.noise_profile, "noise_profile", allowed=(dict,))
        _validate_json_container(self.frequency_profile, "frequency_profile", allowed=(dict,))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "audio_extraction_results"


class PhonationFeature(ValidatedModelMixin, models.Model):
    feature_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    audio_extraction = models.OneToOneField(
        AudioExtractionResult,
        on_delete=models.CASCADE,
        related_name="phonation_feature",
        db_column="audio_extraction_id",
    )

    # Store all 6373 voice extraction features here.
    # Example:
    # {
    #   "F0semitoneFrom27.5Hz_sma3nz_amean": 23.52,
    #   "jitterLocal_sma3nz_amean": 0.012,
    #   "shimmerLocaldB_sma3nz_amean": 0.33,
    #   ...
    # }
    voice_features_json = models.JSONField(blank=True, null=True)

    # Store complete original Voice Feature Extract API response.
    raw_response_json = models.JSONField(blank=True, null=True)

    feature_count = models.PositiveIntegerField(default=0)

    feature_schema_version = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="voice_6373_features_v1",
    )

    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.voice_features_json, "voice_features_json", allowed=(dict,))
        _validate_json_container(self.raw_response_json, "raw_response_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "phonation_features"
        indexes = [
            models.Index(
                fields=["audio_extraction", "-created_at"],
                name="idx_phon_feat_ext_created",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(feature_count__gte=0),
                name="phonation_feature_count_gte_0",
            ),
        ]

    def __str__(self):
        return f"Phonation features - {self.feature_id}"


class VoiceAnalysisResult(ValidatedModelMixin, models.Model):
    voice_analysis_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature = models.OneToOneField(
        PhonationFeature,
        on_delete=models.CASCADE,
        related_name="voice_analysis_result",
        db_column="feature_id",
    )
    normal_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    bipolar_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    anxiety_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    suicidal_tendency_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    stress_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    depression_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    speech_impairment_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    prediction_label = models.CharField(max_length=50, choices=MentalHealthLabel.choices, blank=True, null=True)
    probabilities_json = models.JSONField(blank=True, null=True)
    raw_response_json = models.JSONField(blank=True, null=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    api_version = models.CharField(max_length=100, blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.probabilities_json, "probabilities_json", allowed=(dict,))
        _validate_json_container(self.raw_response_json, "raw_response_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "voice_analysis_results"
        constraints = [
            models.CheckConstraint(condition=Q(stress_score__gte=0, stress_score__lte=100) | Q(stress_score__isnull=True), name="voice_stress_score_0_100"),
            models.CheckConstraint(condition=Q(depression_score__gte=0, depression_score__lte=100) | Q(depression_score__isnull=True), name="voice_depression_score_0_100"),
            models.CheckConstraint(condition=Q(speech_impairment_score__gte=0, speech_impairment_score__lte=100) | Q(speech_impairment_score__isnull=True), name="voice_speech_score_0_100"),
            models.CheckConstraint(condition=Q(confidence_score__gte=0, confidence_score__lte=1) | Q(confidence_score__isnull=True), name="voice_confidence_score_0_1"),
        ]


class AudioScenario(ValidatedModelMixin, models.Model):
    audio_scenario_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scenario_code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    prompt_text = models.TextField()
    is_active = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        _validate_code(self.scenario_code, "scenario_code")
        if len(self.title.strip()) < 3:
            raise ValidationError({"title": "Title must be at least 3 characters."})
        if len(self.prompt_text.strip()) < 10:
            raise ValidationError({"prompt_text": "Prompt text must be at least 10 characters."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "audio_scenarios"

    def __str__(self):
        return self.title


class ScenarioSession(ValidatedModelMixin, models.Model):
    scenario_session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screening_session = models.ForeignKey(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="scenario_sessions",
        db_column="screening_session_id",
    )
    audio_scenario = models.ForeignKey(
        AudioScenario,
        on_delete=models.PROTECT,
        related_name="scenario_sessions",
        db_column="audio_scenario_id",
    )
    media = models.ForeignKey(
        MediaAsset,
        on_delete=models.PROTECT,
        related_name="scenario_sessions",
        db_column="media_id",
        blank=True,
        null=True,
    )
    session_status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.STARTED)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        super().clean()
        if self.completed_at and self.session_status != SessionStatus.COMPLETED:
            raise ValidationError({"session_status": "Completed time requires completed session status."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "scenario_sessions"


class Transcript(ValidatedModelMixin, models.Model):
    transcript_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scenario_session = models.OneToOneField(
        ScenarioSession,
        on_delete=models.CASCADE,
        related_name="transcript",
        db_column="scenario_session_id",
    )
    transcript_text = models.TextField()
    language_code = models.CharField(max_length=10, blank=True, null=True)
    stt_provider = models.CharField(max_length=100, blank=True, null=True)
    stt_model = models.CharField(max_length=100, blank=True, null=True)
    duration_seconds = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    transcript_json = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_language_code(self.language_code, "language_code")
        if not self.transcript_text or len(self.transcript_text.strip()) < 1:
            raise ValidationError({"transcript_text": "Transcript cannot be empty."})
        if len(self.transcript_text) > 10000:
            raise ValidationError({"transcript_text": "Transcript is too long."})
        _validate_json_container(self.transcript_json, "transcript_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "transcripts"

    def __str__(self):
        return self.transcript_text[:80]


class TextParameterResult(ValidatedModelMixin, models.Model):
    text_parameter_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    transcript = models.OneToOneField(
        Transcript,
        on_delete=models.CASCADE,
        related_name="text_parameter_result",
        db_column="transcript_id",
    )

    # Store all text extraction attributes here.
    # Example:
    # {
    #   "total_word_count": 120,
    #   "unique_word_count": 82,
    #   "type_token_ratio_ttr": 0.68,
    #   "moving_average_ttr": 0.55,
    #   "hapax_legoman_ratio": 0.31,
    #   "sentence_count": 8,
    #   "average_sentence_length": 15.0,
    #   "cognitive_load_score": 0.74,
    #   "mental_health_label": "stress"
    # }
    linguistic_features = models.JSONField(blank=True, null=True)

    # Store complete original Text Feature Extraction API response.
    raw_response_json = models.JSONField(blank=True, null=True)

    feature_schema_version = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="text_features_v1",
    )

    api_version = models.CharField(max_length=100, blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.linguistic_features, "linguistic_features", allowed=(dict,))
        _validate_json_container(self.raw_response_json, "raw_response_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "text_parameter_results"
        indexes = [
            models.Index(
                fields=["transcript", "-created_at"],
                name="idx_text_param_tr_created",
            ),
        ]

    def __str__(self):
        return f"Text parameters - {self.text_parameter_id}"


class TextAnalysisResult(ValidatedModelMixin, models.Model):
    text_analysis_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text_parameter = models.OneToOneField(
        TextParameterResult,
        on_delete=models.CASCADE,
        related_name="text_analysis_result",
        db_column="text_parameter_id",
    )
    normal_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    bipolar_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    anxiety_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    suicidal_tendency_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    stress_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    depression_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    prediction_label = models.CharField(max_length=50, choices=MentalHealthLabel.choices, blank=True, null=True)
    probabilities_json = models.JSONField(blank=True, null=True)
    raw_response_json = models.JSONField(blank=True, null=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    api_version = models.CharField(max_length=100, blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.probabilities_json, "probabilities_json", allowed=(dict,))
        _validate_json_container(self.raw_response_json, "raw_response_json", allowed=(dict, list))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "text_analysis_results"
        constraints = [
            models.CheckConstraint(condition=Q(stress_score__gte=0, stress_score__lte=100) | Q(stress_score__isnull=True), name="text_stress_score_0_100"),
            models.CheckConstraint(condition=Q(depression_score__gte=0, depression_score__lte=100) | Q(depression_score__isnull=True), name="text_depression_score_0_100"),
            models.CheckConstraint(condition=Q(anxiety_score__gte=0, anxiety_score__lte=100) | Q(anxiety_score__isnull=True), name="text_anxiety_score_0_100"),
            models.CheckConstraint(condition=Q(confidence_score__gte=0, confidence_score__lte=1) | Q(confidence_score__isnull=True), name="text_confidence_score_0_1"),
        ]


class PcaPipelineResult(ValidatedModelMixin, models.Model):
    pca_result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    screening_session = models.ForeignKey(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="pca_pipeline_results"
    )

    phonation_feature = models.ForeignKey(
        PhonationFeature,
        on_delete=models.CASCADE,
        related_name="pca_pipeline_results",
        null=False,
        blank=False,
    )

    input_feature_count = models.IntegerField(default=0)
    output_feature_count = models.IntegerField(default=0)

    raw_features_json = models.JSONField(default=dict, blank=True)
    pca_response_json = models.JSONField(default=dict, blank=True)
    # pca_components stores dict shape:
    # {"PC1": value, "PC2": value, ..., "PC24": value}
    pca_components = models.JSONField(default=dict, blank=True)
    # pca_features stores list shape:
    # [PC1, PC2, ..., PC24]
    pca_features = models.JSONField(default=list, blank=True)

    latency_seconds = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    status = models.CharField(max_length=50, default="completed")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.raw_features_json, "raw_features_json", allowed=(dict,))
        _validate_json_container(self.pca_response_json, "pca_response_json", allowed=(dict,))
        _validate_json_container(self.pca_components, "pca_components", allowed=(dict,))
        _validate_json_container(self.pca_features, "pca_features", allowed=(list,))
        if self.output_feature_count and self.output_feature_count > self.input_feature_count:
            raise ValidationError({"output_feature_count": "Output feature count cannot exceed input feature count."})
        _validate_range(self.latency_seconds, "latency_seconds", 0, None)
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "pca_pipeline_results"
        indexes = [
            models.Index(fields=["screening_session", "-created_at"], name="idx_pca_session_created"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["screening_session", "phonation_feature"],
                name="unique_pca_per_session_phonation_feature",
            ),
            models.CheckConstraint(condition=Q(input_feature_count__gte=0), name="pca_input_count_gte_0"),
            models.CheckConstraint(condition=Q(output_feature_count__gte=0), name="pca_output_count_gte_0"),
        ]

    def __str__(self):
        return f"PCA Result - {self.screening_session_id}"
    
class FusionPrediction(ValidatedModelMixin, models.Model):
    prediction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    screening_session = models.OneToOneField(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="fusion_prediction",
        db_column="screening_session_id",
    )

    normal_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    bipolar_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    anxiety_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    suicidal_tendency_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    suicidal_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    stress_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    depression_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    overall_risk = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        blank=True,
        null=True,
    )

    prediction_label = models.CharField(max_length=50, choices=MentalHealthLabel.choices, blank=True, null=True)
    probabilities_json = models.JSONField(blank=True, null=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    final_prediction_json = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        _validate_json_container(self.probabilities_json, "probabilities_json", allowed=(dict,))
        _validate_json_container(self.final_prediction_json, "final_prediction_json", allowed=(dict,))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "fusion_predictions"
        constraints = [
            models.CheckConstraint(
                condition=Q(confidence_score__gte=0, confidence_score__lte=1) | Q(confidence_score__isnull=True),
                name="fusion_confidence_score_0_1",
            ),
        ]

    def __str__(self):
        return f"Fusion Prediction - {self.screening_session_id}"


class UserPredictionSummary(ValidatedModelMixin, models.Model):
    summary_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prediction_summary",
        db_column="user_id",
    )

    latest_screening_session = models.ForeignKey(
        "PlatformScreeningSession",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="user_prediction_summaries",
        db_column="latest_screening_session_id",
    )

    latest_fusion_prediction = models.ForeignKey(
        "FusionPrediction",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="user_prediction_summaries",
        db_column="latest_fusion_prediction_id",
    )

    # Highest risk class from latest completed pipeline.
    latest_prediction_label = models.CharField(max_length=80, blank=True, null=True)
    latest_prediction_source = models.CharField(
        max_length=80,
        blank=True,
        null=True,
        help_text="Usually fusion. Fallback can be face, voice, or text.",
    )

    latest_confidence_score = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        blank=True,
        null=True,
    )

    # Previous latest label before this update.
    previous_prediction_label = models.CharField(max_length=80, blank=True, null=True)
    previous_confidence_score = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        blank=True,
        null=True,
    )

    prediction_changed = models.BooleanField(default=False)

    # Disease row/column matrix.
    # Example:
    # {
    #   "normal": {"face": 10, "voice": 5, "text": 2, "fusion": 3},
    #   "anxiety": {"face": 30, "voice": 20, "text": 45, "fusion": 50},
    #   "stress": {"face": 60, "voice": 40, "text": 55, "fusion": 62}
    # }
    disease_score_matrix_json = models.JSONField(blank=True, null=True)

    # Highest class per modality.
    # Example:
    # {
    #   "face": {"label": "stress", "score": 60},
    #   "voice": {"label": "bipolar", "score": 80},
    #   "text": {"label": "anxiety", "score": 65},
    #   "fusion": {"label": "bipolar", "score": 91}
    # }
    modality_winners_json = models.JSONField(blank=True, null=True)

    # Full latest summary snapshot.
    latest_summary_json = models.JSONField(blank=True, null=True)

    # Previous summary snapshot before update.
    previous_summary_json = models.JSONField(blank=True, null=True)

    # Optional simple trend.
    # Example:
    # {
    #   "changed_from": "stress",
    #   "changed_to": "bipolar",
    #   "confidence_delta": 0.15
    # }
    trend_json = models.JSONField(blank=True, null=True)

    analysis_count = models.PositiveIntegerField(default=0)

    last_analyzed_at = models.DateTimeField(blank=True, null=True)
    #resend or current summary created_at can be used to determine recency instead of screening session time which can be old.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        _validate_range(self.latest_confidence_score, "latest_confidence_score", 0, 1)
        _validate_range(self.previous_confidence_score, "previous_confidence_score", 0, 1)
        _validate_json_container(self.disease_score_matrix_json, "disease_score_matrix_json", allowed=(dict,))
        _validate_json_container(self.modality_winners_json, "modality_winners_json", allowed=(dict,))
        _validate_json_container(self.latest_summary_json, "latest_summary_json", allowed=(dict,))
        _validate_json_container(self.previous_summary_json, "previous_summary_json", allowed=(dict,))
        _validate_json_container(self.trend_json, "trend_json", allowed=(dict,))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "user_prediction_summaries"
        indexes = [
            models.Index(fields=["user"], name="idx_user_pred_summary_user"),
            models.Index(fields=["-last_analyzed_at"], name="idx_user_pred_summary_time"),
            models.Index(fields=["latest_prediction_label"], name="idx_user_pred_summary_label"),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.latest_prediction_label or 'no prediction'}"


class AiApiRegistry(ValidatedModelMixin, models.Model):
    api_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_name = models.CharField(max_length=255, unique=True)
    service_type = models.CharField(max_length=100)
    base_url = models.TextField()
    port = models.IntegerField(blank=True, null=True)
    endpoint_path = models.TextField(blank=True, null=True)
    model_version = models.CharField(max_length=100, blank=True, null=True)
    timeout_seconds = models.PositiveIntegerField(default=30)
    retry_count = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    health_status = models.CharField(max_length=50, choices=ApiHealthStatus.choices, default=ApiHealthStatus.UNKNOWN)
    metadata_json = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        _validate_url(self.base_url, "base_url")
        if self.endpoint_path and not self.endpoint_path.startswith("/"):
            raise ValidationError({"endpoint_path": "Endpoint path must start with /."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "ai_api_registry"
        indexes = [
            models.Index(fields=["service_type", "is_active"], name="idx_api_service_active"),
            models.Index(fields=["health_status"], name="idx_api_health_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["base_url", "port", "endpoint_path"],
                name="unique_api_endpoint",
            ),
            models.CheckConstraint(condition=Q(timeout_seconds__gt=0), name="api_timeout_seconds_gt_0"),
            models.CheckConstraint(condition=Q(retry_count__gte=0), name="api_retry_count_gte_0"),
        ]

    def __str__(self):
        return self.api_name


class ApiExecutionLog(ValidatedModelMixin, models.Model):
    execution_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screening_session = models.ForeignKey(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="api_execution_logs",
        db_column="screening_session_id",
    )
    api = models.ForeignKey(
        AiApiRegistry,
        on_delete=models.PROTECT,
        related_name="execution_logs",
        db_column="api_id",
    )
    activity_type = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    modality = models.CharField(max_length=20, choices=Modality.choices, blank=True, null=True, db_index=True)
    endpoint_url = models.TextField(blank=True, null=True)
    http_method = models.CharField(max_length=10, default="POST")
    request_payload = models.JSONField(blank=True, null=True)
    response_payload = models.JSONField(blank=True, null=True)
    request_size_bytes = models.BigIntegerField(blank=True, null=True)
    response_size_bytes = models.BigIntegerField(blank=True, null=True)
    response_status = models.IntegerField(blank=True, null=True)
    external_request_id = models.CharField(max_length=255, blank=True, null=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    timeout_seconds = models.PositiveIntegerField(blank=True, null=True)
    execution_status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING)
    error_message = models.TextField(blank=True, null=True)
    processing_time_ms = models.PositiveIntegerField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        method = (self.http_method or "").upper()
        if method not in HTTP_METHODS:
            raise ValidationError({"http_method": "Unsupported HTTP method."})
        self.http_method = method
        if self.response_status is not None and not (100 <= self.response_status <= 599):
            raise ValidationError({"response_status": "HTTP response status must be between 100 and 599."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "api_execution_logs"
        indexes = [
            models.Index(fields=["screening_session", "-created_at"], name="idx_api_logs_screening"),
            models.Index(fields=["api", "-created_at"], name="idx_api_logs_api_created"),
            models.Index(fields=["execution_status", "-created_at"], name="idx_api_logs_status_created"),
            models.Index(fields=["modality", "-created_at"], name="idx_api_logs_modality_created"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(processing_time_ms__gte=0) | Q(processing_time_ms__isnull=True), name="api_processing_time_gte_0"),
            models.CheckConstraint(condition=Q(request_size_bytes__gte=0) | Q(request_size_bytes__isnull=True), name="api_request_size_gte_0"),
            models.CheckConstraint(condition=Q(response_size_bytes__gte=0) | Q(response_size_bytes__isnull=True), name="api_response_size_gte_0"),
        ]


class ModalityResult(ValidatedModelMixin, models.Model):
    modality_result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screening_session = models.ForeignKey(
        PlatformScreeningSession,
        on_delete=models.CASCADE,
        related_name="modality_results",
        db_column="screening_session_id",
    )
    modality = models.CharField(max_length=20, choices=Modality.choices)
    face_result = models.OneToOneField(
        FacialAnalysisResult,
        on_delete=models.PROTECT,
        related_name="modality_result",
        db_column="face_result_id",
        blank=True,
        null=True,
    )
    voice_result = models.OneToOneField(
        VoiceAnalysisResult,
        on_delete=models.PROTECT,
        related_name="modality_result",
        db_column="voice_result_id",
        blank=True,
        null=True,
    )
    text_result = models.OneToOneField(
        TextAnalysisResult,
        on_delete=models.PROTECT,
        related_name="modality_result",
        db_column="text_result_id",
        blank=True,
        null=True,
    )
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    # Full model response and summary for this modality.
    result_payload = models.JSONField(blank=True, null=True)
    # Exact features used by fusion for this modality.
    fusion_feature_payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        selected = [self.face_result_id, self.voice_result_id, self.text_result_id]
        if sum(1 for item in selected if item) != 1:
            raise ValidationError("Exactly one result reference is required for a modality result.")
        _validate_json_container(self.result_payload, "result_payload", allowed=(dict,))
        _validate_json_container(self.fusion_feature_payload, "fusion_feature_payload", allowed=(dict,))
    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "modality_results"
        indexes = [
            models.Index(fields=["screening_session", "modality"], name="idx_modality_session_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["screening_session", "modality"],
                name="unique_modality_per_screening_session",
            ),
            models.CheckConstraint(condition=Q(confidence_score__gte=0, confidence_score__lte=1) | Q(confidence_score__isnull=True), name="modality_confidence_score_0_1"),
        ]


class AuditLog(ValidatedModelMixin, models.Model):
    audit_log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_column="user_id",
        blank=True,
        null=True,
    )
    action_name = models.CharField(max_length=255)
    entity_name = models.CharField(max_length=255)
    entity_id = models.UUIDField(blank=True, null=True)
    metadata_json = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if len(self.action_name.strip()) < 2:
            raise ValidationError({"action_name": "Action name is too short."})
        if len(self.entity_name.strip()) < 2:
            raise ValidationError({"entity_name": "Entity name is too short."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_name} - {self.entity_name}"


class SecurityEvent(ValidatedModelMixin, models.Model):
    security_event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="security_events",
        db_column="user_id",
        blank=True,
        null=True,
    )
    event_type = models.CharField(max_length=255)
    severity = models.CharField(max_length=50, choices=SeverityLevel.choices, default=SeverityLevel.LOW)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    metadata_json = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if len(self.event_type.strip()) < 2:
            raise ValidationError({"event_type": "Event type is too short."})

    class Meta:
        managed = MANAGED_BY_DJANGO
        db_table = "security_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["severity", "-created_at"], name="idx_security_severity_created"),
            models.Index(fields=["event_type", "-created_at"], name="idx_security_event_created"),
        ]

    def __str__(self):
        return f"{self.severity}: {self.event_type}"
