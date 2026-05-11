import os

SECRET_KEY = "example-only"
DEBUG = True
ROOT_URLCONF = "simple_project.urls"
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = []

MIDDLEWARE = [
    "aporthq_middleware_django.AgentPassportMiddleware",
]

APORT = {
    "API_KEY": os.getenv("APORT_API_KEY"),
    "BASE_URL": os.getenv("APORT_BASE_URL", "https://api.aport.io"),
    "FAIL_CLOSED": True,
    "SKIP_PATHS": ["/health"],
    "POLICY_ID": "finance.payment.refund.v1",
}

