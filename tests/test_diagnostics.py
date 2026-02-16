"""Unit tests for diagnostics module."""

import pytest
from unittest.mock import MagicMock, patch
from src.diagnostics import S3Diagnostics
from src.aws_client import S3Client
from src.models import CheckStatus, Severity


@pytest.fixture
def mock_s3_client():
    """Create a mock S3 client."""
    client = MagicMock(spec=S3Client)
    client.region = "us-east-1"
    return client


@pytest.fixture
def diagnostics(mock_s3_client):
    """Create diagnostics instance with mocked client."""
    return S3Diagnostics(mock_s3_client)


class TestBucketExists:
    def test_bucket_exists_and_accessible(self, diagnostics, mock_s3_client):
        mock_s3_client.bucket_exists.return_value = {"exists": True, "accessible": True}
        result = diagnostics.check_bucket_exists("test-bucket")
        assert result.status == CheckStatus.PASS
        assert result.severity == Severity.CRITICAL

    def test_bucket_exists_access_denied(self, diagnostics, mock_s3_client):
        mock_s3_client.bucket_exists.return_value = {
            "exists": True,
            "accessible": False,
            "error": "Access denied",
        }
        result = diagnostics.check_bucket_exists("test-bucket")
        assert result.status == CheckStatus.FAIL
        assert result.severity == Severity.CRITICAL
        assert "ACCESS DENIED" in result.message

    def test_bucket_not_found(self, diagnostics, mock_s3_client):
        mock_s3_client.bucket_exists.return_value = {
            "exists": False,
            "accessible": False,
            "error": "Bucket not found",
        }
        result = diagnostics.check_bucket_exists("test-bucket")
        assert result.status == CheckStatus.FAIL


class TestEncryptionCheck:
    def test_encryption_enabled(self, diagnostics, mock_s3_client):
        mock_s3_client.get_bucket_encryption.return_value = {
            "enabled": True,
            "rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ],
        }
        result = diagnostics.check_encryption("test-bucket")
        assert result.status == CheckStatus.PASS
        assert "AES256" in result.message

    def test_encryption_disabled(self, diagnostics, mock_s3_client):
        mock_s3_client.get_bucket_encryption.return_value = {
            "enabled": False,
            "rules": [],
        }
        result = diagnostics.check_encryption("test-bucket")
        assert result.status == CheckStatus.FAIL
        assert result.auto_fixable is True


class TestPublicAccess:
    def test_all_blocked(self, diagnostics, mock_s3_client):
        mock_s3_client.get_public_access_block.return_value = {
            "exists": True,
            "config": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        }
        result = diagnostics.check_public_access("test-bucket")
        assert result.status == CheckStatus.PASS

    def test_no_public_access_block(self, diagnostics, mock_s3_client):
        mock_s3_client.get_public_access_block.return_value = {
            "exists": False,
            "config": None,
        }
        result = diagnostics.check_public_access("test-bucket")
        assert result.status == CheckStatus.FAIL
        assert result.severity == Severity.CRITICAL
        assert result.auto_fixable is True

    def test_partial_block(self, diagnostics, mock_s3_client):
        mock_s3_client.get_public_access_block.return_value = {
            "exists": True,
            "config": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": False,
            },
        }
        result = diagnostics.check_public_access("test-bucket")
        assert result.status == CheckStatus.FAIL


class TestVersioning:
    def test_versioning_enabled(self, diagnostics, mock_s3_client):
        mock_s3_client.get_bucket_versioning.return_value = {
            "status": "Enabled",
            "mfa_delete": "Disabled",
        }
        result = diagnostics.check_versioning("test-bucket")
        assert result.status == CheckStatus.PASS

    def test_versioning_suspended(self, diagnostics, mock_s3_client):
        mock_s3_client.get_bucket_versioning.return_value = {
            "status": "Suspended",
            "mfa_delete": "Disabled",
        }
        result = diagnostics.check_versioning("test-bucket")
        assert result.status == CheckStatus.WARNING

    def test_versioning_disabled(self, diagnostics, mock_s3_client):
        mock_s3_client.get_bucket_versioning.return_value = {
            "status": "Disabled",
        }
        result = diagnostics.check_versioning("test-bucket")
        assert result.status == CheckStatus.FAIL
        assert result.auto_fixable is True


class TestBucketPolicy:
    def test_no_policy(self, diagnostics, mock_s3_client):
        mock_s3_client.get_bucket_policy.return_value = {
            "exists": False,
            "policy": None,
        }
        result = diagnostics.check_bucket_policy("test-bucket")
        assert result.status == CheckStatus.WARNING

    def test_secure_policy(self, diagnostics, mock_s3_client):
        import json

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "arn:aws:iam::123456789012:root"},
                    "Action": ["s3:GetObject"],
                    "Resource": "arn:aws:s3:::test-bucket/*",
                }
            ],
        }
        mock_s3_client.get_bucket_policy.return_value = {
            "exists": True,
            "policy": json.dumps(policy),
        }
        result = diagnostics.check_bucket_policy("test-bucket")
        assert result.status == CheckStatus.PASS

    def test_open_policy(self, diagnostics, mock_s3_client):
        import json

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": "arn:aws:s3:::test-bucket/*",
                }
            ],
        }
        mock_s3_client.get_bucket_policy.return_value = {
            "exists": True,
            "policy": json.dumps(policy),
        }
        result = diagnostics.check_bucket_policy("test-bucket")
        assert result.status == CheckStatus.FAIL
        assert result.severity == Severity.CRITICAL


class TestModels:
    def test_diagnostic_result_to_dict(self):
        from src.models import DiagnosticResult

        result = DiagnosticResult(
            check_name="Test",
            status=CheckStatus.PASS,
            severity=Severity.LOW,
            message="Test passed",
        )
        d = result.to_dict()
        assert d["check_name"] == "Test"
        assert d["status"] == "PASS"

    def test_bucket_report_score(self):
        from src.models import BucketReport, DiagnosticResult

        report = BucketReport(bucket_name="test", region="us-east-1")
        report.add_result(DiagnosticResult("c1", CheckStatus.PASS, Severity.HIGH, "ok"))
        report.add_result(DiagnosticResult("c2", CheckStatus.PASS, Severity.HIGH, "ok"))
        report.add_result(
            DiagnosticResult("c3", CheckStatus.FAIL, Severity.LOW, "fail")
        )
        report.calculate_score()
        assert 0 < report.score <= 100
