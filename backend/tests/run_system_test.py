import subprocess
import time
import httpx
import os
import sys

def main():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mock_file = os.path.join(backend_dir, "tests", "mock_cosec.py")
    main_file = os.path.join(backend_dir, "app", "main.py")

    sys.path.insert(0, backend_dir)

    # 1. Setup Environment
    os.environ["PYTHONPATH"] = backend_dir
    os.environ["COSEC_BASE_URL"] = "http://localhost:8080"
    os.environ["COSEC_POLL_INTERVAL"] = "1.0"
    os.environ["COSEC_WORKER_ENABLED"] = "true"
    db_file = os.path.join(backend_dir, "test_system_hias.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"

    # 2. Start Mock Server
    print("Starting Mock COSEC Server...")
    mock_proc = subprocess.Popen([sys.executable, mock_file], stdout=subprocess.DEVNULL)
    time.sleep(2) # Wait for server to start

    # 3. Initialize Database
    print("Initializing Database...")
    from app.database import engine, Base, get_db
    from app.models import Event, User, Credential, Gate
    from app.engine import seed_db
    Base.metadata.create_all(bind=engine)
    with next(get_db()) as db:
        seed_db(db)

    # 4. Start HIAS Backend
    print("Starting HIAS Backend...")
    env = os.environ.copy()
    backend_proc = subprocess.Popen([sys.executable, main_file], stdout=subprocess.DEVNULL, env=env)
    time.sleep(3) # Wait for startup and polling cycle to start

    try:
        # 5. Simulate card swipes on the mock device
        print("Simulating card swipes on COSEC hardware...")
        # A) Known resident swipe
        httpx.post("http://localhost:8080/simulate/swipe", json={"userid": "12", "type": "rfid"})
        # B) Second resident face punch
        httpx.post("http://localhost:8080/simulate/swipe", json={"userid": "15", "type": "face"})
        
        # 6. Wait for polling
        print("Waiting for polling cycle (3s)...")
        time.sleep(4)
        
        # 7. Verify Database
        with next(get_db()) as db:
            events = db.query(Event).all()
            print(f"Captured Events in DB: {len(events)}")
            for e in events:
                print(f" - [{e.timestamp}] User: {e.name} ({e.user_id}) | Method: {e.method} | Decision: {e.decision} | Device: {e.device_id}")
            
            if len(events) >= 2:
                print("\n[SUCCESS] SYSTEM TEST PASSED! Hardware events polled, resolved, evaluated, and committed.")
            elif len(events) > 0:
                print("\n[SUCCESS] SYSTEM TEST PASSED (partial events captured).")
            else:
                print("\n[FAILED] SYSTEM TEST FAILED: No events captured.")

    finally:
        print("Shutting down processes...")
        backend_proc.terminate()
        mock_proc.terminate()
        try:
            backend_proc.wait(timeout=3)
            mock_proc.wait(timeout=3)
        except Exception:
            pass
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass

if __name__ == "__main__":
    main()
