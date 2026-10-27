"""
Unit tests for integrations/local_llm_client.py
Tests:
  - LocalLLMClient offline fallback behavior
  - Typed input and response model boundaries
"""
import pytest
from integrations.local_llm_client import (
    LocalLLMClient,
    LLMAnalysisRequest,
    LLMAnalysisResponse,
)


class TestLocalLLMClient:
    def test_offline_fallback_deterministic(self):
        client = LocalLLMClient(endpoint_url="http://127.0.0.1:99999/unreachable", timeout=0.1)
        req = LLMAnalysisRequest(prompt="Audit access request for S001")
        resp = client.analyze(req)

        assert isinstance(resp, LLMAnalysisResponse)
        assert resp.success is True
        assert resp.is_fallback is True
        assert "[OFFLINE_FALLBACK]" in resp.response_text

    def test_request_model_bounds(self):
        req = LLMAnalysisRequest(prompt="Test prompt", max_tokens=100, temperature=0.5)
        assert req.max_tokens == 100
        assert req.temperature == 0.5
