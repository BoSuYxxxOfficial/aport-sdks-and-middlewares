import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.http import JsonResponse
from django.test import Client
from django.urls import path

from aporthq_sdk_python import AportError


def basic_view(request):
    return JsonResponse(
        {
            "agent": getattr(request, "aport_agent", None),
            "policy_result": getattr(request, "aport_policy_result", None),
        }
    )


def refund_view(request):
    return JsonResponse({"ok": True, "agent": request.aport_agent})


def urlpatterns_with(view):
    return [
        path("refund/", view),
        path("health/", lambda request: JsonResponse({"ok": True})),
    ]


@pytest.fixture(autouse=True)
def django_settings(settings):
    settings.SECRET_KEY = "test-secret"
    settings.ROOT_URLCONF = __name__
    settings.ALLOWED_HOSTS = ["testserver"]
    settings.MIDDLEWARE = []
    settings.APORT = {
        "API_KEY": "test-key",
        "FAIL_CLOSED": True,
        "SKIP_PATHS": ["/health"],
    }


@pytest.mark.urls(__name__)
class TestAgentPassportMiddleware:
    @patch("aporthq_middleware_django.middleware.create_client")
    def test_passport_lookup_success(self, mock_create_client, settings):
        from aporthq_middleware_django import AgentPassportMiddleware

        mock_client = Mock()
        mock_client.get_passport_view = AsyncMock(
            return_value={"agent_id": "ap_test", "status": "active"}
        )
        mock_create_client.return_value = mock_client
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        settings.ROOT_URLCONF = __name__
        globals()["urlpatterns"] = urlpatterns_with(basic_view)

        response = Client().get("/refund/", HTTP_X_AGENT_PASSPORT_ID="ap_test")

        assert response.status_code == 200
        assert response.json()["agent"]["agent_id"] == "ap_test"

    def test_missing_agent_id_returns_401(self, settings):
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)

        response = Client().get("/refund/")

        assert response.status_code == 401
        assert response.json()["error"] == "missing_agent_id"

    def test_skip_paths_bypass_verification(self, settings):
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)

        response = Client().get("/health/")

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @patch("aporthq_middleware_django.middleware.create_client")
    def test_global_policy_allows_request(self, mock_create_client, settings):
        settings.APORT["POLICY_ID"] = "finance.payment.refund.v1"
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)
        mock_client = Mock()
        mock_client.verify_policy = AsyncMock(
            return_value={"decision_id": "dec_1", "allow": True, "reasons": []}
        )
        mock_create_client.return_value = mock_client

        response = Client().post(
            "/refund/",
            data=json.dumps({"amount": 100}),
            content_type="application/json",
            HTTP_X_AGENT_ID="ap_test",
        )

        assert response.status_code == 200
        assert response.json()["agent"]["agent_id"] == "ap_test"
        assert response.json()["policy_result"]["allow"] is True

    @patch("aporthq_middleware_django.middleware.create_client")
    def test_global_policy_denies_request(self, mock_create_client, settings):
        settings.APORT["POLICY_ID"] = "finance.payment.refund.v1"
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)
        mock_client = Mock()
        mock_client.verify_policy = AsyncMock(
            return_value={
                "decision_id": "dec_2",
                "allow": False,
                "reasons": [{"code": "DENIED"}],
            }
        )
        mock_create_client.return_value = mock_client

        response = Client().post(
            "/refund/",
            data=json.dumps({"amount": 100}),
            content_type="application/json",
            HTTP_X_AGENT_ID="ap_test",
        )

        assert response.status_code == 403
        assert response.json()["error"] == "policy_violation"
        assert response.json()["decision_id"] == "dec_2"

    @patch("aporthq_middleware_django.middleware.create_client")
    def test_global_policy_with_passport_in_body(self, mock_create_client, settings):
        settings.APORT["POLICY_ID"] = "finance.payment.refund.v1"
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)
        mock_client = Mock()
        mock_client.verify_policy_with_passport = AsyncMock(
            return_value={"decision_id": "dec_passport", "allow": True, "reasons": []}
        )
        mock_create_client.return_value = mock_client

        response = Client().post(
            "/refund/",
            data=json.dumps(
                {
                    "passport": {"agent_id": "ap_body", "status": "active"},
                    "amount": 100,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["agent"]["agent_id"] == "ap_body"
        mock_client.verify_policy_with_passport.assert_called_once()

    @patch("aporthq_middleware_django.middleware.create_client")
    def test_passport_in_body_without_policy_uses_local_passport(
        self, mock_create_client, settings
    ):
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)
        mock_client = Mock()
        mock_client.get_passport_view = AsyncMock()
        mock_create_client.return_value = mock_client

        response = Client().post(
            "/refund/",
            data=json.dumps(
                {
                    "passport": {"agent_id": "ap_body", "status": "active"},
                    "amount": 100,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["agent"]["agent_id"] == "ap_body"
        assert response.json()["agent"]["status"] == "active"
        mock_client.get_passport_view.assert_not_called()

    @patch("aporthq_middleware_django.middleware.create_client")
    def test_global_policy_with_policy_in_body(self, mock_create_client, settings):
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)
        mock_client = Mock()
        mock_client.verify_policy_with_policy_in_body = AsyncMock(
            return_value={"decision_id": "dec_body_policy", "allow": True, "reasons": []}
        )
        mock_create_client.return_value = mock_client

        response = Client().post(
            "/refund/",
            data=json.dumps(
                {
                    "passport": {"agent_id": "ap_body", "status": "active"},
                    "policy": {
                        "id": "custom.policy.v1",
                        "requires_capabilities": ["refund"],
                    },
                    "amount": 100,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["policy_result"]["decision_id"] == "dec_body_policy"
        mock_client.verify_policy_with_policy_in_body.assert_called_once()

    @patch("aporthq_middleware_django.middleware.create_client")
    def test_api_error_returns_sdk_status(self, mock_create_client, settings):
        settings.MIDDLEWARE = [
            "aporthq_middleware_django.AgentPassportMiddleware",
        ]
        globals()["urlpatterns"] = urlpatterns_with(basic_view)
        mock_client = Mock()
        mock_client.get_passport_view = AsyncMock(
            side_effect=AportError(
                status=503,
                reasons=[{"code": "UPSTREAM"}],
                raw_response="unavailable",
            )
        )
        mock_create_client.return_value = mock_client

        response = Client().get("/refund/", HTTP_X_AGENT_ID="ap_test")

        assert response.status_code == 503
        assert response.json()["error"] == "api_error"


class TestRequirePolicy:
    @patch("aporthq_middleware_django.middleware.create_client")
    def test_require_policy_decorator_allows_request(self, mock_create_client, settings):
        from aporthq_middleware_django import require_policy

        protected_view = require_policy("finance.payment.refund.v1")(refund_view)
        globals()["urlpatterns"] = urlpatterns_with(protected_view)
        mock_client = Mock()
        mock_client.verify_policy = AsyncMock(
            return_value={"decision_id": "dec_3", "allow": True, "reasons": []}
        )
        mock_create_client.return_value = mock_client

        response = Client().post(
            "/refund/",
            data=json.dumps({"amount": 100}),
            content_type="application/json",
            HTTP_X_AGENT_ID="ap_test",
        )

        assert response.status_code == 200
        assert response.json()["agent"]["agent_id"] == "ap_test"

    def test_require_policy_decorator_requires_agent_id(self):
        from aporthq_middleware_django import require_policy

        protected_view = require_policy("finance.payment.refund.v1")(refund_view)
        globals()["urlpatterns"] = urlpatterns_with(protected_view)

        response = Client().post("/refund/", data={})

        assert response.status_code == 401
        assert response.json()["error"] == "missing_agent_id"
