# IOLGenv2_BackEnd
 
.venv\Scripts\activate
<!-- cd IOLGenv2_BackEnd -->
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate

python manage.py collectstatic --noinput

python manage.py runserver 0.0.0.0:8005

# In case Migration fails or history messaed up use >>
python manage.py migrate tracker 0003 --fake


Open Command Prompt as Administrator:
mkdir C:\media
Step 2: Set Permissions
icacls C:\media /grant "IIS AppPool\DefaultAppPool:(OI)(CI)M"
Replace DefaultAppPool with your actual App Pool name if different.
Step 3: Create IIS Virtual Directory (IMPORTANT!)
Open IIS Manager
Navigate to your website
Right-click your site → Add Virtual Directory
Configure:
Alias: media
Physical path: C:\media
Click OK
OR via PowerShell (as Administrator):
Import-Module WebAdministration
New-WebVirtualDirectory -Site "Default Web Site" -Name "media" -PhysicalPath "C:\media"
Replace "Default Web Site" with your actual site name.
Step 4: Restart IIS
iisreset /restart
File Structure (Production)
C:\media\                           ← New location for uploads
├── bug_reports\
│   └── {report_id}\
│       └── *.jpeg

D:\Testing_All\IOLGenv2.0\
├── .venv\
└── IOLGenv2_BackEnd\
    ├── web.config                  ← Updated ✓
    ├── media\                      ← Git ignored (local dev only)
    └── IOLGenv2_BackEnd\
        └── settings.py             ← Updated ✓

# 1) Get latest refs
git fetch origin
 
# 2) Switch to your branch
git checkout TrackerPlanner02
 
# 3) Rebase your branch onto latest main
git rebase origin/main