"""
Hash Chain Implementation — SHA256-based tamper-evident linking

Each record is cryptographically linked to the previous one:
    hash(current) = SHA256(prev_hash + current_record_json)

This creates an immutable chain where:
✅ Cannot modify past records (hash wouldn't match)
✅ Cannot reorder events (prev_hash wouldn't match)
✅ Cannot insert events (chain would break)
✅ Complete audit trail (all history visible)

Example:
Event 1: hash = sha256(GENESIS + event1_data)
Event 2: hash = sha256(event1_hash + event2_data)
Event 3: hash = sha256(event2_hash + event3_data)
"""

import hashlib
import json
from typing import Optional, Dict, Tuple


class HashChain:
    """Manages SHA256 hash chain for event immutability"""

    GENESIS_HASH = "0" * 64  # Initial hash (all zeros)

    def __init__(self):
        self.last_hash = self.GENESIS_HASH

    def generate_hash(self, prev_hash: str, event_data: dict) -> str:
        """
        Generate SHA256 hash for new event

        Formula: hash(current) = SHA256(prev_hash + JSON(event_data))

        Args:
            prev_hash: Previous event hash
            event_data: Event data to hash

        Returns:
            64-character hex SHA256 digest
        """
        # Serialize event data to JSON (deterministic order)
        event_json = json.dumps(event_data, sort_keys=True, separators=(',', ':'))

        # Combine prev_hash + event_data
        combined = prev_hash + event_json

        # Generate SHA256
        hash_obj = hashlib.sha256(combined.encode('utf-8'))
        return hash_obj.hexdigest()

    def verify_chain_link(self, prev_hash: str, current_hash: str, event_data: dict) -> Tuple[bool, Optional[str]]:
        """
        Verify that current_hash is valid for given prev_hash and event_data

        Returns:
            (is_valid: bool, error_message: Optional[str])
        """
        calculated_hash = self.generate_hash(prev_hash, event_data)

        if calculated_hash != current_hash:
            return False, f"Hash mismatch: calculated {calculated_hash}, got {current_hash}"

        return True, None

    def verify_full_chain(self, events: list) -> Tuple[bool, Optional[str]]:
        """
        Verify the entire chain, including sequential hash links.
        """
        if not events:
            return True, None

        expected_prev_hash = self.GENESIS_HASH

        for i, event in enumerate(events):
            # Verify that this event links to the previous event.
            actual_prev_hash = event.get("prev_hash")
            if actual_prev_hash != expected_prev_hash:
                return False, (
                    f"Event {i} chain-link mismatch: "
                    f"expected prev_hash {expected_prev_hash}, "
                    f"got {actual_prev_hash}"
                )

            current_hash = event.get("hash")
            if not current_hash:
                return False, f"Event {i} is missing its hash"

            # Reconstruct event data, excluding hash fields.
            event_data = {
                k: v for k, v in event.items()
                if k not in ["hash", "prev_hash"]
            }

            is_valid, error_msg = self.verify_chain_link(
                actual_prev_hash,
                current_hash,
                event_data
            )
            if not is_valid:
                return False, f"Event {i} validation failed: {error_msg}"

            # The next event must reference this event's hash.
            expected_prev_hash = current_hash

        return True, None

    def get_chain_proof(self, event_hash: str, all_events: list) -> Dict:
        """
        Return event position only after verifying the complete chain.
        """
        is_valid, error = self.verify_full_chain(all_events)
        if not is_valid:
            return {
                "event_hash": event_hash,
                "verified": False,
                "reason": f"Chain integrity verification failed: {error}"
            }

        for i, event in enumerate(all_events):
            if event.get("hash") == event_hash:
                next_hash = (
                    all_events[i + 1]["hash"]
                    if i + 1 < len(all_events)
                    else None
                )
                return {
                    "event_hash": event_hash,
                    "position": i,
                    "chain_length": len(all_events),
                    "prev_hash": event["prev_hash"],
                    "next_hash": next_hash,
                    "verified": True
                }

        return {
            "event_hash": event_hash,
            "verified": False,
            "reason": "Event hash not found in chain"
        }


# ============================================================================
# HASH CHAIN EXAMPLES (For Testing)
# ============================================================================

def demo_hash_chain():
    """Demonstration of hash chain mechanics"""
    hc = HashChain()

    # Event 1
    event1_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95,
        "timestamp": "2026-04-18T08:00:00Z"
    }
    event1_hash = hc.generate_hash(hc.GENESIS_HASH, event1_data)
    print(f"Event 1 Hash: {event1_hash}")
    print(f"  Prev Hash: {hc.GENESIS_HASH}")

    # Event 2
    event2_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000002",
        "student_id": "STU002",
        "event": "ENTRY",
        "confidence": 0.87,
        "timestamp": "2026-04-18T08:05:00Z"
    }
    event2_hash = hc.generate_hash(event1_hash, event2_data)
    print(f"\nEvent 2 Hash: {event2_hash}")
    print(f"  Prev Hash: {event1_hash}")

    # Verify chain
    events = [
        {
            "hash": event1_hash,
            "prev_hash": hc.GENESIS_HASH,
            **event1_data
        },
        {
            "hash": event2_hash,
            "prev_hash": event1_hash,
            **event2_data
        }
    ]

    is_valid, error = hc.verify_full_chain(events)
    print(f"\nChain Valid: {is_valid}")
    if error:
        print(f"  Error: {error}")

    # Try to tamper
    print("\n--- TAMPERING ATTEMPT ---")
    tampered_events = [
        {
            "hash": event1_hash,
            "prev_hash": hc.GENESIS_HASH,
            "trace_id": "HIAS-20260418-a1b2c3d4-000001",
            "student_id": "STU999",  # TAMPERED!
            "event": "ENTRY",
            "confidence": 0.95,
            "timestamp": "2026-04-18T08:00:00Z"
        }
    ]
    is_valid, error = hc.verify_full_chain(tampered_events)
    print(f"Tampered Chain Valid: {is_valid}")
    print(f"  Error: {error}")


if __name__ == "__main__":
    demo_hash_chain()
