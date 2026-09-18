# Deployment automation for the IIS/wfastcgi host.
#
# This package is deliberately NOT in INSTALLED_APPS: it has no models, templates or
# admin, only the GitHub webhook endpoint in views.py. It sits next to the PowerShell
# scripts (auto_pull.ps1, Register-AutoPullTask.ps1) that do the privileged work, so
# the whole deploy story lives in one folder. See docs/AUTO_DEPLOY.md.
