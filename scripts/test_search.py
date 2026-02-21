import requests
import json

def test_search():
    url = "http://127.0.0.1:8000/api/v1/channels/search"
    payload = {
        "district": "Hyderabad",
        "demographic": "Urban",
        "specific_need": "maternal vaccination outreach"
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        print(f"Sending request to {url}...")
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_search()
