"""Which commit is this process serving, and when did it go live?

Feeds the small release marker in the sidebar (templates/base.html).

The answer comes from RELEASE_STAMP_FILE, which deploy\\auto_pull.ps1 writes after every
successful pull - that is the only place the *deploy* time is known. Where no stamp
exists yet (a dev machine, or the VM before its first stamped deploy) it falls back to
asking git for the checked-out commit, which gives the commit but no deploy time.
Either source failing just means no marker is shown; it must never break a page.
"""

import json
import re
import subprocess
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from django.conf import settings

_SHA_RE = re.compile(r"[0-9a-f]{40}")


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


def _git_dir():
    """The .git directory, following the `gitdir:` pointer a worktree leaves behind."""
    path = Path(settings.BASE_DIR) / ".git"
    if path.is_file():
        try:
            pointer = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not pointer.startswith("gitdir:"):
            return None
        path = Path(pointer[len("gitdir:"):].strip())
    return path if path.is_dir() else None


def _from_git_dir():
    """The checked-out SHA read straight out of .git, with no git binary involved.

    This is the only fallback that can work in production: the IIS application pool
    identity has no Git (docs/AUTO_DEPLOY.md), so _from_git() always fails there and a
    missing stamp used to leave the marker blank. Reading the ref files needs nothing but
    read access to the checkout, which the worker already has to serve the code.

    Gives the commit and nothing else -- the times live inside the commit object, which
    is zlib-compressed and usually inside a packfile. Not worth it for a marker.
    """
    git_dir = _git_dir()
    if git_dir is None:
        return None

    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not head.startswith("ref:"):
        # Detached HEAD: the file holds the SHA itself.
        return {"sha": head} if _SHA_RE.fullmatch(head) else None

    ref = head[len("ref:"):].strip()
    try:
        loose = (git_dir / ref).read_text(encoding="utf-8").strip()
        if _SHA_RE.fullmatch(loose):
            return {"sha": loose}
    except OSError:
        pass

    # Nothing loose, so the ref has been packed into .git/packed-refs.
    try:
        lines = (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith(("#", "^")):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip() == ref and _SHA_RE.fullmatch(parts[0]):
            return {"sha": parts[0]}
    return None


# Cached for the life of the process: every deploy restarts the app (auto_pull.ps1
# writes the stamp *before* recycling it), so a fresh process always reads a fresh stamp.
@lru_cache(maxsize=1)
def get_release():
    data = _from_stamp() or _from_git() or _from_git_dir()
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
