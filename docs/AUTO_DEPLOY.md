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

## The current deployment

Filled in from the live setup, so a second machine has something concrete to compare
against. Find your own equivalents in [Step 4](#4-grant-the-app-pool-write-access-to-logs).

| Thing | Value here |
|---|---|
| Checkout | `C:\IOLGenv2_BackEnd` |
| Virtualenv | `C:\IOLGenv2_BackEnd\.venv` |
| IIS site | `ACG` |
| IIS app pool | `NoManagedCode` (identity: `ApplicationPoolIdentity`) |
| Public URL | `http://115.245.5.130:8005` |
| Task name | `IOLGen AutoPull`, every 1 minute |
| Task logon | `S4U` as `ARMSTRONGLTD\pravin.shinde` — no stored password |
| Git auth | Read-only fine-grained PAT in the remote URL |
| Restart method | Touch `web.config` (pool not confirmed exclusive to this site) |

---

## Install (once, on the VM)

Follow in order. Each step verifies before the next depends on it.

### 1. Get the code onto the server

The scripts ship in the repo, so the first update is manual — auto-pull cannot install
itself:

```powershell
cd C:\IOLGenv2_BackEnd
git pull --ff-only origin main
```

### 2. Make git authenticate without a prompt

**Do this before registering the task.** An unattended task cannot answer a credential
prompt; it will hang until the 30-minute execution limit kills it.

Unless you are using the default `-LogonType Password` with a stable password, set up a
read-only PAT or deploy key now — see
[Logon type and git credentials](#logon-type-and-git-credentials). Then prove it:

```powershell
git pull --ff-only origin main
```

Must return with **no prompt**. `Already up to date.` counts as a pass.

> Git writes progress to stderr, which PowerShell ISE paints **red** as a
> `NativeCommandError`. That is not a failure — read the `Fast-forward` /
> `Already up to date` line underneath it.

### 3. Register the scheduled task

From an **elevated** prompt (the script throws otherwise):

```powershell
cd C:\IOLGenv2_BackEnd
.\deploy\Register-AutoPullTask.ps1 -IntervalMinutes 1 -LogonType S4U
```

Use `-LogonType S4U` whenever the account's password rotates. Drop to
`-IntervalMinutes 3` if you are not setting up the webhook.

Success ends with a **green** `Registered.` line. The script verifies the task really
exists first, so anything else throws rather than printing a false success.

Then confirm it runs unattended:

```powershell
Get-ScheduledTask -TaskName 'IOLGen AutoPull' | Select-Object TaskName, State
Start-ScheduledTask -TaskName 'IOLGen AutoPull'
Get-Content C:\IOLGenv2_BackEnd\logs\auto_pull.log -Tail 20
```

`State: Ready` and a log line `Up to date at <sha>`. Wait two or three minutes and check
the log again — you should see **one entry per minute**, which is the real proof that
the logon, git auth and repetition all work with nobody logged on:

```text
15:30:45 [INFO] Up to date at de0a53d
15:31:45 [INFO] Up to date at de0a53d
15:32:45 [INFO] Up to date at de0a53d
```

At this point auto-deploy is already working. Everything below only adds the webhook.

### 4. Grant the app pool write access to `logs\`

Find the site and pool serving the app:

```powershell
Import-Module WebAdministration
Get-Website | Where-Object { $_.physicalPath -like '*IOLGenv2_BackEnd*' } |
    Select-Object Name, applicationPool, physicalPath
```

Check what identity that pool runs as:

```powershell
(Get-ItemProperty "IIS:\AppPools\<YourPoolName>" -Name processModel) |
    Select-Object identityType, userName
```

| `identityType` | Grant this |
|---|---|
| `ApplicationPoolIdentity` | `"IIS AppPool\<YourPoolName>"` |
| `SpecificUser` | the `userName` shown |
| `NetworkService` | `"NETWORK SERVICE"` |

```powershell
icacls C:\IOLGenv2_BackEnd\logs /grant "IIS AppPool\NoManagedCode:(OI)(CI)M"
icacls C:\IOLGenv2_BackEnd\logs
```

The second line should list your pool with `(OI)(CI)(M)` and **no** `(I)` — an explicit
entry, not an inherited one.

> **Should you also pass `-AppPoolName` to the task?** Only if that pool serves this site
> alone — check with `Get-Website | Select-Object Name, applicationPool`. Recycling a
> shared pool would restart every site on it on every deploy. Touching `web.config` (the
> default) restarts only this app, which is why it is the safer default.

### 5. Set the webhook secret

```powershell
C:\IOLGenv2_BackEnd\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Add to `C:\IOLGenv2_BackEnd\.env` — no quotes, no trailing whitespace:

```ini
DEPLOY_WEBHOOK_SECRET=<the generated string>
```

Then recycle so Django re-reads `.env`, and confirm the route:

```powershell
iisreset
curl.exe -s http://115.245.5.130:8005/deploy-hook/
```

Expect `deploy hook: ready`. (Without `-s`, curl's progress meter also shows up red in
ISE — harmless.)

### 6. Add the hook in GitHub

**Repo → Settings → Webhooks → Add webhook**

| Field | Value |
|---|---|
| Payload URL | `http://115.245.5.130:8005/deploy-hook/` |
| Content type | **`application/json`** — see the warning below |
| Secret | the same string as `.env` |
| SSL verification | n/a on plain HTTP |
| Events | **Just the push event** |
| Active | ✔ |

> ⚠️ **`application/json` is the single most common mistake here.** The default is
> `application/x-www-form-urlencoded`, which wraps the JSON in a `payload=` form field.
> The signature still verifies, so the request gets *past* authentication and then fails
> to parse — a **400**, which looks like a signing problem but is not one.

GitHub sends a `ping` immediately; the endpoint answers `pong` and the delivery goes
green.

### 7. Prove it end to end

Push a trivial commit to `main`, then:

```powershell
Get-Content C:\IOLGenv2_BackEnd\logs\auto_pull.log -Tail 20
```

Three lines in sequence is the whole pipeline:

```text
Webhook trigger consumed - push to main by <user> -> <sha>
New commits on origin/main : <old> -> <new>
Update complete at <new>
```

> **Test with a real push, not "Redeliver".** A redelivery replays the request exactly as
> it was recorded, including the old `Content-Type` — so it will keep failing after you
> fix the setting and tell you nothing.

To remove the task: `.\deploy\Register-AutoPullTask.ps1 -Unregister`

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

## Logon type and git credentials

These two choices are linked: how the task logs on decides what git can use to
authenticate. Pick the row that matches your environment.

| `-LogonType` | Password stored? | Survives password rotation | Git auth available |
|---|---|---|---|
| `Password` (default) | Yes | **No** | Credential Manager, PAT, or deploy key |
| `S4U` | No | Yes | PAT or deploy key only |
| `System` | No | Yes | PAT or deploy key only |

**If the account's password rotates — on a monthly domain policy, say — do not use
`Password`.** Task Scheduler keeps using the old password, every run fails to log on,
and deploys stop with no error anywhere except the task's history. Use `S4U`.

Only a password logon can open Windows Credential Manager, because its secrets are
sealed with a DPAPI key that unlocks from the logon password. S4U and SYSTEM get a
local-only token with no DPAPI access, so `credential.helper=manager` cannot work
under them — which is why those two need a token or key instead.

### Recommended: S4U + a read-only PAT

Keeps the deploy running as your own account, stores no password, and never needs
touching when the domain password changes.

1. Create a **fine-grained personal access token** on GitHub with read-only
   **Contents** access to this repository only.

2. Put it in the remote URL, as the account the task will run as:

   ```powershell
   cd C:\IOLGenv2_BackEnd
   git remote set-url origin https://<PAT>@github.com/DanShinde/IOLGenv2_BackEnd.git
   git pull --ff-only origin main   # must succeed with no prompt
   ```

   The token lives in `.git\config`, which is on the server and NTFS-protected. It is
   read-only and scoped to one repo, so a leak cannot be used to push. Restrict the
   file if the VM has other users:

   ```powershell
   icacls C:\IOLGenv2_BackEnd\.git\config /inheritance:r /grant "%USERNAME%:R" "Administrators:F"
   ```

3. Register the task without a password:

   ```powershell
   .\deploy\Register-AutoPullTask.ps1 -IntervalMinutes 1 -LogonType S4U
   ```

Rotating the PAT later is one `git remote set-url` — no task changes.

> **Prefer a credentials file to a URL?** `git config --local credential.helper ""`
> followed by `git config --local --add credential.helper store`, then one manual
> `git pull` where you paste the PAT as the password. The empty value first is what
> clears the inherited `manager` helper; without it git tries `manager` first and
> hangs waiting for a prompt. The token lands in `%USERPROFILE%\.git-credentials`.

### Cleanest: an SSH deploy key

If the VM can reach GitHub on port 22, a read-only deploy key beats both. Generate a
key as the task account, add the public half under **Repo → Settings → Deploy keys**
(leave *Allow write access* unchecked), and switch the remote:

```powershell
git remote set-url origin git@github.com:DanShinde/IOLGenv2_BackEnd.git
```

Nothing expires, nothing rotates, and the key cannot push. Combine with `-LogonType S4U`.

### If the password is stable

Credential Manager is fine. Log in as the task account once, run `git pull`
interactively so the manager stores the credential, and register with the default
`-LogonType Password`.

### Not usually worth it: gMSA

A group Managed Service Account has AD rotate its password automatically and works with
Task Scheduler. It needs a domain admin to create it, and it still has no Credential
Manager — so it lands on the same PAT or deploy key as S4U, for more setup. Only makes
sense if your policy forbids S4U.

---

## About the webhook endpoint

Setup lives in [Install](#install-once-on-the-vm) steps 4-6. This is what the endpoint
actually does once it is running.

- Verifies `X-Hub-Signature-256` with `hmac.compare_digest`. Anything unsigned or
  tampered gets a **404**, not a 403 — an unauthenticated caller learns nothing.
- Acts only on `push` to `refs/heads/main`. Other branches, tags, **branch deletions**
  and non-push events are acknowledged with 200 and ignored. A branch deletion looks
  like a push in the payload (`"deleted": true`, `"after": "0000…"`) and is meant to be
  ignored.
- Never runs git, pip, or a shell. Never imports GitPython. It writes one file.
- Caps the request body at 1 MB.
- Returns **503** until `DEPLOY_WEBHOOK_SECRET` is set, rather than trusting an
  unsigned caller.

Verified against bad, missing and tampered signatures, ping, non-main pushes, branch
deletion, malformed JSON, wrong HTTP method, and unconfigured-secret — 13 cases.

### Response codes, and what each one means

| Code | Meaning |
|---|---|
| 200 `Trigger accepted` | Working. `logs\deploy.trigger` written. |
| 200 `Ignoring …` | Not a push to `main`. Expected for other branches and deletions. |
| 200 `pong` | The `ping` GitHub sends when the hook is created. |
| **400** | Signature verified, body would not parse — **almost always Content type set to `x-www-form-urlencoded` instead of `application/json`.** A 400 is therefore good news about your secret. |
| 404 | Signature did not verify: secret mismatch, or the body changed after signing. |
| 202 | Signed and accepted, but the trigger file could not be written — the app pool lacks write access to `logs\`. The poll still deploys. |
| 503 | `DEPLOY_WEBHOOK_SECRET` is empty as far as the running app is concerned. |

### On latency

The task interval is the floor. A push goes live in about a minute — the webhook does
**not** make it instant, because Task Scheduler has no native "run when this file
appears" trigger. What it buys is a 1-minute worst case instead of 3-5 minutes, plus a
log line naming the exact push behind each deploy. Sub-minute would need an
always-running watcher service, which is a bigger commitment than this warrants.

The poll is also the safety net: if a delivery fails or the trigger cannot be written,
the next tick compares SHAs and pulls anyway.

### On plain HTTP

The payload and signature header cross the internet in the clear. The HMAC still
prevents forgery — the secret itself is never transmitted — but an observer can read the
payload and replay it. A replay only means "pull whatever is on main", so the practical
risk is low. Put the 8005 binding behind TLS when you can, and use a secret not reused
anywhere else.

---

## Troubleshooting

### Things that look like errors but are not

| What you see | What it means |
|---|---|
| Red `git : From https://github.com/…` in PowerShell ISE | Git writes progress to stderr; ISE paints all stderr red as `NativeCommandError`. Read the `Fast-forward` line underneath. |
| Red curl progress-meter block | Same thing. Use `curl.exe -s`. |
| `LastTaskResult: 267009` | `0x41301` = `SCHED_S_TASK_RUNNING`. The task was still running when queried. Re-check; it settles to `0`. |
| `LastTaskResult: 267011` | `0x41303` = the task has not run yet. |
| Webhook delivery `200 Ignoring push to 'refs/heads/…'` | Correct behaviour for a non-`main` branch, including branch deletions after a merged PR. |
| Empty `Duration` on the task's repetition | Correct — that is what "repeat indefinitely" looks like. |

### Actual problems

**Task runs but nothing happens.** Check `logs\auto_pull.log` first — the script logs
every decision, including "up to date". If the log does not exist at all, the script
never started: check Task Scheduler's History tab and `Last Run Result`.

**`git.exe not found on PATH for this account`.** Git is installed per-user, or its PATH
entry is not visible to the task account. Install Git system-wide, or add its `cmd`
folder to the machine PATH.

**Exit code 2, "Working tree has local modifications".** Someone edited a tracked file
directly on the server. Decide whether it matters: commit and push it from the VM, or
discard with `git checkout -- <file>`. The script will not choose for you.

**Exit code 2, "git pull --ff-only failed".** The VM has commits `origin/main` does not,
or `main` was force-pushed. Resolve by hand on the server.

**The run hangs and dies at the 30-minute limit with nothing logged after the fetch.**
Git is waiting on a credential prompt nobody can answer. Under `S4U` or `System` there
is no Credential Manager — switch to a PAT or deploy key, and confirm with a manual
`git pull` that returns without prompting.

**Task history shows a logon failure, result `0x8007052E`, and deploys silently
stopped.** The stored password is stale — almost always a rotated domain password.
Re-register with `-LogonType S4U` so there is nothing to go stale.

**`Register-ScheduledTask : The task XML contains a value which is incorrectly formatted
or out of range. Duration:P99999999DT23H59M59S`.** A `-RepetitionDuration` of
`[TimeSpan]::MaxValue`. Omit the parameter entirely; an empty `<Duration>` is how an
open-ended repetition is expressed. Fixed in the script — this only appears if someone
reintroduces it.

**`This script must be run from an elevated prompt`.** Registering a task under a
different logon type needs admin. Run PowerShell as Administrator.

**Code updated but the site still serves the old version.** The restart did not take.
Pass `-AppPoolName` so the script recycles the pool explicitly, or run `iisreset`.

**Migrations ran but the app 500s.** Look at `logs\err.log` (the wfastcgi log) — the pull
succeeded, so this is an application error, not a deploy one.

**Webhook 400.** Content type is `x-www-form-urlencoded`. Change it to
`application/json` and test with a **fresh push** — a redelivery replays the original
recorded headers and will keep failing.

**Webhook 404.** The secret in the GitHub hook and `DEPLOY_WEBHOOK_SECRET` in `.env`
differ, or the app was not restarted after `.env` changed. Confirm the route itself with
`curl.exe -s http://<host>:8005/deploy-hook/` — that should return `deploy hook: ready`.

**Webhook 503.** `DEPLOY_WEBHOOK_SECRET` is empty for the running app. Check `.env`,
then `iisreset`.

**Webhook 202.** The app pool cannot write `logs\`. Apply the `icacls` grant from
[Step 4](#4-grant-the-app-pool-write-access-to-logs). Deploys continue on the poll.

**Webhook 200 but nothing deployed.** The trigger only annotates a run; the pull is
driven by the SHA comparison. Check `logs\auto_pull.log` — most likely the task is
stopped, or a run exited `2` on a dirty tree.

**Deploys stopped months later, fetch failing.** The PAT expired. Renew it and re-run
`git remote set-url`; the task needs no changes. An SSH deploy key avoids this entirely.
