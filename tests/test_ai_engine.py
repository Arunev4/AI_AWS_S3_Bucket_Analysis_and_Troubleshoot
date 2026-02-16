"""Unit tests for AI Engine."""

import pytest
from unittest.mock import MagicMock, patch
from src.ai_engine import AIEngine
from src.models import BucketReport, DiagnosticResult, CheckStatus, Severity


class TestAIEngine:
    def test_init_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            engine = AIEngine(api_key=None)
            # It may pick up env, but if not:
            # We test the is_available method
            if not engine.api_key:
                assert not engine.is_available()

    def test_init_with_key(self):
        engine = AIEngine(api_key="test-key-123")
        assert engine.is_available()

    def test_analyze_report_no_key(self):
        engine = AIEngine(api_key=None)
        engine.client = None  # Force unavailable
        report = BucketReport(bucket_name="test", region="us-east-1")
        result = engine.analyze_report(report)
        assert "unavailable" in result["analysis"].lower()

    def test_troubleshoot_no_key(self):
        engine = AIEngine(api_key=None)
        engine.client = None
        result = engine.troubleshoot_issue("test issue", "test-bucket")
        assert "unavailable" in result.lower()
