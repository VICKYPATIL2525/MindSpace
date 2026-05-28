from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from mindspace.models import UserPredictionSummary
from mindspace.services.activity.recommendations import get_recommendation_for_label


@login_required
def activity_hub_view(request):
    summary = UserPredictionSummary.objects.filter(user=request.user).first()

    latest_label = "normal"
    latest_score = None

    if summary:
        latest_label = summary.latest_prediction_label or "normal"
        latest_score = summary.latest_confidence_score

    recommendation = get_recommendation_for_label(latest_label)

    return render(request, "activity/activity_hub.html", {
        "summary": summary,
        "latest_label": latest_label,
        "latest_score": latest_score,
        "recommendation": recommendation,
    })


@login_required
def breath_box_view(request):
    return render(request, "activity/breathing/breath_box.html")


@login_required
def breath_478_view(request):
    return render(request, "activity/breathing/breath_478.html")


@login_required
def breath_extended_exhale_view(request):
    return render(request, "activity/breathing/breath_extended_exhale.html")


@login_required
def breath_paced_recovery_view(request):
    return render(request, "activity/breathing/breath_paced_recovery.html")


@login_required
def breath_resonance_view(request):
    return render(request, "activity/breathing/breath_resonance.html")


@login_required
def breath_triangle_view(request):
    return render(request, "activity/breathing/breath_triangle.html")


@login_required
def activity_grounding_flow_view(request):
    return render(request, "activity/movement/grounding_flow.html")


@login_required
def activity_neck_release_view(request):
    return render(request, "activity/movement/neck_release.html")


@login_required
def activity_shoulder_unlock_view(request):
    return render(request, "activity/movement/shoulder_unlock.html")


@login_required
def activity_spine_wakeup_view(request):
    return render(request, "activity/movement/spine_wakeup.html")


@login_required
def activity_stillness_stretch_view(request):
    return render(request, "activity/movement/stillness_stretch.html")