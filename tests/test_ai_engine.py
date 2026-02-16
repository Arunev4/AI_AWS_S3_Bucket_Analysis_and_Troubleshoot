"""Tests for AI Engine."""

import pytest
from src.ai_engine import AIEngine
from src.models import BucketReport, DiagnosticResult, CheckStatus, Severity


class TestInit:
    def test_no_key(self):
        e = AIEngine(api_key=None, provider="none")
        e.client = None
        assert not e.is_available()

    def test_with_key(self):
        e = AIEngine(api_key="test-123", provider="openai")
        assert e.is_available()


class TestAnalysis:
    def test_no_key_analyze(self):
        e = AIEngine(api_key=None, provider="none")
        e.client = None
        r = e.analyze_report(BucketReport("t", "us-east-1"))
        assert "unavailable" in r["analysis"].lower()

    def test_no_key_troubleshoot(self):
        e = AIEngine(api_key=None, provider="none")
        e.client = None
        assert "unavailable" in e.troubleshoot_issue("x", "b").lower()

    def test_no_key_policy(self):
        e = AIEngine(api_key=None, provider="none")
        e.client = None
        assert "unavailable" in e.generate_policy_recommendation("b", "web").lower()


class TestPrompts:
    def test_system(self):
        e = AIEngine(api_key=None, provider="none")
        assert len(e._get_system_prompt()) > 20

    def test_analysis_prompt(self):
        e = AIEngine(api_key=None, provider="none")
        rpt = BucketReport("my-bucket", "eu-west-1")
        rpt.add_result(DiagnosticResult("c", CheckStatus.PASS, Severity.LOW, "ok"))
        p = e._build_analysis_prompt(rpt)
        assert "my-bucket" in p
        assert "eu-west-1" in p
