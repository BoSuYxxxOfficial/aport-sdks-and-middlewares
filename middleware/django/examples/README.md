# Django Middleware Example

Run the example project from this directory after installing the package:

```bash
python -m venv .venv
.venv/bin/python -m pip install ../../
APORT_API_KEY=your_api_key .venv/bin/python simple_project/manage.py runserver
```

Try the health endpoint:

```bash
curl http://localhost:8000/health
```

Try a protected endpoint:

```bash
curl -H "X-Agent-Passport-Id: ap_a2d10232c6534523812423eec8a1425c45678" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "currency": "USD"}' \
  http://localhost:8000/refund
```
