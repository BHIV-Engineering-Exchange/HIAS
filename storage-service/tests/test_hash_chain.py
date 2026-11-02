"""
Test: Hash Chain Integrity

Verifies that:
✅ Hash chain is correctly generated (SHA256)
✅ Hash chain can be verified
✅ Tampering is detected
✅ Full chain linkage is maintained
"""

import pytest
import json
from app.hash_chain import HashChain


@pytest.fixture
def hash_chain():
    """Create HashChain instance"""
    return HashChain()


def test_genesis_hash(hash_chain):
    """✅ Genesis hash should be all zeros"""
    assert hash_chain.GENESIS_HASH == "0" * 64
    assert len(hash_chain.GENESIS_HASH) == 64


def test_generate_hash(hash_chain):
    """✅ Hash generation should produce valid SHA256"""
    event_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    hash_value = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event_data)
    
    assert hash_value is not None
    assert len(hash_value) == 64  # SHA256 produces 64 hex chars
    assert all(c in '0123456789abcdef' for c in hash_value)


def test_hash_deterministic(hash_chain):
    """✅ Same event should always produce same hash"""
    event_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event_data)
    hash2 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event_data)
    
    assert hash1 == hash2, "Same input should produce same hash"


def test_hash_sensitive_to_data(hash_chain):
    """✅ Different events should produce different hashes"""
    event1 = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    event2 = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU002",  # Different student
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event1)
    hash2 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event2)
    
    assert hash1 != hash2, "Different events should produce different hashes"


def test_verify_valid_chain_link(hash_chain):
    """✅ Valid chain link should verify successfully"""
    event_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    prev_hash = hash_chain.GENESIS_HASH
    current_hash = hash_chain.generate_hash(prev_hash, event_data)
    
    is_valid, error = hash_chain.verify_chain_link(prev_hash, current_hash, event_data)
    
    assert is_valid is True
    assert error is None


def test_verify_invalid_chain_link(hash_chain):
    """❌ Tampered hash should not verify"""
    event_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    prev_hash = hash_chain.GENESIS_HASH
    correct_hash = hash_chain.generate_hash(prev_hash, event_data)
    tampered_hash = "a" * 64  # Fake hash
    
    is_valid, error = hash_chain.verify_chain_link(prev_hash, tampered_hash, event_data)
    
    assert is_valid is False
    assert error is not None
    assert "mismatch" in error.lower()


def test_tamper_detection(hash_chain):
    """❌ Tampering should be detected"""
    event_data = {
        "trace_id": "HIAS-20260418-a1b2c3d4-000001",
        "student_id": "STU001",
        "event": "ENTRY",
        "confidence": 0.95
    }
    
    prev_hash = hash_chain.GENESIS_HASH
    original_hash = hash_chain.generate_hash(prev_hash, event_data)
    
    # Try to verify with tampered event data
    tampered_event = event_data.copy()
    tampered_event['student_id'] = "STU999"
    
    is_valid, error = hash_chain.verify_chain_link(prev_hash, original_hash, tampered_event)
    
    assert is_valid is False, "Tampered event should not verify"


def test_full_chain_verification(hash_chain):
    """✅ Complete chain should verify successfully"""
    events = [
        {
            "hash": hash_chain.generate_hash(hash_chain.GENESIS_HASH, {"n": 1}),
            "prev_hash": hash_chain.GENESIS_HASH,
            "n": 1
        }
    ]
    
    # Add more events
    for i in range(2, 5):
        prev_hash = events[-1]['hash']
        event_data = {"n": i}
        current_hash = hash_chain.generate_hash(prev_hash, event_data)
        
        events.append({
            "hash": current_hash,
            "prev_hash": prev_hash,
            "n": i
        })
    
    is_valid, error = hash_chain.verify_full_chain(events)
    
    assert is_valid is True
    assert error is None


def test_chain_break_detection(hash_chain):
    """❌ Broken chain should not verify"""
    events = [
        {
            "hash": hash_chain.generate_hash(hash_chain.GENESIS_HASH, {"n": 1}),
            "prev_hash": hash_chain.GENESIS_HASH,
            "n": 1
        }
    ]
    
    # Create a broken chain (wrong prev_hash)
    events.append({
        "hash": "a" * 64,
        "prev_hash": "b" * 64,  # Wrong prev_hash
        "n": 2
    })
    
    is_valid, error = hash_chain.verify_full_chain(events)
    
    assert is_valid is False
    assert error is not None


def test_chain_proof(hash_chain):
    """✅ Proof of inclusion should work"""
    # Create chain
    event1 = {"trace_id": "T1", "n": 1}
    event2 = {"trace_id": "T2", "n": 2}
    
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event1)
    hash2 = hash_chain.generate_hash(hash1, event2)
    
    events = [
        {"hash": hash1, "prev_hash": hash_chain.GENESIS_HASH, **event1},
        {"hash": hash2, "prev_hash": hash1, **event2}
    ]
    
    # Get proof for event1
    proof = hash_chain.get_chain_proof(hash1, events)
    
    assert proof['verified'] is True
    assert proof['position'] == 0
    assert proof['next_hash'] == hash2
    assert proof['prev_hash'] == hash_chain.GENESIS_HASH


def test_non_existent_hash_proof(hash_chain):
    """❌ Proof for non-existent hash should fail"""
    events = []
    
    proof = hash_chain.get_chain_proof("fake_hash", events)
    
    assert proof['verified'] is False
    assert "not found" in proof['reason'].lower()


def test_valid_two_event_chain(hash_chain):
    """✅ Valid two-event chain should verify successfully"""
    event1_data = {"trace_id": "T1", "student_id": "S001", "event": "ENTRY"}
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event1_data)
    event1 = {"hash": hash1, "prev_hash": hash_chain.GENESIS_HASH, **event1_data}

    event2_data = {"trace_id": "T2", "student_id": "S001", "event": "EXIT"}
    hash2 = hash_chain.generate_hash(hash1, event2_data)
    event2 = {"hash": hash2, "prev_hash": hash1, **event2_data}

    is_valid, error = hash_chain.verify_full_chain([event1, event2])
    assert is_valid is True
    assert error is None


def test_modified_event_payload(hash_chain):
    """❌ Tampered payload in chain should fail validation"""
    event1_data = {"trace_id": "T1", "student_id": "S001", "event": "ENTRY"}
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event1_data)
    event1 = {"hash": hash1, "prev_hash": hash_chain.GENESIS_HASH, **event1_data}

    event2_data = {"trace_id": "T2", "student_id": "S001", "event": "EXIT"}
    hash2 = hash_chain.generate_hash(hash1, event2_data)
    # Modify payload of event2
    event2 = {"hash": hash2, "prev_hash": hash1, **event2_data, "event": "ENTRY"}

    is_valid, error = hash_chain.verify_full_chain([event1, event2])
    assert is_valid is False
    assert "validation failed" in error


def test_broken_prev_hash_link(hash_chain):
    """❌ Broken sequential link between events should be detected"""
    event1_data = {"trace_id": "T1", "student_id": "S001", "event": "ENTRY"}
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event1_data)
    event1 = {"hash": hash1, "prev_hash": hash_chain.GENESIS_HASH, **event1_data}

    # Event 2 has an unrelated prev_hash even if its internal hash matches that unrelated prev_hash
    unrelated_prev_hash = "f" * 64
    event2_data = {"trace_id": "T2", "student_id": "S001", "event": "EXIT"}
    hash2 = hash_chain.generate_hash(unrelated_prev_hash, event2_data)
    event2 = {"hash": hash2, "prev_hash": unrelated_prev_hash, **event2_data}

    is_valid, error = hash_chain.verify_full_chain([event1, event2])
    assert is_valid is False
    assert "chain-link mismatch" in error
    assert f"expected prev_hash {hash1}" in error


def test_missing_event_hash(hash_chain):
    """❌ Missing event hash should be caught"""
    event1_data = {"trace_id": "T1", "student_id": "S001", "event": "ENTRY"}
    hash1 = hash_chain.generate_hash(hash_chain.GENESIS_HASH, event1_data)
    event1 = {"hash": hash1, "prev_hash": hash_chain.GENESIS_HASH, **event1_data}

    event2 = {
        "prev_hash": hash1,
        "trace_id": "T2",
        "student_id": "S001",
        "event": "EXIT"
    }

    is_valid, error = hash_chain.verify_full_chain([event1, event2])
    assert is_valid is False
    assert "missing its hash" in error


def test_chain_proof_rejects_broken_chain():
    hc = HashChain()
    event_data = {
        "trace_id": "TRACE-001",
        "student_id": "STU001",
        "event": "ENTRY",
    }
    event_hash = hc.generate_hash(hc.GENESIS_HASH, event_data)
    broken_chain = [{
        "hash": event_hash,
        "prev_hash": "f" * 64,
        **event_data,
    }]
    proof = hc.get_chain_proof(event_hash, broken_chain)
    assert proof["verified"] is False
    assert "integrity verification failed" in proof["reason"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
