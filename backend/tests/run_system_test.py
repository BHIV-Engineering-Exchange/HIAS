import subprocess
import time
import httpx
import os
import sys

def main():
    # 1. Setup Environment
    os.environ["PYTHONPATH"] = "."
    os.environ["COSEC_BASE_URL"] = "http://localhost:8080"
    os.environ["COSEC_POLL_INTERVAL"] = "1.0"
    os.environ["DATABASE_URL"] = "sqlite:///./test_hias.db"

    # 2. Start Mock Server
    print("Starting Mock COSEC Server...")
    mock_proc = subprocess.Popen([sys.executable, "tests/mock_cosec.py"], stdout=subprocess.DEVNULL)
    time.sleep(2) # Wait for server to start

    # 3. Initialize Database
    print("Initializing Database...")
    from app.database import engine, Base, get_db
    from app.models import Event
    Base.metadata.create_all(bind=engine)

    # 4. Start HIAS Backend
    print("Starting HIAS Backend...")
    backend_proc = subprocess.Popen([sys.executable, "app/main.py"], stdout=subprocess.DEVNULL)
    time.sleep(3) # Wait for polling cycle to start

    try:
        # 5. Simulate a swipe on the mock device
        print("Simulating a card swipe (User ID: 12 -> S001)...")
        httpx.post("http://localhost:8080/simulate/swipe", json={"userid": "12", "type": "rfid"})
        
        # 6. Wait for polling
        print("Waiting for polling cycle (3s)...")
        time.sleep(4)
        
        # 7. Verify Database
        with next(get_db()) as db:
            events = db.query(Event).all()
            print(f"Captured Events in DB: {len(events)}")
            for e in events:
                print(f" - [{e.timestamp}] User: {e.name} ({e.user_id}) | Decision: {e.decision}")
            
            if len(events) > 0:
                print("\n✅ SYSTEM TEST PASSED!")
            else:
                print("\n❌ SYSTEM TEST FAILED: No events captured.")

    finally:
        print("Shutting down processes...")
        backend_proc.terminate()
        mock_proc.terminate()
        if os.path.exists("./test_hias.db"):
            os.remove("./test_hias.db")

if __name__ == "__main__":
    main()

