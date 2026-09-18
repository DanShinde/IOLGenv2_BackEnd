# Auto-pull: keeping the Windows VM in sync with `main`

How new commits on `origin/main` reach the IIS VM and refresh the running app.
The code this describes lives in [`deploy/`](../deploy/) at the repo root.

| File | What it is |
|---|---|
| [`auto_pull.ps1`](../deploy/auto_pull.ps1) | The worker. Fetch → compare → pull → pip/migrate/collectstatic → restart. Safe to run on every tick. |
| [`Register-AutoPullTask.ps1`](../deploy/Register-AutoPullTask.ps1) | One-time setup: registers the Windows Scheduled Task that runs the worker. |
| [`views.py`](../deploy/views.py) | The GitHub webhook endpoint at `/deploy-hook/`. Verifies the HMAC signature and writes a trigger file — nothing else. |
| [`urls.py`](../deploy/urls.py) | Wires that view up; included from [`IOLGenv2_BackEnd/urls.py`](../IOLGenv2_BackEnd/urls.py). |

The deployment is IIS + wfastcgi rooted at `C:\IOLGenv2_BackEnd` with its venv at
`C:\IOLGenv2_BackEnd\.venv` — those paths come straight out of
[`web.config`](../web.config). Both scripts default to them; pass `-RepoPath` if
your server differs.

> This is unrelated to [`.github/workflows/docker-image.yml`](../.github/workflows/docker-image.yml),
> which builds and pushes Docker images to Docker Hub. That workflow never touches this VM.

---

## How the two halves fit together

```text
GitHub push to main
      │
      ├──► POST /deploy-hook/  ──►  views.py: verify HMAC, write logs\deploy.trigger
      │                                   (app pool identity; no git, no shell)
      │
      └──► Scheduled Task (every minute)  ──►  auto_pull.ps1
                                                 git pull --ff-only
                                                 pip / migrate / collectstatic
                                                 recycle the app
                                            (real account; real credentials)
```

The webhook is the **signal**; the scheduled task is the **muscle**. They are split
because a view runs under the **IIS application pool identity**, which has no Git
credentials for the private remote, usually no write access to `C:\IOLGenv2_BackEnd`,
cannot `pip install` over `.pyd`/`.dll` files the running worker holds locked, and
cannot cleanly restart the process it is itself executing inside. Long deploy steps
would also blow past the FastCGI request timeout and be killed mid-migration.

So the view does the one safe thing — writes a few bytes to a file — and everything
privileged happens in the task.

**The task's poll is also the safety net.** If GitHub's delivery fails, or the trigger
file can't be written, the next tick compares SHAs and pulls anyway. The webhook only
removes waiting; it is never the sole path.

---

## Install (once, on the VM)

1. **Get this folder onto the server.** It ships in the repo, so once `main` is
   checked out at `C:\IOLGenv2_BackEnd` the scripts are already at
   `C:\IOLGenv2_BackEnd\deploy\`.

2. **Confirm `git pull` works by hand, as the account the task will use.** This is
   the step that catches credential problems early:

   ```powershell
   cd C:\IOLGenv2_BackEnd
   git status
   git pull --ff-only origin main
   ```

   If this prompts for a username or password, fix that first — see
   [Git credentials](#git-credentials) below. An unattended task cannot answer a prompt.

3. **Dry-run the worker** from an elevated prompt:

   ```powershell
   cd C:\IOLGenv2_BackEnd\deploy
   .\auto_pull.ps1 -Verbose
   ```

   Expect `Up to date at <sha>` when there is nothing new.

4. **Register the task** (elevated):

   ```powershell
   .\Register-AutoPullTask.ps1
   ```

   It prompts for the Windows password of the account it runs as. Options:

   ```powershell
   .\Register-AutoPullTask.ps1 -IntervalMinutes 1 -AppPoolName "YourPoolName"
   ```

   Use `-IntervalMinutes 1` if you are also setting up the GitHub webhook below;
   3–5 minutes is fine for polling alone.

   Pass `-AppPoolName` if you know the IIS pool serving this site — the script then
   recycles it properly. Without it, the script touches `web.config`, which makes IIS
   reload the app anyway and needs no pool name.

5. **Verify end to end:**

   ```powershell
   Start-ScheduledTask -TaskName 'IOLGen AutoPull'
   Get-Content C:\IOLGenv2_BackEnd\logs\auto_pull.log -Tail 20
   ```

To remove it: `.\Register-AutoPullTask.ps1 -Unregister`

---

## What a run actually does

1. Takes an exclusive lock (`logs\auto_pull.lock`) so a slow run is never overlapped
   by the next tick.
2. Consumes `logs\deploy.trigger` if the webhook left one, logging which push caused
   this run. Its absence changes nothing — the SHA comparison below is what decides.
3. Checks the checkout is on `main` and that **no tracked file is locally modified**.
   If either fails it logs loudly and exits `2` — it will never force-reset your VM.
4. `git fetch`, then compares `HEAD` with `origin/main`. Equal → logs one line and exits.
5. `git pull --ff-only`. A diverged history fails here rather than creating a merge.
6. Runs only what the diff needs:
   - `requirements.txt` changed → `pip install -r requirements.txt` into `.venv`
   - anything under a `migrations/` folder changed → `manage.py migrate --noinput`
   - anything under a `static/` folder changed → `manage.py collectstatic --noinput`
7. Recycles the app pool, or touches `web.config`.

Everything is appended to `logs\auto_pull.log`, which rotates at 5 MB. `logs/` is
gitignored, so the log never shows up as a pending change.

**Your server-local state is safe.** `.env`, `db.sqlite3`, `media/` and `staticfiles/`
are all gitignored, so a fast-forward pull cannot overwrite them.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Up to date, or updated successfully |
| 1 | Error — fetch/pull/migrate/pip failed, or the repo is misconfigured |
| 2 | Blocked — dirty working tree, wrong branch, or diverged history. Needs a human on the VM. |

### Useful flags

```powershell
.\auto_pull.ps1 -Force               # run every step even with no new commits
.\auto_pull.ps1 -SkipCollectStatic   # never run collectstatic
.\auto_pull.ps1 -Branch release      # track a branch other than main
```

---

## Git credentials

The remote is `https://github.com/DanShinde/IOLGenv2_BackEnd.git` over HTTPS, so the
task's account needs non-interactive credentials. Two workable setups:

**A. Credential Manager (what the repo is configured for).** `credential.helper` is
already `manager`. Log in as the task account once, run `git pull` interactively, and
let the manager store the credential. This is why `Register-AutoPullTask.ps1` registers
with a **stored password** rather than SYSTEM or S4U logon — Credential Manager secrets
are protected by the user's DPAPI key, which only unlocks under a password logon.

**B. A token file (no stored Windows password).** Create a fine-grained GitHub PAT with
read-only Contents access on this repo, then, as the task account:

```powershell
cd C:\IOLGenv2_BackEnd
git config credential.helper store
git config credential.https://github.com.username DanShinde
# next pull writes the token to %USERPROFILE%\.git-credentials
git pull origin main   # paste the PAT as the password
```

The token then sits in plaintext in that user's profile — lock the file down with
`icacls` and use a read-only PAT. With B you can register the task with a different
logon type if storing the Windows password is not acceptable in your environment.

A read-only **deploy key** over SSH is the cleanest option of all if the VM can reach
GitHub on port 22; it needs the remote switched to the `git@github.com:` form.

---

## Setting up the GitHub webhook

### 1. Generate a secret and put it in `.env` on the VM

```powershell
# any long random string; this one is fine
python -c "import secrets; print(secrets.token_hex(32))"
```

Add to `C:\IOLGenv2_BackEnd\.env`:

```ini
DEPLOY_WEBHOOK_SECRET=<the string you just generated>
# Optional - these are the defaults:
# DEPLOY_WEBHOOK_BRANCH=main
# DEPLOY_TRIGGER_FILE=C:\IOLGenv2_BackEnd\logs\deploy.trigger
```

`.env` is gitignored, so the secret stays on the server. **Until `DEPLOY_WEBHOOK_SECRET`
is set the endpoint is inert** — it returns 503 rather than trusting an unsigned caller.
Restart the app (or recycle the pool) after editing `.env`.

### 2. Let the app pool write the trigger file

The endpoint's only filesystem need is `logs\`:

```powershell
icacls C:\IOLGenv2_BackEnd\logs /grant "IIS AppPool\<YourPoolName>:(OI)(CI)M"
```

If you skip this the webhook still returns 202 and logs the failure — the scheduled
poll then picks the commits up on its own.

### 3. Check the route is reachable

```powershell
curl.exe http://115.245.5.130:8005/deploy-hook/
# deploy hook: ready
```

### 4. Add the hook in GitHub

Go to **Repo → Settings → Webhooks → Add webhook** and fill in:

| Field | Value |
|---|---|
| Payload URL | `http://115.245.5.130:8005/deploy-hook/` |
| Content type | `application/json` |
| Secret | the `DEPLOY_WEBHOOK_SECRET` value |
| SSL verification | n/a on plain HTTP |
| Events | **Just the push event** |
| Active | ✔ |

GitHub immediately sends a `ping`; the endpoint answers `pong`, which is what turns the
delivery green. Check **Recent Deliveries** on the hook to confirm.

> **On plain HTTP:** the payload and the signature header cross the internet in the
> clear. The HMAC still stops anyone from *forging* a deploy — the secret itself is
> never transmitted — but a network observer can read the payload and replay it. Since
> replaying only causes "pull the current main", the practical risk is low. Put the
> 8005 binding behind TLS when you can, and set `DEPLOY_WEBHOOK_SECRET` to something
> not used anywhere else.

### 5. Use a 1-minute task interval

With the webhook in place, register the task to tick every minute so the trigger is
acted on promptly:

```powershell
.\Register-AutoPullTask.ps1 -IntervalMinutes 1
```

**Be clear-eyed about the latency:** the task interval is the floor. A push is live
within about a minute — the webhook does not make it instant, because Task Scheduler
has no native "run when this file appears" trigger. What the webhook buys you is a
1-minute worst case instead of a 3-to-5-minute one, plus a log line naming the exact
push that caused each deploy. If sub-minute matters, the next step up is a small
always-running watcher service, which is a bigger commitment than this is worth.

### What the endpoint will and won't do

- Verifies `X-Hub-Signature-256` with `hmac.compare_digest`; anything unsigned or
  tampered gets a **404**, not a 403 — an unauthenticated caller learns nothing.
- Only acts on `push` to `refs/heads/main`. Other branches, tags, branch deletions
  and non-push events are acknowledged and ignored.
- Never runs git, pip, or a shell. Never imports GitPython. Writes one file.
- Caps the body at 1 MB.

Verified against: bad/missing/tampered signatures, ping, non-main pushes, branch
deletion, malformed JSON, wrong HTTP method, and unconfigured-secret — 13 cases.

---

## Troubleshooting

**Task runs but nothing happens.** Check `logs\auto_pull.log` first — the script logs
every decision, including "up to date". If the log is missing entirely, the task never
started the script: check Task Scheduler's History tab and the `Last Run Result`.

**`git.exe not found on PATH for this account`.** Git is installed per-user or its PATH
entry is not visible to the task account. Install Git system-wide, or add its `cmd`
folder to the machine PATH.

**Exit code 2, "Working tree has local modifications".** Someone edited a tracked file
directly on the server. Decide whether that change matters: commit and push it from the
VM, or discard it with `git checkout -- <file>`. The script intentionally will not
choose for you.

**Exit code 2, "git pull --ff-only failed".** The VM has commits that `origin/main`
does not, or `main` was force-pushed. Resolve by hand on the server.

**Code updated but the site still serves the old version.** The restart didn't take.
Pass `-AppPoolName` so the script recycles the pool explicitly, or run `iisreset`.

**Migrations ran but the app 500s.** Look at `logs\err.log` (the wfastcgi log) — the
pull succeeded, so this is an application error, not a deploy one.

**Webhook delivery shows 404 in GitHub.** The signature didn't verify. The secret in
the GitHub hook and `DEPLOY_WEBHOOK_SECRET` in `.env` differ, or the app wasn't
restarted after `.env` was edited. Confirm the route itself with a plain
`curl http://…/deploy-hook/` — that should return `deploy hook: ready`.

**Webhook delivery shows 503.** `DEPLOY_WEBHOOK_SECRET` is empty as far as the running
app is concerned. Check `.env` and recycle the app pool.

**Webhook returns 202, "trigger file could not be written".** The app pool identity
can't write `logs\`. Apply the `icacls` grant in step 2 of the webhook setup. Deploys
still happen on the poll in the meantime.

**Webhook says 200 but nothing deployed.** The trigger only *annotates* a run; the pull
is driven by the SHA comparison. Check `logs\auto_pull.log` — most likely the task is
stopped, or the run exited `2` on a dirty tree.
