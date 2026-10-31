import requests
import time

BASE_URL = "http://127.0.0.1:8000"

def run_failure_scenarios():
    print("Starting Phase 5: Failure Testing...")
    
    # 1. Malformed JSON
    print("\n[1/4] Testing Malformed JSON...")
    try:
        response = requests.post(
            f"{BASE_URL}/access/event", 
            data="{'invalid_json': True}", 
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code} (Expected: 400/422)")
    except Exception as e:
        print(f"Error: {e}")

    # 2. Incomplete Payload
    print("\n[2/4] Testing Missing Fields...")
    payload = {"user_id": "S001"} # Missing method and device_id
    response = requests.post(f"{BASE_URL}/access/event", json=payload)
    print(f"Status: {response.status_code} (Expected: 422)")

    # 3. Duplicate Flood (Fast)
    print("\n[3/4] Testing Duplicate Flood (within 100ms)...")
    payload = {"user_id": "S001", "method": "RFID", "device_id": "test_dup"}
    for i in range(5):
        response = requests.post(f"{BASE_URL}/access/event", json=payload)
        print(f"Request {i+1}: {response.status_code}")

    # 4. Unknown User
    print("\n[4/4] Testing Unknown User...")
    payload = {"user_id": "S999", "method": "RFID", "device_id": "test_unknown"}
    response = requests.post(f"{BASE_URL}/access/event", json=payload)
    event = response.json()
    print(f"Status: {response.status_code} | Decision: {event['decision']} | Reason: {event['reason']}")

if __name__ == "__main__":
    run_failure_scenarios()

