import requests

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect


@login_required
def chat_page_view(request):
    return render(request, "chat/chat.html")


@login_required
@require_POST
@csrf_protect
def chat_api_proxy_view(request):
    """
    Frontend sends user message here.
    Django sends it to your external chatbot API.
    This keeps your API key hidden from browser.
    """

    try:
        user_message = request.POST.get("message", "").strip()

        if not user_message:
            return JsonResponse({
                "ok": False,
                "error": "Message is required.",
            }, status=400)

        api_url = getattr(settings, "CHATBOT_API_URL", "")
        api_key = getattr(settings, "CHATBOT_API_KEY", "")

        if not api_url:
            return JsonResponse({
                "ok": False,
                "error": "CHATBOT_API_URL is missing in settings.",
            }, status=500)

        headers = {
            "Content-Type": "application/json",
        }

        if api_key:
            headers["X-API-Key"] = api_key

        payload = {
            "message": user_message,
            "user_id": str(request.user.id),
            "email": request.user.email,
        }

        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=60,
        )

        if response.status_code >= 400:
            return JsonResponse({
                "ok": False,
                "error": f"Chatbot API failed with status {response.status_code}",
                "detail": response.text[:500],
            }, status=502)

        data = response.json()

        # Adjust these keys according to your chatbot API response.
        bot_reply = (
            data.get("reply")
            or data.get("response")
            or data.get("answer")
            or data.get("message")
            or "I received your message, but the API did not return a reply."
        )

        return JsonResponse({
            "ok": True,
            "reply": bot_reply,
            "raw": data,
        })

    except requests.exceptions.Timeout:
        return JsonResponse({
            "ok": False,
            "error": "Chatbot API timeout. Please try again.",
        }, status=504)

    except requests.exceptions.RequestException as exc:
        return JsonResponse({
            "ok": False,
            "error": f"Chatbot API connection failed: {exc}",
        }, status=502)

    except Exception as exc:
        return JsonResponse({
            "ok": False,
            "error": f"Server error: {exc}",
        }, status=500)