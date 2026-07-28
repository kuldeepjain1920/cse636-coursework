"""Deliberately missing a dependency: uses `requests` but requirements.txt
doesn't list it, to demonstrate the auto-remediation agent."""
import requests

def get_status_code(url):
    return requests.get(url, timeout=5).status_code
