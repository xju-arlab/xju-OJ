import hmac
import os
from pathlib import Path

from .contracts import require


def authenticate_worker(request):
    path = os.environ.get("AI_WORKER_TOKEN_FILE", "")
    try:
        expected = Path(path).read_text().strip() if path else ""
    except OSError:
        expected = ""
    supplied = request.META.get("HTTP_AUTHORIZATION", "")
    require(len(expected) >= 32 and hmac.compare_digest(supplied, "Bearer " + expected), "Invalid worker token")
