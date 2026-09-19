"""GitHub webhook endpoint that signals the deploy scripts to pull.

Deliberately minimal: this view runs as the IIS application pool identity, so it must
never shell out, never touch git, and never run migrations. All it does is verify
GitHub's HMAC signature and write a marker file that ``auto_pull.ps1`` -- running under
a Scheduled Task with real credentials -- consumes on its next tick.

That split is the whole point. The privileged work stays in the scheduled task; the
publicly reachable endpoint only ever writes a few bytes to a file.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

# GitHub push payloads are small; anything larger is not one of ours. Read the body
# through this cap so a bogus multi-megabyte POST cannot be used to chew up memory.
MAX_PAYLOAD_BYTES = 1024 * 1024


def _signature_is_valid(secret: str, body: bytes, header: str) -> bool:
    """Constant-time check of GitHub's X-Hub-Signature-256 header."""
    if not header or not header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, header)


@csrf_exempt
@require_http_methods(["GET", "HEAD", "POST"])
def github_webhook(request):
    """Verify a GitHub push webhook and drop a trigger file for auto_pull.ps1.

    A GET answers with a plain readiness line so you can confirm from a browser that
    the route is wired up and reachable, without sending a signed payload. It exposes
    no repository state.
    """
    if request.method in ("GET", "HEAD"):
        return HttpResponse("deploy hook: ready", content_type="text/plain")

    secret = getattr(settings, "DEPLOY_WEBHOOK_SECRET", "")
    if not secret:
        # Fail closed: without a secret there is no way to tell a real GitHub
        # delivery from anyone who guessed the URL.
        logger.error("Deploy webhook hit but DEPLOY_WEBHOOK_SECRET is not configured")
        return JsonResponse({"detail": "Deploy webhook is not configured."}, status=503)

    if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_PAYLOAD_BYTES:
        return HttpResponseBadRequest("Payload too large.")

    body = request.body
    if len(body) > MAX_PAYLOAD_BYTES:
        return HttpResponseBadRequest("Payload too large.")

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _signature_is_valid(secret, body, signature):
        logger.warning(
            "Deploy webhook rejected: bad signature (from %s)",
            request.META.get("REMOTE_ADDR", "unknown"),
        )
        # 404, not 403: an unauthenticated caller learns nothing about the endpoint.
        return JsonResponse({"detail": "Not found."}, status=404)

    event = request.headers.get("X-GitHub-Event", "")

    if event == "ping":
        # GitHub sends this once when the hook is created - answering it is what makes
        # the green tick appear in the repo's webhook settings.
        return JsonResponse({"detail": "pong"})

    if event != "push":
        return JsonResponse({"detail": f"Ignoring '{event}' event."})

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("Malformed JSON payload.")

    branch = getattr(settings, "DEPLOY_WEBHOOK_BRANCH", "main")
    ref = payload.get("ref", "")
    if ref != f"refs/heads/{branch}":
        return JsonResponse({"detail": f"Ignoring push to '{ref}'."})

    if payload.get("deleted"):
        return JsonResponse({"detail": "Ignoring branch deletion."})

    trigger_path = getattr(settings, "DEPLOY_TRIGGER_FILE", "")
    if not trigger_path:
        logger.error("Deploy webhook verified but DEPLOY_TRIGGER_FILE is not configured")
        return JsonResponse({"detail": "Deploy webhook is not configured."}, status=503)

    head = (payload.get("after") or "")[:12]
    pusher = (payload.get("pusher") or {}).get("name", "unknown")
    detail = (
        f"push to {branch} by {pusher} -> {head} "
        f"at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    try:
        os.makedirs(os.path.dirname(trigger_path), exist_ok=True)
        with open(trigger_path, "w", encoding="utf-8") as handle:
            handle.write(detail)
    except OSError:
        # The app pool identity may not have write access to logs\. The scheduled
        # poll still catches the commits, so report the failure without 500ing at
        # GitHub (which would mark the delivery failed and retry).
        logger.exception("Could not write deploy trigger file at %s", trigger_path)
        return JsonResponse(
            {"detail": "Trigger file could not be written; the scheduled poll will still pick this up."},
            status=202,
        )

    logger.info("Deploy trigger written: %s", detail)
    return JsonResponse({"detail": "Trigger accepted.", "head": head})
