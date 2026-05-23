from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch


class OnboardingRequiredMiddleware:
    """
    Force authenticated users to complete onboarding before accessing app pages.

    Required order:
        1. Consent
        2. Complete profile
        3. Wellness check / dashboard / activities
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _safe_reverse(self, name, fallback):
        try:
            return reverse(name)
        except NoReverseMatch:
            return fallback

    def __call__(self, request):
        user = request.user

        if not user.is_authenticated:
            return self.get_response(request)

        path = request.path

        # Allow these paths always
        allowed_prefixes = [
            "/admin/",
            "/static/",
            "/media/",
            "/favicon.ico",

            # auth / allauth routes
            "/accounts/logout/",
            "/accounts/google/",
            "/accounts/social/",
            "/accounts/password/",
            "/accounts/confirm-email/",
            "/accounts/email/",
            "/accounts/verify-success/",
            "/accounts/forgot-password/",

            # current onboarding pages
            "/accounts/consent/",
            "/accounts/complete-profile/",
        ]

        for prefix in allowed_prefixes:
            if path.startswith(prefix):
                return self.get_response(request)

        # Superuser/admin can skip onboarding
        if user.is_superuser or user.is_staff:
            return self.get_response(request)

        # Get profile safely
        profile = getattr(user, "profile", None)

        if profile is None:
            return redirect(self._safe_reverse("complete_profile", "/accounts/complete-profile/"))

        # Step 1: consent required
        if not getattr(profile, "consented", False):
            return redirect(self._safe_reverse("consent", "/accounts/consent/"))

        # Step 2: profile completion required
        if not getattr(profile, "profile_completed", False):
            return redirect(self._safe_reverse("complete_profile", "/accounts/complete-profile/"))

        return self.get_response(request)