# Deploying OneDesigner alongside this app on the single public port (8005)

This runbook explains how to serve a **second Django app (OneDesigner)** under the
same public port as this app, using **IIS sub-applications** — no extra port
forwarding, no nginx/Caddy.

| URL | App |
|---|---|
| `http://115.245.5.130:8005/` | **This app** (Armstrong "All‑In‑One" — the existing/"Autoverse" role). Unchanged. |
| `http://115.245.5.130:8005/onedesigner/` | **OneDesigner** (new sub‑application) |

Both apps live behind one IIS listener on 8005. IIS routes by URL path: `/onedesigner/*`
goes to the OneDesigner sub‑application; everything else stays with this app.

---

## Why the IIS sub‑application approach

This app is hosted **inside IIS via wfastcgi** (see [`web.config`](web.config) —
`FastCgiModule` + `wfastcgi.py`). When the parent app is already an IIS/wfastcgi
site, the clean way to add a second app is an **IIS Application nested under the same
site**. IIS does the path routing natively — `/onedesigner/*` is handled by the
sub‑application, everything else stays with this app — with no URL Rewrite / reverse
proxy rules required.

---

## What has already been done in THIS repo

✅ **`web.config` inheritance fix (committed on branch `iis-dual-app-hosting`).**
The parent's `<system.webServer>` is now wrapped in:

```xml
<location path="." inheritInChildApplications="false">
  <system.webServer> ... </system.webServer>
</location>
```

Without this, the OneDesigner sub‑application would **inherit** this app's
`<handlers>` (the `PythonFastCGI` handler) and `<fastCgi>` block, then redefine them
in its own `web.config`, causing startup failure:
`HTTP 500.19 – Cannot add duplicate collection entry`.

This change applies to **this app exactly as before** (it is a no‑op until a child
app exists), so there is **no regression** for existing users. Deploy this branch to
the server before adding the sub‑application.

Everything below happens on the **OneDesigner side** and in **IIS Manager on the VM**.

---

## Step 1 — Lay down OneDesigner on the server

Put OneDesigner in its own folder with its **own virtual environment**. Example:

```
C:\OneDesigner\
├── manage.py
├── OneDesigner\            (the Django project package: settings.py, wsgi.py, ...)
├── .venv\                  (SEPARATE venv — see the critical note in Step 3)
├── staticfiles\            (collectstatic target)
└── web.config              (created in Step 4)
```

> ⚠️ **Critical:** OneDesigner MUST use a **separate virtual environment** from this
> app (a different `python.exe` path). IIS keys each FastCGI application by
> `fullPath|arguments`. If both apps point at the same `python.exe` + `wfastcgi.py`,
> IIS treats them as **one** FastCGI application and both sites end up running the
> *same* Django settings. Separate venvs give distinct `fullPath` values → distinct
> FastCGI apps → correct isolation.

Install deps and run migrations from an **Administrator** prompt:

```powershell
cd C:\OneDesigner
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install wfastcgi
wfastcgi-enable          # registers the FastCGI application in applicationHost.config
python manage.py migrate
```

---

## Step 2 — OneDesigner Django `settings.py` changes

The sub‑path prefix is the single most important part. Add / set:

```python
# --- Serve everything under /onedesigner/ ---
FORCE_SCRIPT_NAME = '/onedesigner'          # Django prefixes reverse(), redirects,
                                            # login_required, etc. with this.
STATIC_URL = '/onedesigner/static/'
MEDIA_URL  = '/onedesigner/media/'          # if OneDesigner serves uploads

# Login/redirect URLs must live under the prefix too. If you set them as absolute
# paths, include the prefix; if you use named URLs + reverse(), FORCE_SCRIPT_NAME
# handles it automatically.
LOGIN_URL          = '/onedesigner/accounts/login/'   # adjust to OneDesigner's login route
LOGIN_REDIRECT_URL = '/onedesigner/'
LOGOUT_REDIRECT_URL = '/onedesigner/'

# --- Production hardening ---
DEBUG = False
ALLOWED_HOSTS = ['115.245.5.130', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = [
    'http://115.245.5.130:8005',
    # add the https origin too if/when TLS is enabled on the 8005 binding
]

# STATIC_ROOT for collectstatic
STATIC_ROOT = BASE_DIR / 'staticfiles'
```

Notes:
- `FORCE_SCRIPT_NAME` makes all **server‑side** URL generation prefix‑aware.
- It does **not** fix **hard‑coded absolute URLs in templates/JS** — see the gotcha
  in Step 6.

---

## Step 3 — Collect static files

```powershell
cd C:\OneDesigner
.\.venv\Scripts\Activate.ps1
python manage.py collectstatic --noinput
```

Static files will be requested at `/onedesigner/static/...`. Serve them via IIS (Step
5) rather than Django. (This app already serves its own static via IIS/whitenoise;
keep the two static roots separate.)

---

## Step 4 — OneDesigner `web.config`

Create `C:\OneDesigner\web.config`. This mirrors this app's pattern but points at
**OneDesigner's own venv and settings**, and is itself wrapped so its config stays
self‑contained:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <location path="." inheritInChildApplications="false">
  <system.webServer>

    <handlers>
      <remove name="StaticFile" />
      <add name="PythonFastCGI"
           path="*"
           verb="GET,HEAD,POST,PUT,DELETE,PATCH"
           modules="FastCgiModule"
           scriptProcessor="C:\OneDesigner\.venv\Scripts\python.exe|C:\OneDesigner\.venv\Lib\site-packages\wfastcgi.py"
           resourceType="Unspecified"
           requireAccess="Script" />
    </handlers>

    <fastCgi>
      <application
           fullPath="C:\OneDesigner\.venv\Scripts\python.exe"
           arguments="C:\OneDesigner\.venv\Lib\site-packages\wfastcgi.py">
        <environmentVariables>
          <environmentVariable name="DJANGO_SETTINGS_MODULE" value="OneDesigner.settings" />
          <environmentVariable name="PYTHONPATH" value="C:\OneDesigner" />
          <environmentVariable name="DJANGO_ENV" value="production" />
          <environmentVariable name="WSGI_HANDLER" value="django.core.wsgi.get_wsgi_application()" />
        </environmentVariables>
      </application>
    </fastCgi>

    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="52428800"
                       maxQueryString="8192"
                       maxUrl="16384" />
      </requestFiltering>
    </security>

  </system.webServer>
  </location>
</configuration>
```

> Update `DJANGO_SETTINGS_MODULE` / `PYTHONPATH` / the venv paths to match
> OneDesigner's real project package name and install location.

---

## Step 5 — Wire it into IIS (on the VM, IIS Manager as Administrator)

1. **Add the application** under the existing site (the one bound to 8005):
   - IIS Manager → expand the 8005 site → right‑click → **Add Application**
   - **Alias:** `onedesigner`  (this is what makes the URL `/onedesigner/`)
   - **Physical path:** `C:\OneDesigner`
   - **Application pool:** click *Select…* and choose a **new, separate pool** (next step)

2. **Create a separate Application Pool** (isolate the two Python processes):
   - IIS Manager → **Application Pools** → **Add Application Pool**
   - Name: `OneDesignerPool`
   - .NET CLR version: **No Managed Code**
   - Start mode: **AlwaysRunning** (helps survive reboots / cold starts)
   - Assign this pool to the `onedesigner` application from step 1.

3. **Static virtual directory** (serve `/onedesigner/static/` via IIS, not Django):
   - Right‑click the `onedesigner` application → **Add Virtual Directory**
   - **Alias:** `static`  →  **Physical path:** `C:\OneDesigner\staticfiles`
   - (Optional) add a `media` virtual directory the same way if OneDesigner has uploads.

   Grant the app pool identity read access, e.g.:
   ```powershell
   icacls C:\OneDesigner\staticfiles /grant "IIS AppPool\OneDesignerPool:(OI)(CI)R"
   ```

4. **PowerShell alternative** for steps 1–3:
   ```powershell
   Import-Module WebAdministration
   New-WebAppPool -Name "OneDesignerPool"
   Set-ItemProperty IIS:\AppPools\OneDesignerPool -Name managedRuntimeVersion -Value ""
   Set-ItemProperty IIS:\AppPools\OneDesignerPool -Name startMode -Value AlwaysRunning
   New-WebApplication -Site "<your 8005 site name>" -Name "onedesigner" `
       -PhysicalPath "C:\OneDesigner" -ApplicationPool "OneDesignerPool"
   New-WebVirtualDirectory -Site "<your 8005 site name>" -Application "onedesigner" `
       -Name "static" -PhysicalPath "C:\OneDesigner\staticfiles"
   ```

5. `iisreset` (or recycle both app pools) after config changes.

---

## Step 6 — Frontend gotcha: hard‑coded absolute URLs

`FORCE_SCRIPT_NAME` fixes **server‑side** URLs only. Anything hard‑coded to root in
**templates or JavaScript** will break under `/onedesigner/`. Before go‑live, grep
OneDesigner for absolute paths that ignore the prefix:

- `fetch("/api/...")`, `axios.get("/...")`, `xhr.open(..., "/...")`
- `<a href="/...">`, `<form action="/...">`, `<img src="/...">`
- `url("/static/...")` in CSS

Fix by either:
- Using Django's `{% url %}` / `{% static %}` tags (prefix‑aware), or
- Prefixing with the script name, or reading a base path injected into the page, e.g.
  `<script>window.BASE = "{{ request.META.SCRIPT_NAME }}";</script>` and building URLs
  from `window.BASE`.

---

## Step 7 — Survive a VM reboot (no manual intervention)

- IIS starts on boot (its Windows service `W3SVC` is automatic) and brings the site up.
- Set both app pools to **Start Mode = AlwaysRunning** (and optionally enable
  **Application Initialization** / preload) so the wfastcgi Python processes spin up
  without waiting for the first request.
- Because both apps run **inside IIS via wfastcgi**, there are **no standalone
  Python processes to babysit** — IIS owns their lifecycle, so there is nothing extra
  to register as a Windows service.

Verify after a test reboot that both URLs answer without anyone logging in.

---

## Production checklist (OneDesigner)

- [ ] `DEBUG = False`
- [ ] `ALLOWED_HOSTS` includes `115.245.5.130` (+ domain if any)
- [ ] `CSRF_TRUSTED_ORIGINS` includes `http://115.245.5.130:8005` (and the https origin if TLS added)
- [ ] `FORCE_SCRIPT_NAME='/onedesigner'` and `STATIC_URL='/onedesigner/static/'`
- [ ] `collectstatic` run; `/onedesigner/static/` served by IIS
- [ ] Separate app pool (`OneDesignerPool`) + **separate venv** (distinct `python.exe`)
- [ ] No standalone Python process bound to a public port (only IIS listens on 8005)
- [ ] Secret key / DB credentials via env, not committed
- [ ] (Recommended) HTTPS on the 8005 IIS binding

---

## Acceptance test (after deploy)

Run from a machine on the public internet (or with the public IP):

```powershell
# This app — must behave EXACTLY as before (no regression)
curl.exe -i http://115.245.5.130:8005/

# OneDesigner — pages, login, static, redirects all stay under /onedesigner/
curl.exe -i http://115.245.5.130:8005/onedesigner/
curl.exe -i http://115.245.5.130:8005/onedesigner/static/    # served by IIS (200/301)
```

Confirm:
- [ ] `/` serves this app unchanged
- [ ] `/onedesigner/` serves OneDesigner; login works; redirects stay under `/onedesigner/`
- [ ] Static assets load (no 404s, no requests leaking to `/static/`)
- [ ] Neither app is reachable on any other port from the internet

---

## Rollback

The change to **this** repo (the `web.config` `<location>` wrapper) is safe and
independent. If you need to remove OneDesigner:
1. IIS Manager → delete the `onedesigner` application and `OneDesignerPool`.
2. `iisreset`. This app on `/` is untouched.

The `inheritInChildApplications="false"` wrapper can stay in place permanently; it has
no effect when there are no child applications.
