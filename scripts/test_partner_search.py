import requests
import json

url = 'http://localhost:8000/api/v1/partners/search'
payload = {
    'target_region': 'Mumbai',
    'project_goal': 'AI-driven maternal nutrition pilot for rural mothers'
}

print(f"Calling: {url}")
try:
    r = requests.post(url, json=payload, timeout=30)
    print(f"STATUS: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print("\n--- Ranked Results ---")
        for i, res in enumerate(data.get('results', []), 1):
            title = res.get('title')
            ptype = res.get('partner_type')
            city = res.get('city')
            reasoning = res.get('alignment_reasoning')
            
            print(f"Rank {i}: {title}")
            print(f"  Type: {ptype}")
            print(f"  City: {city}")
            print(f"  Reasoning: {reasoning}")
            print("-" * 50)
    else:
        print(f"ERROR: {r.text}")
except Exception as e:
    print(f"FAILED: {e}")
