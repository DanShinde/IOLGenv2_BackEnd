import requests
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings




def fetch_info():
    """
    Fetch ACGenCurrentVersion and UpdateUrl periodically from the server.
    This function can be called from anywhere in the project.
    """
    base_url = "https://iolgen.onrender.com"  # Change this to your actual domain
    endpoints = [
        "/accounts/info/get_by_key/?key=ACGenCurrentVersion",
        "/accounts/info/get_by_key/?key=UpdateUrl",
        "/ACGen/standard-strings/",
        "/ACGen/cluster-templates/",
        "/IOLGen/segments/",
    ]

    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                print(f"Fetched {endpoint}: {response.text}")
            else:
                print(f"Failed {endpoint}: HTTP {response.status_code}")
        except requests.RequestException as e:
            print(f"Request error for {endpoint}: {e}")

    return "Fetch completed"



def start():
    if True or not settings.DEBUG:  # Only run in production
        scheduler = BackgroundScheduler()
        scheduler.add_job(fetch_info, 'interval', minutes=10)  # Runs every 2 minutes
        scheduler.start()