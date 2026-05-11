from django.http import JsonResponse
from django.urls import path

from aporthq_middleware_django import require_policy


def health(request):
    return JsonResponse({"ok": True})


def refund(request):
    return JsonResponse(
        {
            "ok": True,
            "agent": getattr(request, "aport_agent", None),
            "policy_result": getattr(request, "aport_policy_result", None),
        }
    )


@require_policy("data.export.create.v1")
def export_data(request):
    return JsonResponse({"ok": True, "agent": request.aport_agent})


urlpatterns = [
    path("health", health),
    path("refund", refund),
    path("export", export_data),
]

