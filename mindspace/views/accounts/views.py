"""
Accounts views for the current MindSpace single-app structure.

Updated with strong backend input validation:
- Protects all end-user fields from bad format and unsafe script/html payloads.
- Keeps existing email verification, consent, profile completion, redirects, and audit flow.
- Models live in mindspace/models.py.
"""

import re
from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, password_validation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from mindspace.models import AuditLog, PendingSignup, UserProfile

User = get_user_model()


# ======================================================
# SMALL HELPERS
# ======================================================

def safe_redirect(*route_names, fallback="/"):
    """
    Try multiple route names and return the first valid redirect.
    Useful while your urls.py is still changing.
    """
    for route_name in route_names:
        try:
            reverse(route_name)
            return redirect(route_name)
        except NoReverseMatch:
            continue

    return redirect(fallback)


def get_or_create_profile(user):
    """
    Your new models.py has UserProfile related_name='profile'.
    This helper prevents 'user has no profile' errors.
    """
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": "user",
            "account_status": "active",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "is_email_verified": False,
            "avatar": "avatar_1.png",
        },
    )
    return profile


def is_profile_complete(profile):
    """
    New models.py field name: profile_completed.
    Old code used: is_profile_completed.
    """
    return bool(getattr(profile, "profile_completed", False))


def mark_profile_complete(profile):
    profile.profile_completed = True
    profile.full_clean()
    profile.save(update_fields=["profile_completed", "updated_at"])


def role_redirect(user):
    """
    Redirect user according to saved role in UserProfile.
    Normal users go to wellness check-in after onboarding.
    """

    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": "user",
            "account_status": "active",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "avatar": "avatar_1.png",
            "is_email_verified": False,
        }
    )

    if not profile.avatar:
        profile.avatar = "avatar_1.png"
        profile.full_clean()
        profile.save(update_fields=["avatar"])

    if profile.role == "admin" or user.is_superuser:
        return redirect("/admin/")

    if profile.role == "counselor":
        return redirect("counselor_support")

    return safe_redirect("check_in", fallback="/assessments/check-in/")


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ======================================================
# INPUT VALIDATION HELPERS
# ======================================================

DANGEROUS_INPUT_PATTERNS = [
    r"<\s*script",
    r"<\s*/\s*script\s*>",
    r"javascript\s*:",
    r"data\s*:",
    r"vbscript\s*:",
    r"onerror\s*=",
    r"onclick\s*=",
    r"onload\s*=",
    r"onmouseover\s*=",
    r"<\s*iframe",
    r"<\s*object",
    r"<\s*embed",
    r"<\s*link",
    r"<\s*meta",
    r"\{\{.*\}\}",
    r"\{%.*%\}",
]

ALLOWED_ROLES = ["user", "counselor"]

ALLOWED_GENDERS = [
    "male",
    "female",
    "other",
    "prefer_not_to_say",
]

ALLOWED_AVATARS = [
    "avatar_1.png",
    "avatar_2.png",
    "avatar_3.png",
    "avatar_4.png",
    "avatar_5.png",
    "avatar_6.png",
    "avatar_7.png",
    "avatar_8.png",
]


def add_form_error(errors, field, message):
    errors.setdefault(field, []).append(message)


def normalize_spaces(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def has_unsafe_input(value):
    """
    Detect common XSS/script/template injection payloads.
    This does not replace Django autoescaping, but blocks bad data before DB save.
    """
    if value is None:
        return False

    value = str(value)
    lowered = value.lower()

    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in DANGEROUS_INPUT_PATTERNS)


def validate_safe_value(value, field_label, errors, field_name):
    if has_unsafe_input(value):
        add_form_error(errors, field_name, f"{field_label} contains unsafe text or script-like content.")


def validate_required(value, field_label, errors, field_name):
    if not str(value or "").strip():
        add_form_error(errors, field_name, f"{field_label} is required.")
        return False
    return True


def validate_person_name(value, field_label, errors, field_name, required=True):
    value = normalize_spaces(value)

    if required and not validate_required(value, field_label, errors, field_name):
        return value

    if not value:
        return value

    validate_safe_value(value, field_label, errors, field_name)

    if len(value) < 2:
        add_form_error(errors, field_name, f"{field_label} must be at least 2 characters.")

    if len(value) > 100:
        add_form_error(errors, field_name, f"{field_label} cannot be more than 100 characters.")

    # Allows Indian/English-style names with spaces, apostrophe, dot, and hyphen.
    if not re.fullmatch(r"[A-Za-z][A-Za-z\s.'-]*", value):
        add_form_error(errors, field_name, f"{field_label} can contain only letters, spaces, dot, apostrophe, or hyphen.")

    return value.title()


def validate_full_name(value, errors):
    value = normalize_spaces(value)

    if not validate_required(value, "Name", errors, "name"):
        return value

    validate_safe_value(value, "Name", errors, "name")

    if len(value) < 2:
        add_form_error(errors, "name", "Name must be at least 2 characters.")

    if len(value) > 150:
        add_form_error(errors, "name", "Name cannot be more than 150 characters.")

    if not re.fullmatch(r"[A-Za-z][A-Za-z\s.'-]*", value):
        add_form_error(errors, "name", "Name can contain only letters, spaces, dot, apostrophe, or hyphen.")

    return value.title()


def validate_email_address(value, errors, field_name="email", required=True):
    value = str(value or "").strip().lower()

    if required and not validate_required(value, "Email", errors, field_name):
        return value

    if not value:
        return value

    validate_safe_value(value, "Email", errors, field_name)

    if len(value) > 254:
        add_form_error(errors, field_name, "Email address is too long.")
        return value

    try:
        validate_email(value)
    except ValidationError:
        add_form_error(errors, field_name, "Enter a valid email address.")

    return value


def validate_role(value, errors):
    value = str(value or "user").strip().lower()

    if has_unsafe_input(value):
        add_form_error(errors, "role", "Invalid role selected.")

    if value not in ALLOWED_ROLES:
        add_form_error(errors, "role", "Select a valid account role.")
        return "user"

    return value


def validate_password_input(password, confirm_password, errors, user=None):
    if not password:
        add_form_error(errors, "password", "Password is required.")

    if not confirm_password:
        add_form_error(errors, "confirm_password", "Confirm password is required.")

    if not password or not confirm_password:
        return

    if password != confirm_password:
        add_form_error(errors, "confirm_password", "Passwords do not match.")

    if has_unsafe_input(password):
        add_form_error(errors, "password", "Password contains unsafe script-like content.")

    try:
        password_validation.validate_password(password, user=user)
    except ValidationError as exc:
        for msg in exc.messages:
            add_form_error(errors, "password", msg)


def validate_indian_mobile(value, errors):
    value = str(value or "").strip().replace(" ", "").replace("-", "")

    if not validate_required(value, "Mobile number", errors, "mobile_number"):
        return value

    validate_safe_value(value, "Mobile number", errors, "mobile_number")

    # Accepts 9876543210, +919876543210, 919876543210.
    if not re.fullmatch(r"(?:\+91|91)?[6-9]\d{9}", value):
        add_form_error(errors, "mobile_number", "Enter a valid Indian mobile number, e.g. 9876543210 or +919876543210.")

    return value


def validate_gender(value, errors):
    value = str(value or "").strip().lower()

    if not validate_required(value, "Gender", errors, "gender"):
        return value

    validate_safe_value(value, "Gender", errors, "gender")

    if value not in ALLOWED_GENDERS:
        add_form_error(errors, "gender", "Select a valid gender option.")

    return value


def validate_date_of_birth_input(value, errors):
    raw_value = str(value or "").strip()

    if not validate_required(raw_value, "Date of birth", errors, "date_of_birth"):
        return None

    validate_safe_value(raw_value, "Date of birth", errors, "date_of_birth")

    dob = parse_date(raw_value)

    if dob is None:
        add_form_error(errors, "date_of_birth", "Enter date of birth in YYYY-MM-DD format.")
        return None

    today = timezone.localdate()

    if dob > today:
        add_form_error(errors, "date_of_birth", "Date of birth cannot be in the future.")
        return dob

    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    if age < 5:
        add_form_error(errors, "date_of_birth", "User must be at least 5 years old.")

    if age > 120:
        add_form_error(errors, "date_of_birth", "Enter a realistic date of birth.")

    return dob


def validate_location(value, field_label, errors, field_name):
    value = normalize_spaces(value)

    if not validate_required(value, field_label, errors, field_name):
        return value

    validate_safe_value(value, field_label, errors, field_name)

    if len(value) < 2:
        add_form_error(errors, field_name, f"{field_label} must be at least 2 characters.")

    if len(value) > 100:
        add_form_error(errors, field_name, f"{field_label} cannot be more than 100 characters.")

    # Allows names like Madhya Pradesh, Dadra & Nagar Haveli.
    if not re.fullmatch(r"[A-Za-z][A-Za-z\s.'\-&]*", value):
        add_form_error(errors, field_name, f"{field_label} can contain only letters, spaces, dot, apostrophe, hyphen, or &.")

    return value.title()


def validate_address(value, errors):
    value = normalize_spaces(value)

    if not validate_required(value, "Address", errors, "address"):
        return value

    validate_safe_value(value, "Address", errors, "address")

    if len(value) < 10:
        add_form_error(errors, "address", "Address must be at least 10 characters.")

    if len(value) > 500:
        add_form_error(errors, "address", "Address cannot be more than 500 characters.")

    # Allows readable address characters only.
    if not re.fullmatch(r"[A-Za-z0-9\s,./#()'\-&]+", value):
        add_form_error(errors, "address", "Address contains invalid characters.")

    return value


def validate_avatar(value, errors):
    value = str(value or "avatar_1.png").strip()

    validate_safe_value(value, "Avatar", errors, "avatar")

    if value not in ALLOWED_AVATARS:
        add_form_error(errors, "avatar", "Invalid avatar selected.")
        return "avatar_1.png"

    return value


def flatten_errors(errors):
    return [message for field_errors in errors.values() for message in field_errors]


def show_form_errors(request, errors):
    for message in flatten_errors(errors):
        messages.error(request, message)


def build_signup_clean_data(request):
    errors = {}

    name = validate_full_name(request.POST.get("name", ""), errors)
    email = validate_email_address(request.POST.get("email", ""), errors)
    role = validate_role(request.POST.get("role", "user"), errors)

    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")
    validate_password_input(password, confirm_password, errors)

    terms = request.POST.get("terms")
    if not terms:
        add_form_error(errors, "terms", "Please accept terms and policy.")

    return {
        "name": name,
        "email": email,
        "role": role,
        "password": password,
        "terms": terms,
    }, errors


def build_profile_clean_data(request):
    errors = {}

    first_name = validate_person_name(
        request.POST.get("first_name", ""),
        "First name",
        errors,
        "first_name",
        required=True,
    )

    last_name = validate_person_name(
        request.POST.get("last_name", ""),
        "Last name",
        errors,
        "last_name",
        required=False,
    )

    mobile_number = validate_indian_mobile(request.POST.get("mobile_number", ""), errors)
    address = validate_address(request.POST.get("address", ""), errors)
    state = validate_location(request.POST.get("state", ""), "State", errors, "state")
    district = validate_location(request.POST.get("district", ""), "District", errors, "district")
    gender = validate_gender(request.POST.get("gender", ""), errors)
    date_of_birth = validate_date_of_birth_input(request.POST.get("date_of_birth", ""), errors)
    avatar = validate_avatar(request.POST.get("avatar", "avatar_1.png"), errors)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "mobile_number": mobile_number,
        "address": address,
        "state": state,
        "district": district,
        "gender": gender,
        "date_of_birth": date_of_birth,
        "avatar": avatar,
    }, errors


# ======================================================
# EMAIL VERIFICATION HELPERS
# ======================================================

def cleanup_expired_pending_signups():
    PendingSignup.objects.filter(expires_at__lt=timezone.now()).delete()


def send_signup_verification_email(request, pending_signup):
    """
    Send signup verification email with a clean HTML button.

    The email contains:
    - HTML button for normal users
    - Plain-text fallback for email clients that block HTML
    - Raw fallback URL below the button
    """
    verify_path = reverse("verify_email", kwargs={"token": str(pending_signup.token)})

    site_base_url = getattr(settings, "SITE_BASE_URL", "").strip().rstrip("/")

    if site_base_url:
        verification_url = urljoin(site_base_url + "/", verify_path.lstrip("/"))
    else:
        verification_url = request.build_absolute_uri(verify_path)

    subject = "Verify your MindSpace account"

    text_message = (
        f"Hi {pending_signup.name},\n\n"
        "Thanks for signing up for MindSpace.\n\n"
        "Please verify your email address by opening this link:\n"
        "This link will expire in 5 minutes.\n\n"
        "If you did not create this account, you can ignore this email."
    )

    html_message = render_to_string(
        "accounts/email/verify_email.html",
        {
            "name": pending_signup.name,
            "verification_url": verification_url,
            "expires_in": "5 minutes",
        },
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[pending_signup.email],
    )
    email.attach_alternative(html_message, "text/html")
    email.send(fail_silently=False)


# ======================================================
# SIGNUP
# ======================================================

def signup_view(request):
    """
    Signup flow:
    - Validate all end-user input before touching database
    - Store signup data temporarily in PendingSignup
    - Send verification email
    - Create real User only after email verification
    - Pending signup expires after 5 minutes
    """

    cleanup_expired_pending_signups()

    if request.method == "POST":
        clean_data, errors = build_signup_clean_data(request)

        name = clean_data["name"]
        email = clean_data["email"]
        role = clean_data["role"]
        password = clean_data["password"]

        if errors:
            show_form_errors(request, errors)
            return safe_redirect("signup", fallback="/accounts/signup/")

        if User.objects.filter(email=email).exists() or User.objects.filter(username=email).exists():
            messages.error(request, "This email is already registered. Please login.")
            return safe_redirect("login", fallback="/accounts/login/")

        # Remove old pending request for same email.
        PendingSignup.objects.filter(email=email).delete()

        try:
            pending_signup = PendingSignup(
                name=name,
                email=email,
                role=role,
                password_hash=make_password(password),
                terms_accepted=True,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            pending_signup.full_clean()
            pending_signup.save()

            send_signup_verification_email(request, pending_signup)

        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field_errors in exc.message_dict.values():
                    for msg in field_errors:
                        messages.error(request, msg)
            else:
                for msg in exc.messages:
                    messages.error(request, msg)
            return safe_redirect("signup", fallback="/accounts/signup/")

        except Exception as exc:
            messages.error(request, f"Could not send verification email: {exc}")
            return safe_redirect("signup", fallback="/accounts/signup/")

        messages.success(
            request,
            "Verification email sent. Please check your inbox, verify your email, then login."
        )
        return safe_redirect("login", fallback="/accounts/login/")

    return render(request, "accounts/signup.html")


def verify_email_view(request, token):
    """
    Verify email token:
    - If valid and not expired, create User and UserProfile
    - Delete pending signup
    - Login user
    - Redirect to consent
    """

    cleanup_expired_pending_signups()

    pending_signup = PendingSignup.objects.filter(token=token).first()

    if not pending_signup:
        messages.error(request, "Invalid or expired verification link. Please sign up again.")
        return safe_redirect("signup", fallback="/accounts/signup/")

    if pending_signup.is_expired:
        email = pending_signup.email
        pending_signup.delete()
        messages.error(
            request,
            f"Verification link expired for {email}. Please sign up again."
        )
        return safe_redirect("signup", fallback="/accounts/signup/")

    if User.objects.filter(email=pending_signup.email).exists() or User.objects.filter(username=pending_signup.email).exists():
        pending_signup.delete()
        messages.info(request, "Account already exists. Please login.")
        return safe_redirect("login", fallback="/accounts/login/")

    first_name = pending_signup.name.split(" ", 1)[0]
    last_name = pending_signup.name.split(" ", 1)[1] if " " in pending_signup.name else ""

    try:
        with transaction.atomic():
            user = User(
                username=pending_signup.email,
                email=pending_signup.email,
                password=pending_signup.password_hash,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )
            user.full_clean()
            user.save()

            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": pending_signup.role,
                    "account_status": "pending" if pending_signup.role == "counselor" else "active",
                    "is_email_verified": True,
                    "first_name": first_name,
                    "last_name": last_name,
                    "avatar": "avatar_1.png",
                    "profile_completed": False,
                    "consented": False,
                },
            )
            profile.full_clean()
            profile.save()

            AuditLog.objects.create(
                user=user,
                action_name="email_verified_account_created",
                entity_name="UserProfile",
                metadata_json={
                    "role": pending_signup.role,
                    "email": pending_signup.email,
                    "ip_address": get_client_ip(request),
                },
            )

            pending_signup.delete()

    except (IntegrityError, ValidationError):
        messages.error(request, "Could not create account. Please try again.")
        return safe_redirect("signup", fallback="/accounts/signup/")

    if user.profile.account_status == "pending":
        messages.success(
            request,
            "Email verified. Counselor account is pending admin approval. You can login after approval."
        )
        return safe_redirect("verify_success", fallback="/accounts/verify-success/")

    messages.success(request, "Email verified successfully. You can now login.")
    return safe_redirect("verify_success", fallback="/accounts/verify-success/")


# ======================================================
# VERIFY EMAIL SIGNUP
# ======================================================

def verify_signup_view(request, token=None):
    if not token:
        messages.error(request, "Invalid verification link.")
        return safe_redirect("signup", fallback="/accounts/signup/")

    return verify_email_view(request, token)


def verify_success_view(request):
    return render(request, "accounts/verify-success.html")


# ======================================================
# LOGIN
# ======================================================

def login_view(request):
    if request.method == "POST":
        errors = {}

        email = validate_email_address(request.POST.get("email", ""), errors)
        password = request.POST.get("password", "")

        if not password:
            add_form_error(errors, "password", "Password is required.")

        if has_unsafe_input(password):
            add_form_error(errors, "password", "Password contains unsafe script-like content.")

        if errors:
            show_form_errors(request, errors)
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        pending_signup = PendingSignup.objects.filter(email=email).first()

        if pending_signup:
            if pending_signup.is_expired:
                pending_signup.delete()
                messages.error(request, "Your verification link expired. Please sign up again.")
                return safe_redirect("signup", fallback="/accounts/signup/")

            messages.error(
                request,
                "Please verify your email first. Check your inbox for the MindSpace verification link."
            )
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        user = authenticate(request, username=email, password=password)

        if user is None:
            messages.error(request, "Invalid email or password.")
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        profile = get_or_create_profile(user)

        if not profile.is_email_verified:
            messages.error(request, "Please verify your email before logging in.")
            return safe_redirect("login", fallback="/accounts/login/")

        if profile.account_status == "pending":
            messages.error(request, "Your account is pending admin approval.")
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        if profile.account_status == "suspended":
            messages.error(request, "Your account has been suspended.")
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        if profile.account_status == "deleted":
            messages.error(request, "This account has been deleted.")
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        if profile.account_status != "active":
            messages.error(request, "Your account is not active.")
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        login(request, user)

        if not profile.consented:
            return safe_redirect("consent", fallback="/accounts/consent/")

        if not is_profile_complete(profile):
            return safe_redirect("complete_profile", fallback="/accounts/complete-profile/")

        return role_redirect(user)

    return render(request, "accounts/login.html")


# ======================================================
# GOOGLE LOGIN/SIGNUP REDIRECT
# ======================================================

@login_required
def google_login_redirect_view(request):
    """
    After successful Google login/signup:
    - create UserProfile if missing
    - force unknown roles to user
    - continue flow: consent -> complete profile -> dashboard
    """
    user = request.user

    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": "user",
            "account_status": "active",
            "is_email_verified": True,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "profile_completed": False,
            "consented": False,
        },
    )

    changed_fields = []

    if profile.role not in ["user", "counselor", "admin", "researcher"]:
        profile.role = "user"
        changed_fields.append("role")

    if not profile.account_status:
        profile.account_status = "active"
        changed_fields.append("account_status")

    if not profile.first_name and user.first_name:
        profile.first_name = user.first_name
        changed_fields.append("first_name")

    if not profile.last_name and user.last_name:
        profile.last_name = user.last_name
        changed_fields.append("last_name")

    if not profile.is_email_verified:
        profile.is_email_verified = True
        changed_fields.append("is_email_verified")

    if changed_fields:
        changed_fields.append("updated_at")
        profile.full_clean()
        profile.save(update_fields=changed_fields)

    if profile.account_status == "pending":
        messages.error(request, "Your account is pending admin approval.")
        logout(request)
        return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

    if profile.account_status == "suspended":
        messages.error(request, "Your account has been suspended.")
        logout(request)
        return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

    if profile.account_status == "deleted":
        messages.error(request, "This account has been deleted.")
        logout(request)
        return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

    if profile.account_status != "active":
        messages.error(request, "Your account is not active.")
        logout(request)
        return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

    if not profile.consented:
        return safe_redirect("consent", fallback="/accounts/consent/")

    if not is_profile_complete(profile):
        return safe_redirect("complete_profile", fallback="/accounts/complete-profile/")

    return role_redirect(user)


# ======================================================
# COMPLETE PROFILE
# ======================================================

@login_required
def complete_profile_view(request):
    profile = get_or_create_profile(request.user)

    if not profile.consented:
        messages.info(request, "Please accept consent before completing your profile.")
        return safe_redirect("consent", fallback="/accounts/consent/")

    if is_profile_complete(profile):
        return role_redirect(request.user)

    if request.method == "POST":
        clean_data, errors = build_profile_clean_data(request)

        if errors:
            show_form_errors(request, errors)
            return render(
                request,
                "accounts/complete_profile.html",
                {
                    "profile": profile,
                    "avatars": ALLOWED_AVATARS,
                    "form_data": request.POST,
                    "form_errors": errors,
                },
            )

        profile.first_name = clean_data["first_name"]
        profile.last_name = clean_data["last_name"]
        profile.mobile_number = clean_data["mobile_number"]
        profile.address = clean_data["address"]
        profile.state = clean_data["state"]
        profile.district = clean_data["district"]
        profile.gender = clean_data["gender"]
        profile.date_of_birth = clean_data["date_of_birth"]
        profile.avatar = clean_data["avatar"]
        profile.profile_completed = True

        try:
            profile.full_clean()
            profile.save()

            request.user.first_name = profile.first_name
            request.user.last_name = profile.last_name or ""
            request.user.full_clean()
            request.user.save(update_fields=["first_name", "last_name"])

            AuditLog.objects.create(
                user=request.user,
                action_name="profile_completed",
                entity_name="UserProfile",
                metadata_json={"ip_address": get_client_ip(request)},
            )

        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field_errors in exc.message_dict.values():
                    for msg in field_errors:
                        messages.error(request, msg)
            else:
                for msg in exc.messages:
                    messages.error(request, msg)

            return render(
                request,
                "accounts/complete_profile.html",
                {
                    "profile": profile,
                    "avatars": ALLOWED_AVATARS,
                    "form_data": request.POST,
                },
            )

        return safe_redirect("check_in", fallback="/assessments/check-in/")

    return render(
        request,
        "accounts/complete_profile.html",
        {
            "profile": profile,
            "avatars": ALLOWED_AVATARS,
        },
    )


# ======================================================
# PROFILE PAGE
# ======================================================

@login_required
def profile_view(request):
    profile = get_or_create_profile(request.user)

    return render(
        request,
        "accounts/profile.html",
        {
            "profile": profile,
        },
    )


# ======================================================
# FORGOT PASSWORD
# ======================================================

def forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "")
        errors = {}
        validate_email_address(email, errors)

        if errors:
            show_form_errors(request, errors)
            return render(request, "accounts/forgot-password.html")

        form = PasswordResetForm(request.POST)

        if form.is_valid():
            form.save(
                request=request,
                from_email=settings.DEFAULT_FROM_EMAIL,
                email_template_name="accounts/password-reset-email.html",
                subject_template_name="accounts/password-reset-subject.txt",
            )

            messages.success(request, "Password reset link sent.")
            return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

        messages.error(request, "Please enter a valid email address.")

    return render(request, "accounts/forgot-password.html")


# ======================================================
# LOGOUT
# ======================================================

def logout_view(request):
    if request.method == "POST":
        logout(request)
        return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

    return safe_redirect("accounts:login", "login", fallback="/accounts/login/")


# ======================================================
# DELETE ACCOUNT
# ======================================================

@login_required
def delete_account_view(request):
    user = request.user

    if request.method == "POST":
        confirm = request.POST.get("confirm_delete", "").strip()

        if has_unsafe_input(confirm):
            messages.error(request, "Invalid confirmation text.")
            return safe_redirect(
                "accounts:delete_account",
                "delete_account",
                fallback="/accounts/delete-account/",
            )

        if confirm != "DELETE":
            messages.error(request, "Please type DELETE to confirm account deletion.")
            return safe_redirect(
                "accounts:delete_account",
                "delete_account",
                fallback="/accounts/delete-account/",
            )

        profile = get_or_create_profile(user)
        profile.account_status = "deleted"
        profile.deleted_at = timezone.now()
        profile.full_clean()
        profile.save(update_fields=["account_status", "deleted_at", "updated_at"])

        AuditLog.objects.create(
            user=user,
            action_name="account_deleted",
            entity_name="UserProfile",
            metadata_json={"ip_address": get_client_ip(request)},
        )

        logout(request)

        # Soft-delete profile status first, then deactivate user.
        user.is_active = False
        user.save(update_fields=["is_active"])

        messages.success(request, "Your account has been deleted.")
        return safe_redirect("accounts:login", "login", fallback="/accounts/login/")

    return render(request, "accounts/delete_account.html")
