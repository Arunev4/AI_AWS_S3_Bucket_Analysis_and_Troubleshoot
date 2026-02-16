"""Tests for diagnostics."""

import json
import pytest
from unittest.mock import MagicMock
from src.diagnostics import S3Diagnostics
from src.aws_client import S3Client
from src.models import CheckStatus, Severity, DiagnosticResult, BucketReport


@pytest.fixture
def mock_s3():
    c = MagicMock(spec=S3Client)
    c.region = "us-east-1"
    return c


@pytest.fixture
def diag(mock_s3):
    return S3Diagnostics(mock_s3)


class TestBucketExists:
    def test_exists_accessible(self, diag, mock_s3):
        mock_s3.bucket_exists.return_value = {"exists": True, "accessible": True}
        r = diag.check_bucket_exists("b")
        assert r.status == CheckStatus.PASS

    def test_access_denied(self, diag, mock_s3):
        mock_s3.bucket_exists.return_value = {"exists": True, "accessible": False}
        r = diag.check_bucket_exists("b")
        assert r.status == CheckStatus.FAIL
        assert "ACCESS DENIED" in r.message

    def test_not_found(self, diag, mock_s3):
        mock_s3.bucket_exists.return_value = {"exists": False, "accessible": False}
        r = diag.check_bucket_exists("b")
        assert r.status == CheckStatus.FAIL
        assert "NOT exist" in r.message


class TestEncryption:
    def test_enabled(self, diag, mock_s3):
        mock_s3.get_bucket_encryption.return_value = {"enabled": True, "rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}
        r = diag.check_encryption("b")
        assert r.status == CheckStatus.PASS
        assert "AES256" in r.message

    def test_disabled(self, diag, mock_s3):
        mock_s3.get_bucket_encryption.return_value = {"enabled": False, "rules": []}
        r = diag.check_encryption("b")
        assert r.status == CheckStatus.FAIL
        assert r.auto_fixable is True


class TestPublicAccess:
    def test_all_blocked(self, diag, mock_s3):
        mock_s3.get_public_access_block.return_value = {"exists": True, "config": {"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True}}
        r = diag.check_public_access("b")
        assert r.status == CheckStatus.PASS

    def test_no_config(self, diag, mock_s3):
        mock_s3.get_public_access_block.return_value = {"exists": False, "config": None}
        r = diag.check_public_access("b")
        assert r.status == CheckStatus.FAIL
        assert r.severity == Severity.CRITICAL
        assert r.auto_fixable is True

    def test_partial(self, diag, mock_s3):
        mock_s3.get_public_access_block.return_value = {"exists": True, "config": {"BlockPublicAcls": True, "IgnorePublicAcls": False, "BlockPublicPolicy": True, "RestrictPublicBuckets": False}}
        r = diag.check_public_access("b")
        assert r.status == CheckStatus.FAIL


class TestVersioning:
    def test_enabled(self, diag, mock_s3):
        mock_s3.get_bucket_versioning.return_value = {"status": "Enabled"}
        r = diag.check_versioning("b")
        assert r.status == CheckStatus.PASS

    def test_suspended(self, diag, mock_s3):
        mock_s3.get_bucket_versioning.return_value = {"status": "Suspended"}
        r = diag.check_versioning("b")
        assert r.status == CheckStatus.WARNING

    def test_disabled(self, diag, mock_s3):
        mock_s3.get_bucket_versioning.return_value = {"status": "Disabled"}
        r = diag.check_versioning("b")
        assert r.status == CheckStatus.FAIL
        assert r.auto_fixable is True


class TestPolicy:
    def test_no_policy(self, diag, mock_s3):
        mock_s3.get_bucket_policy.return_value = {"exists": False, "policy": None}
        r = diag.check_bucket_policy("b")
        assert r.status == CheckStatus.WARNING

    def test_secure(self, diag, mock_s3):
        p = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::123:root"}, "Action": ["s3:GetObject"], "Resource": "*"}]}
        mock_s3.get_bucket_policy.return_value = {"exists": True, "policy": json.dumps(p)}
        r = diag.check_bucket_policy("b")
        assert r.status == CheckStatus.PASS

    def test_open(self, diag, mock_s3):
        p = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:*", "Resource": "*"}]}
        mock_s3.get_bucket_policy.return_value = {"exists": True, "policy": json.dumps(p)}
        r = diag.check_bucket_policy("b")
        assert r.status == CheckStatus.FAIL
        assert r.severity == Severity.CRITICAL


class TestACL:
    def test_private(self, diag, mock_s3):
        mock_s3.get_bucket_acl.return_value = {"success": True, "owner": {}, "grants": [{"Grantee": {"Type": "CanonicalUser", "ID": "x"}, "Permission": "FULL_CONTROL"}]}
        r = diag.check_acl_permissions("b")
        assert r.status == CheckStatus.PASS

    def test_public(self, diag, mock_s3):
        mock_s3.get_bucket_acl.return_value = {"success": True, "owner": {}, "grants": [{"Grantee": {"Type": "Group", "URI": "http://acs.amazonaws.com/groups/global/AllUsers"}, "Permission": "READ"}]}
        r = diag.check_acl_permissions("b")
        assert r.status == CheckStatus.FAIL


class TestLogging:
    def test_on(self, diag, mock_s3):
        mock_s3.get_bucket_logging.return_value = {"enabled": True, "config": {}}
        assert diag.check_logging("b").status == CheckStatus.PASS

    def test_off(self, diag, mock_s3):
        mock_s3.get_bucket_logging.return_value = {"enabled": False}
        assert diag.check_logging("b").status == CheckStatus.WARNING


class TestLifecycle:
    def test_exists(self, diag, mock_s3):
        mock_s3.get_lifecycle_rules.return_value = {"exists": True, "rules": [{"Status": "Enabled"}]}
        assert diag.check_lifecycle("b").status == CheckStatus.PASS

    def test_none(self, diag, mock_s3):
        mock_s3.get_lifecycle_rules.return_value = {"exists": False, "rules": []}
        assert diag.check_lifecycle("b").status == CheckStatus.WARNING


class TestModels:
    def test_to_dict(self):
        r = DiagnosticResult("T", CheckStatus.PASS, Severity.LOW, "ok")
        d = r.to_dict()
        assert d["status"] == "PASS"

    def test_score_mixed(self):
        rpt = BucketReport("t", "us-east-1")
        rpt.add_result(DiagnosticResult("a", CheckStatus.PASS, Severity.HIGH, "ok"))
        rpt.add_result(DiagnosticResult("b", CheckStatus.FAIL, Severity.LOW, "bad"))
        rpt.calculate_score()
        assert 0 < rpt.score < 100

    def test_all_pass(self):
        rpt = BucketReport("t", "us-east-1")
        rpt.add_result(DiagnosticResult("a", CheckStatus.PASS, Severity.HIGH, "ok"))
        rpt.calculate_score()
        assert rpt.score == 100

    def test_all_fail(self):
        rpt = BucketReport("t", "us-east-1")
        rpt.add_result(DiagnosticResult("a", CheckStatus.FAIL, Severity.HIGH, "bad"))
        rpt.calculate_score()
        assert rpt.score == 0

    def test_empty(self):
        rpt = BucketReport("t", "us-east-1")
        rpt.calculate_score()
        assert rpt.score == 0
        assert rpt.overall_health == "UNKNOWN"

    def test_report_dict(self):
        rpt = BucketReport("t", "us-east-1")
        rpt.add_result(DiagnosticResult("a", CheckStatus.PASS, Severity.LOW, "ok"))
        d = rpt.to_dict()
        assert d["total_checks"] == 1
        assert d["passed"] == 1
