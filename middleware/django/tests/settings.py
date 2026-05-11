SECRET_KEY = "test-secret"
ROOT_URLCONF = "tests.test_middleware"
ALLOWED_HOSTS = ["testserver"]
MIDDLEWARE = []
INSTALLED_APPS = []
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

APORT = {
    "API_KEY": "test-key",
    "FAIL_CLOSED": True,
    "SKIP_PATHS": ["/health"],
}
