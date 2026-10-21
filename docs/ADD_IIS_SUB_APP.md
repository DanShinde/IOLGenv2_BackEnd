# Adding any app to the server as an IIS sub-application (port 8005)

The standard way to host **any** new app on the ACG server: it becomes an IIS
sub-application of the ACG site, and people reach it at
`http://115.245.5.130:8005/<name>/`. **No new port, no router change, no firewall
change.** Every app added after AutoVerse should follow this.

Steps 1–3 are written for a Django app (the common case). A Flask or other Python web
app follows the same steps with small differences, and a non-Python app (Node, .NET, a
ready-made product) uses a reverse proxy instead — see
[section 9](#9-apps-that-are-not-django).

Two apps are already hosted this way and are working examples: the Department Planner
(`C:\department-planner-combined`, path `/deptplanner/`) was set up exactly as described
here, and One Designer (`/onedesigner/`) earlier — its longer history is in
[DEPLOY_ONEDESIGNER.md](DEPLOY_ONEDESIGNER.md).

---

## How it works

Only port **8005** is forwarded from outside. It belongs to the IIS site **ACG**. IIS
looks at the first part of the path and hands the request to the matching
*application*; each application runs its own Python (its own venv) through wfastcgi.

```text
http://115.245.5.130:8005/...
        │
   IIS site "ACG" (*:8005)
        ├── /onedesigner/*  → C:\OneDesigner                  pool OneDesignerPool
        ├── /deptplanner/*  → C:\department-planner-combined  pool DeptPlannerPool
        ├── /<name>/*       → C:\<YourApp>                    pool <YourApp>Pool   ← new
        └── everything else → C:\IOLGenv2_BackEnd (AutoVerse) pool NoManagedCode
```

Each app gets: its own folder, its own venv, its own app pool, its own FastCGI
registration. They share only the address.

### Currently used

| Path | App | Folder | App pool |
|---|---|---|---|
| `/` | AutoVerse (this repo) | `C:\IOLGenv2_BackEnd` | `NoManagedCode` |
| `/onedesigner/` | One Designer | `C:\OneDesigner` | `OneDesignerPool` |
| `/deptplanner/` | Department Planner | `C:\department-planner-combined` | `DeptPlannerPool` |

Ports in use on the server: 80 (IIS default site), 8005 (ACG), 9000/9001 (MinIO —
AutoVerse file storage), 22 (SSH), 3389 (RDP). A new app does **not** need a port.

---

## 0. Before you start

- **Pick the path name.** Short, lower case, no spaces (e.g. `qms`). It must not be one
  of AutoVerse's own first path segments: `tracker`, `planner`, `inventory`, `skillgap`,
  `estimator`, `testvault`, `forum`, `tools`, `ACGen`, `log`, `blog`, `accounts`,
  `admin`, `ckeditor`, `downloads`, `cacheclear`, `deploy-hook`, `static`, `media`,
  `__debug__` — nor an existing sub-app (`onedesigner`, `deptplanner`). Check
  [`IOLGenv2_BackEnd/urls.py`](../IOLGenv2_BackEnd/urls.py) and
  [`home/urls.py`](../home/urls.py) if unsure. A clash makes that AutoVerse page
  unreachable.
- **Work in an Administrator PowerShell** on the server.
- Below, replace these everywhere:

  | Placeholder | Example (Department Planner) |
  |---|---|
  | `<name>` — URL path | `deptplanner` |
  | `<Root>` — app folder | `C:\department-planner-combined` |
  | `<Pool>` — app pool name | `DeptPlannerPool` |
  | `<settings>` — Django settings module | `config.settings` |
  | `<project>` — package holding `wsgi.py` | `config` |

---

## 1. Folder and virtual environment

```powershell
git clone <repo-url> <Root>
cd <Root>
& "C:\Program Files\Python313\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install wfastcgi
```

- **Build the venv from `C:\Program Files\Python313`**, not a Python under your user
  profile (and not a `uv`-managed one). The app pool account cannot read
  `C:\Users\<you>\...`, and the app then fails with a 500 before Django starts
  (One Designer hit this — see its runbook §13a).
- **One venv per app.** IIS identifies a FastCGI application by its `python.exe` path.
  Two apps sharing one venv become one FastCGI application and run the same settings.

Then the usual Django first-run against the app's own `.env`:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput   # if not using WhiteNoise finders
```

---

## 2. Changes inside the new app's code

Three things. All of them are harmless when the app runs on its own at `/`.

### 2a. A WSGI wrapper that removes the prefix — `<project>/wsgi_iis.py`

wfastcgi passes the **full** path (`/<name>/home/`) to the app, so no URL would match.

```python
"""WSGI entry point when the app is an IIS application under the 8005 site."""
from django.conf import settings

from <project>.wsgi import application as _application

PREFIX = settings.URL_PREFIX


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if PREFIX and (path == PREFIX or path.startswith(PREFIX + "/")):
        environ["SCRIPT_NAME"] = PREFIX
        environ["PATH_INFO"] = path[len(PREFIX):] or "/"
    return _application(environ, start_response)
```

### 2b. Settings — prefix and cookies

Add to the settings module (driven by an environment variable, so local runs are
unchanged):

```python
URL_PREFIX = os.getenv("URL_PREFIX", "").strip().strip("/")
URL_PREFIX = f"/{URL_PREFIX}" if URL_PREFIX else ""
if URL_PREFIX:
    FORCE_SCRIPT_NAME = URL_PREFIX                  # reverse(), {% url %}, redirects, login
    # AutoVerse on the same address already uses "sessionid" / "csrftoken".
    # Same names = the browser sends both, Django keeps the wrong one, login loops.
    SESSION_COOKIE_NAME = "<name>_sessionid"
    CSRF_COOKIE_NAME = "<name>_csrftoken"
    SESSION_COOKIE_PATH = CSRF_COOKIE_PATH = URL_PREFIX + "/"

STATIC_URL = os.getenv("STATIC_URL", URL_PREFIX + "/static/")   # {% static %} ignores FORCE_SCRIPT_NAME
```

Also check:

- **Plain HTTP.** 8005 has no TLS. `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` and
  `CSRF_COOKIE_SECURE` must be **False**, or login silently fails / redirects forever.
- `DEBUG = False` and `ALLOWED_HOSTS` includes `115.245.5.130` (or `*`).
- **Hard-coded URLs.** `FORCE_SCRIPT_NAME` fixes everything Django generates, but not
  `href="/something"`, `fetch("/api/...")` or `window.location = "/..."` written by hand
  in templates and JavaScript. Search for them and use `{% url %}` / `{% static %}` /
  a base path variable instead:

  ```powershell
  rg -n "(href|src|action)=[\"']/[a-zA-Z]|fetch\([\"'\`]/|location(\.href)?\s*=\s*[\"'\`]/" <Root>
  ```
- If the app uses a JavaScript helper that reads the CSRF cookie **by name**, point it
  at the new name.

### 2c. `web.config` in `<Root>`

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
           scriptProcessor="<Root>\.venv\Scripts\python.exe|<Root>\.venv\Lib\site-packages\wfastcgi.py"
           resourceType="Unspecified"
           requireAccess="Script" />
    </handlers>
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="52428800" maxQueryString="8192" maxUrl="16384" />
      </requestFiltering>
    </security>
  </system.webServer>
  </location>
</configuration>
```

The `scriptProcessor` paths must match the FastCGI registration in step 3 **exactly**.

### 2d. Static files — pick one

- **WhiteNoise** (Department Planner): Django serves `/<name>/static/` itself. Nothing
  more to do in IIS. Simplest.
- **IIS virtual directory** (One Designer): add a `static` virtual directory under the
  application pointing at `<Root>\staticfiles`, and put this `web.config` **inside
  `staticfiles\`** so IIS serves files instead of handing them to Python:

  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <configuration>
    <system.webServer>
      <handlers>
        <clear />
        <add name="StaticFile" path="*" verb="GET,HEAD" modules="StaticFileModule"
             resourceType="File" requireAccess="Read" />
      </handlers>
    </system.webServer>
  </configuration>
  ```

  `collectstatic` does not delete it, but recreate it if `staticfiles\` is ever wiped.

Commit 2a–2c in the new app's repo.

---

## 3. IIS: app pool, permissions, FastCGI, application

The AutoVerse `web.config` already stops its own settings leaking into child
applications (`inheritInChildApplications="false"`), so nothing changes for AutoVerse.

Run in an **Administrator** PowerShell, after filling in the first block:

```powershell
$Name     = '<name>'                       # URL path, e.g. 'qms'
$Root     = '<Root>'                       # e.g. 'C:\QMS'
$Pool     = '<Pool>'                       # e.g. 'QmsPool'
$Settings = '<settings>'                   # e.g. 'config.settings'
$Handler  = '<project>.wsgi_iis.application'

$ErrorActionPreference = 'Stop'
Import-Module WebAdministration
$appcmd = "$env:windir\system32\inetsrv\appcmd.exe"
$py = "$Root\.venv\Scripts\python.exe"
$wf = "$Root\.venv\Lib\site-packages\wfastcgi.py"
if (-not (Test-Path $wf)) { throw "wfastcgi is not installed in $Root\.venv" }

# 0) Backup of the whole IIS configuration (undo with: appcmd restore backup "<name>")
& $appcmd add backup "before-$Name-$(Get-Date -Format yyyyMMdd)"

# 1) App pool: no .NET, always running, never idles out
New-WebAppPool -Name $Pool | Out-Null
Set-ItemProperty IIS:\AppPools\$Pool -Name managedRuntimeVersion -Value ''
Set-ItemProperty IIS:\AppPools\$Pool -Name startMode -Value AlwaysRunning
Set-ItemProperty IIS:\AppPools\$Pool -Name processModel.idleTimeout -Value ([TimeSpan]::Zero)

# 2) The pool's account may read and write the app folder (logs, uploads, SQLite...)
New-Item -ItemType Directory -Force "$Root\logs" | Out-Null
icacls $Root /grant "IIS AppPool\${Pool}:(OI)(CI)M" /T /Q

# 3) FastCGI application + its environment (applicationHost.config, not web.config)
& $appcmd set config -section:system.webServer/fastCgi "/+[fullPath='$py',arguments='$wf',activityTimeout='180',requestTimeout='300']" /commit:apphost
$envs = [ordered]@{
    WSGI_HANDLER           = $Handler
    DJANGO_SETTINGS_MODULE = $Settings
    PYTHONPATH             = $Root
    URL_PREFIX             = "/$Name"
    DEBUG                  = '0'
    WSGI_LOG               = "$Root\logs\wfastcgi.log"
}
foreach ($k in $envs.Keys) {
    & $appcmd set config -section:system.webServer/fastCgi "/+[fullPath='$py',arguments='$wf'].environmentVariables.[name='$k',value='$($envs[$k])']" /commit:apphost | Out-Null
}

# 4) The application under the 8005 site
New-WebApplication -Site ACG -Name $Name -PhysicalPath $Root -ApplicationPool $Pool | Out-Null
# (only for the static virtual directory option in 2d)
# New-WebVirtualDirectory -Site ACG -Application $Name -Name static -PhysicalPath "$Root\staticfiles"

Get-WebApplication -Site ACG | Format-Table Path, PhysicalPath, applicationPool -AutoSize
```

Notes:

- Values set here as environment variables **win over the app's `.env`**
  (`python-dotenv` does not overwrite variables that are already set). Put anything
  that must differ under IIS here; secrets can stay in `.env`.
- The app's working directory under FastCGI is not guaranteed to be `<Root>`. Use
  `BASE_DIR`-based paths, or set the path explicitly as an environment variable (the
  planner sets `AVATAR_DIR` this way).
- To add or change one variable later:

  ```powershell
  & $appcmd set config -section:system.webServer/fastCgi "/[fullPath='$py',arguments='$wf'].environmentVariables.[name='DEBUG'].value:0" /commit:apphost
  Restart-WebAppPool -Name $Pool
  ```

---

## 4. Link it from AutoVerse

In this repo add a sidebar entry next to the others in
[`templates/base.html`](../templates/base.html):

```html
<li class="nav-item">
  <a class="nav-link" href="/<name>/" title="<Display name>">
    <i class="bi bi-<icon>"></i><span class="nav-label sidebar-text"><Display name></span>
  </a>
</li>
```

and in the top bar of [`templates/base1.html`](../templates/base1.html):

```html
<li class="nav-item"><a class="nav-link" href="/<name>/"><Display name></a></li>
```

Use a plain same-host path like `/<name>/` — never `http://...:port/`. Commit to `main`;
auto-pull deploys it. If you edit the live checkout directly instead, recycle AutoVerse
so the templates reload:

```powershell
Restart-WebAppPool -Name NoManagedCode
```

---

## 5. Check it

```powershell
$B = 'http://localhost:8005'
foreach ($u in '/', '/onedesigner/', '/deptplanner/login', '/<name>/', '/<name>/static/<some file>') {
    try   { $r = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 "$B$u" -TimeoutSec 90; "$($r.StatusCode)  $u" }
    catch { "$($_.Exception.Response.StatusCode.value__)  $u  $($_.Exception.Response.Headers['Location'])" }
}
```

- AutoVerse `/` → 302 to its login, One Designer and the planner → 200: **nothing else
  broke.**
- `/<name>/` → 200 or a 302 whose `Location` **starts with `/<name>/`**.
- Open `/<name>/` in a browser, sign in, submit a form. Links, images and CSS must all
  stay under `/<name>/`. Check the cookie in DevTools: `<name>_sessionid`, path `/<name>/`.
- The first request after a change can take 10–30 s while Python starts.

---

## 6. Running it

| What | How |
|---|---|
| Restart the app | `Restart-WebAppPool -Name <Pool>` |
| Python errors at start-up | `<Root>\logs\wfastcgi.log` (`WSGI_LOG`) |
| Django errors (500s) | stderr is thrown away under IIS — configure a file handler in the app's `LOGGING` |
| New code | wfastcgi restarts Python by itself when a `.py` or `.config` file changes. Template-only or `.env` changes need a recycle. |
| Auto-deploy | Use the app's own pull task (see [AUTO_DEPLOY.md](AUTO_DEPLOY.md)) and give it `-AppPoolName <Pool>` so it recycles the right pool after pulling. |
| Reboot | Nothing to do: the pool is `AlwaysRunning` and IIS starts with Windows. |

### Background jobs and schedulers

Do **not** rely on a scheduler that starts inside the web process (APScheduler, a
thread in `wsgi.py`, a loop in a custom `serve.py`):

- IIS may run **several** Python processes for one app (`maxInstances` is `0` =
  automatic), so each one would run the job — duplicate mails.
- FastCGI stops an idle Python process after **5 minutes** (`idleTimeout` 300), and the
  scheduler dies with it.

Run jobs as **Windows Scheduled Tasks** instead, e.g. daily at 08:00:

```powershell
$act = New-ScheduledTaskAction -Execute "<Root>\.venv\Scripts\python.exe" -Argument "manage.py send_reminders" -WorkingDirectory "<Root>"
Register-ScheduledTask -TaskName "<Name> reminders" -Action $act -Trigger (New-ScheduledTaskTrigger -Daily -At 8am) -User SYSTEM -RunLevel Highest
```

The Department Planner's daily reminders and its daily database backup used to run
inside its `serve.py`; under IIS they must be scheduled tasks like this one (its IIS
registration sets `ENABLE_SCHEDULER=0`).

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **500.19** "Cannot add duplicate collection entry" | A parent `web.config` without `inheritInChildApplications="false"` | Wrap the parent's `<system.webServer>` in `<location path="." inheritInChildApplications="false">` (already done for AutoVerse). |
| **500** before Django loads; `wfastcgi.log` empty or missing | Wrong `python.exe`/`wfastcgi.py` path, `web.config` and FastCGI registration don't match, or the pool account can't read the venv | Compare `scriptProcessor` with `appcmd list config -section:system.webServer/fastCgi`; rebuild the venv from `C:\Program Files\Python313`; re-run the `icacls` grant. |
| Every page is **404** from Django | `WSGI_HANDLER` is not the `wsgi_iis` wrapper | Set `WSGI_HANDLER=<project>.wsgi_iis.application`. |
| Links/redirects go to `/home/` instead of `/<name>/home/` | `URL_PREFIX` not set | Add the variable to the FastCGI registration; recycle. |
| CSS/JS missing | `STATIC_URL` lacks the prefix, or (vdir option) `staticfiles\web.config` missing | See 2b / 2d. |
| Login goes back to the login page; or AutoVerse logs you out | Cookie name clash with AutoVerse | Distinct `SESSION_COOKIE_NAME` / `CSRF_COOKIE_NAME` (2b); clear the browser's cookies for the address once. |
| **403 CSRF** on every form | Secure cookies over HTTP, or the CSRF cookie name in JS is wrong | 2b. |
| Both apps show the same pages/settings | Two apps share one venv | Separate venv per app (step 1). |
| AutoVerse page suddenly 404s | The new app's path equals an AutoVerse URL | Rename the application (step 0). |

---

## 8. Removing an app (rollback)

```powershell
Import-Module WebAdministration
$appcmd = "$env:windir\system32\inetsrv\appcmd.exe"
Remove-WebApplication -Site ACG -Name <name>
& $appcmd set config -section:system.webServer/fastCgi "/-[fullPath='<Root>\.venv\Scripts\python.exe',arguments='<Root>\.venv\Lib\site-packages\wfastcgi.py']" /commit:apphost
Remove-WebAppPool -Name <Pool>
```

Or restore the whole IIS configuration to the backup taken in step 3
(`appcmd list backup`, then `appcmd restore backup "<backup name>"`) — this also undoes
any other IIS change made since. Remove the sidebar link from AutoVerse afterwards.

---

## 9. Apps that are not Django

### Flask or any other Python WSGI app

Same steps 1, 3, 4, 5. Differences in step 2:

- **2a**: same wrapper, but import your app object (`from app import app as _application`)
  and read the prefix from `os.environ["URL_PREFIX"]` instead of Django settings.
  Setting `SCRIPT_NAME` is what makes Flask's `url_for()` and redirects carry the prefix
  — there is no `FORCE_SCRIPT_NAME` to set.
- **2b**: give the session cookie its own name and path
  (Flask: `SESSION_COOKIE_NAME = "<name>_session"`, `SESSION_COOKIE_PATH = "/<name>/"`),
  keep cookies non-secure over HTTP, and fix hand-written absolute URLs as above.
- **Step 3**: `WSGI_HANDLER` points at the wrapper (`wsgi_iis.application`); drop
  `DJANGO_SETTINGS_MODULE`.

FastAPI and other **ASGI-only** apps cannot run under wfastcgi — treat them like the
next case.

### Anything else (Node, .NET, ASGI, a vendor product with its own server)

Run the app as its own service bound to **`127.0.0.1`** on a free local port (e.g.
8006 or 8008–8010; avoid 80, 8005, 9000, 9001), and let the ACG site forward
`/<name>/` to it. URL Rewrite and Application Request Routing (ARR) are already
installed on the server and proxying is enabled.

1. Start the app on `127.0.0.1:<port>` as a Windows service or a scheduled task
   that starts at boot. **Bind to 127.0.0.1, not 0.0.0.0** — Windows Firewall is off
   on this server, so anything bound to all addresses is open to the whole office
   network.
2. Tell the app it lives under `/<name>/` (most frameworks have a "base path" /
   "root path" / `PUBLIC_URL` setting) and give its cookies their own name and path.
3. Add a rewrite rule for the path. Create an IIS application `/<name>` (as in step 3,
   but it needs no FastCGI registration) whose `web.config` holds only the proxy rule:

   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <configuration>
     <location path="." inheritInChildApplications="false">
     <system.webServer>
       <rewrite>
         <rules>
           <rule name="proxy-<name>" stopProcessing="true">
             <match url="(.*)" />
             <action type="Rewrite" url="http://127.0.0.1:<port>/{R:1}" />
           </rule>
         </rules>
       </rewrite>
     </system.webServer>
     </location>
   </configuration>
   ```

   This forwards with the `/<name>` prefix removed. If the app expects to see the
   prefix itself, use `url="http://127.0.0.1:<port>/<name>/{R:1}"`.
4. The proxy sends the app `Host: 127.0.0.1:<port>`. If the app checks the request's
   origin (CSRF) or builds absolute links, add `http://115.245.5.130:8005` to its
   trusted origins, or turn on ARR's *Preserve host header* (server-wide setting:
   IIS Manager → server → Application Request Routing Cache → Server Proxy Settings).
5. Link it from AutoVerse (step 4) and test (step 5) as usual.
