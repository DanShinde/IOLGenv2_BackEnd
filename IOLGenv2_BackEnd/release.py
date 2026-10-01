"""Which commit is this process serving, and when did it go live?

Feeds the small release marker in the sidebar (templates/base.html).

The answer comes from RELEASE_STAMP_FILE, which deploy\\auto_pull.ps1 writes after every
successful pull - that is the only place the *deploy* time is known. Where no stamp
exists yet (a dev machine, or the VM before its first stamped deploy) it falls back to
asking git for the checked-out commit, which gives the commit but no deploy time.
Either source failing just means no marker is shown; it must never break a page.
"""

import json
import subprocess
from datetime import datetime
from functools import lru_cache

from django.conf import settings


def _parse(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _from_stamp():
    try:
        # utf-8-sig: tolerate a BOM in case the stamp is ever rewritten by hand in PowerShell.
        with open(settings.RELEASE_STAMP_FILE, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None

    if not isinstance(data, dict) or not data.get("sha"):
        return None
    return data


def _from_git():
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H%n%cI%n%s"],
            cwd=settings.BASE_DIR,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) < 2:
        return None

    return {
        "sha": lines[0],
        "committed_at": lines[1],
        "subject": lines[2] if len(lines) > 2 else "",
    }


# Cached for the life of the process: every deploy restarts the app (auto_pull.ps1
# writes the stamp *before* recycling it), so a fresh process always reads a fresh stamp.
@lru_cache(maxsize=1)
def get_release():
    data = _from_stamp() or _from_git()
    if not data:
        return None

    sha = str(data["sha"])
    return {
        "sha": sha,
        "short_sha": sha[:7],
        "subject": data.get("subject", ""),
        "committed_at": _parse(data.get("committed_at")),
        "deployed_at": _parse(data.get("deployed_at")),
    }


def release(request):
    """Context processor: exposes ``release`` (or None) to every template."""
    return {"release": get_release()}
