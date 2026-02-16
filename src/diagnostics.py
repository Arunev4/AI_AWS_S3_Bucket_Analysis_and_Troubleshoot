"""S3 diagnostic checks."""

import json
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from src.aws_client import S3Client
from src.models import DiagnosticResult, BucketReport, Severity, CheckStatus

console = Console()


class S3Diagnostics:
    def __init__(self, s3_client):
        self.s3 = s3_client

    def run_all_checks(self, bucket_name):
        region = self.s3.get_bucket_location(bucket_name) or self.s3.region
        report = BucketReport(bucket_name=bucket_name, region=region)
        checks = [
            ("Bucket Existence & Access", self.check_bucket_exists),
            ("Bucket Policy", self.check_bucket_policy),
            ("Public Access Block", self.check_public_access),
            ("ACL Permissions", self.check_acl_permissions),
            ("Server-Side Encryption", self.check_encryption),
            ("Versioning", self.check_versioning),
            ("Lifecycle Rules", self.check_lifecycle),
            ("CORS Configuration", self.check_cors),
            ("Access Logging", self.check_logging),
            ("Replication", self.check_replication),
            ("Object Lock", self.check_object_lock),
            ("Transfer Acceleration", self.check_transfer_acceleration),
            ("Bucket Tagging", self.check_tagging),
            ("Bucket Size", self.check_bucket_size),
        ]
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Running...", total=len(checks))
            for name, func in checks:
                progress.update(task, description="Checking: " + name)
                try:
                    report.add_result(func(bucket_name))
                except Exception as e:
                    report.add_result(DiagnosticResult(name, CheckStatus.ERROR, Severity.MEDIUM, str(e)))
                progress.advance(task)
        report.scan_end = datetime.utcnow().isoformat()
        report.calculate_score()
        return report

    def check_bucket_exists(self, bucket_name):
        r = self.s3.bucket_exists(bucket_name)
        if r.get("exists") and r.get("accessible"):
            return DiagnosticResult("Bucket Existence & Access", CheckStatus.PASS, Severity.CRITICAL, "Bucket '" + bucket_name + "' exists and is accessible.", r)
        elif r.get("exists"):
            return DiagnosticResult("Bucket Existence & Access", CheckStatus.FAIL, Severity.CRITICAL, "Bucket '" + bucket_name + "' exists but ACCESS DENIED.", r, "Check IAM policies.")
        return DiagnosticResult("Bucket Existence & Access", CheckStatus.FAIL, Severity.CRITICAL, "Bucket '" + bucket_name + "' does NOT exist.", r, "Verify bucket name.")

    def check_bucket_policy(self, bucket_name):
        r = self.s3.get_bucket_policy(bucket_name)
        if not r.get("exists"):
            return DiagnosticResult("Bucket Policy", CheckStatus.WARNING, Severity.LOW, "No bucket policy.", r, "Consider adding one.")
        try:
            policy = json.loads(r["policy"])
            issues = []
            for st in policy.get("Statement", []):
                p = st.get("Principal", "")
                e = st.get("Effect", "")
                a = st.get("Action", "")
                if e == "Allow" and (p == "*" or p == {"AWS": "*"}):
                    issues.append({"type": "OPEN_ACCESS", "severity": "CRITICAL"})
                if isinstance(a, str) and a == "s3:*":
                    issues.append({"type": "WILDCARD", "severity": "HIGH"})
            if issues:
                crit = any(i["severity"] == "CRITICAL" for i in issues)
                return DiagnosticResult("Bucket Policy", CheckStatus.FAIL if crit else CheckStatus.WARNING, Severity.CRITICAL if crit else Severity.HIGH, str(len(issues)) + " issue(s).", {"policy": policy, "issues": issues}, "Tighten policy.")
            return DiagnosticResult("Bucket Policy", CheckStatus.PASS, Severity.HIGH, "Policy looks good.", {"policy": policy})
        except json.JSONDecodeError:
            return DiagnosticResult("Bucket Policy", CheckStatus.ERROR, Severity.HIGH, "Parse error.", r)

    def check_public_access(self, bucket_name):
        r = self.s3.get_public_access_block(bucket_name)
        if not r.get("exists"):
            return DiagnosticResult("Public Access Block", CheckStatus.FAIL, Severity.CRITICAL, "No Public Access Block!", r, "Enable all settings.", True, "Enable all Public Access Block settings.")
        c = r["config"]
        if all([c.get("BlockPublicAcls", False), c.get("IgnorePublicAcls", False), c.get("BlockPublicPolicy", False), c.get("RestrictPublicBuckets", False)]):
            return DiagnosticResult("Public Access Block", CheckStatus.PASS, Severity.CRITICAL, "All blocked.", {"config": c})
        d = [k for k, v in c.items() if not v]
        return DiagnosticResult("Public Access Block", CheckStatus.FAIL, Severity.CRITICAL, "Incomplete: " + str(d), {"config": c}, "Enable: " + str(d), True, "Fix public access.")

    def check_acl_permissions(self, bucket_name):
        r = self.s3.get_bucket_acl(bucket_name)
        if not r.get("success"):
            return DiagnosticResult("ACL Permissions", CheckStatus.ERROR, Severity.HIGH, "Cannot get ACL.", r)
        issues = []
        for g in r["grants"]:
            uri = g.get("Grantee", {}).get("URI", "")
            if "AllUsers" in uri:
                issues.append("PUBLIC: " + g.get("Permission", ""))
            elif "AuthenticatedUsers" in uri:
                issues.append("AUTH_USERS: " + g.get("Permission", ""))
        if issues:
            return DiagnosticResult("ACL Permissions", CheckStatus.FAIL, Severity.CRITICAL, str(len(issues)) + " bad grant(s).", {"grants": r["grants"], "issues": issues}, "Remove public grants.")
        return DiagnosticResult("ACL Permissions", CheckStatus.PASS, Severity.HIGH, "ACL OK.", {"grants": r["grants"]})

    def check_encryption(self, bucket_name):
        r = self.s3.get_bucket_encryption(bucket_name)
        if r.get("enabled"):
            algo = r["rules"][0].get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm", "Unknown")
            return DiagnosticResult("Server-Side Encryption", CheckStatus.PASS, Severity.HIGH, "Encryption enabled with " + algo + ".", r)
        return DiagnosticResult("Server-Side Encryption", CheckStatus.FAIL, Severity.HIGH, "Encryption NOT enabled.", r, "Enable encryption.", True, "Enable AES-256.")

    def check_versioning(self, bucket_name):
        r = self.s3.get_bucket_versioning(bucket_name)
        s = r.get("status", "Disabled")
        if s == "Enabled":
            return DiagnosticResult("Versioning", CheckStatus.PASS, Severity.MEDIUM, "Versioning enabled.", r)
        if s == "Suspended":
            return DiagnosticResult("Versioning", CheckStatus.WARNING, Severity.MEDIUM, "Versioning SUSPENDED.", r, "Re-enable.", True, "Enable versioning.")
        return DiagnosticResult("Versioning", CheckStatus.FAIL, Severity.MEDIUM, "Versioning NOT enabled.", r, "Enable versioning.", True, "Enable versioning.")

    def check_lifecycle(self, bucket_name):
        r = self.s3.get_lifecycle_rules(bucket_name)
        if r.get("exists") and r.get("rules"):
            en = [x for x in r["rules"] if x.get("Status") == "Enabled"]
            return DiagnosticResult("Lifecycle Rules", CheckStatus.PASS, Severity.LOW, str(len(en)) + " active rule(s).", r)
        return DiagnosticResult("Lifecycle Rules", CheckStatus.WARNING, Severity.LOW, "No lifecycle rules.", r, "Add lifecycle rules.")

    def check_cors(self, bucket_name):
        r = self.s3.get_cors_configuration(bucket_name)
        if not r.get("exists"):
            return DiagnosticResult("CORS Configuration", CheckStatus.PASS, Severity.INFO, "No CORS.", r)
        issues = [i for i, rule in enumerate(r["rules"]) if "*" in rule.get("AllowedOrigins", [])]
        if issues:
            return DiagnosticResult("CORS Configuration", CheckStatus.WARNING, Severity.MEDIUM, "Wildcard origin.", r, "Restrict origins.")
        return DiagnosticResult("CORS Configuration", CheckStatus.PASS, Severity.LOW, "CORS OK.", r)

    def check_logging(self, bucket_name):
        r = self.s3.get_bucket_logging(bucket_name)
        if r.get("enabled"):
            return DiagnosticResult("Access Logging", CheckStatus.PASS, Severity.MEDIUM, "Logging enabled.", r)
        return DiagnosticResult("Access Logging", CheckStatus.WARNING, Severity.MEDIUM, "Logging NOT enabled.", r, "Enable logging.", True, "Enable logging.")

    def check_replication(self, bucket_name):
        r = self.s3.get_bucket_replication(bucket_name)
        if r.get("enabled"):
            return DiagnosticResult("Replication", CheckStatus.PASS, Severity.INFO, "Replication configured.", r)
        return DiagnosticResult("Replication", CheckStatus.INFO, Severity.INFO, "No replication.", r)

    def check_object_lock(self, bucket_name):
        r = self.s3.get_object_lock_configuration(bucket_name)
        if r.get("enabled"):
            return DiagnosticResult("Object Lock", CheckStatus.PASS, Severity.INFO, "Object Lock enabled.", r)
        return DiagnosticResult("Object Lock", CheckStatus.INFO, Severity.INFO, "No Object Lock.", r)

    def check_transfer_acceleration(self, bucket_name):
        r = self.s3.get_transfer_acceleration(bucket_name)
        return DiagnosticResult("Transfer Acceleration", CheckStatus.INFO, Severity.INFO, "Accel: " + r.get("status", "Unknown"), r)

    def check_tagging(self, bucket_name):
        r = self.s3.get_bucket_tagging(bucket_name)
        if r.get("exists") and r.get("tags"):
            return DiagnosticResult("Bucket Tagging", CheckStatus.PASS, Severity.LOW, str(len(r["tags"])) + " tag(s).", r)
        return DiagnosticResult("Bucket Tagging", CheckStatus.WARNING, Severity.LOW, "No tags.", r, "Add tags.")

    def check_bucket_size(self, bucket_name):
        r = self.s3.get_bucket_size_estimate(bucket_name)
        if r.get("success"):
            return DiagnosticResult("Bucket Size", CheckStatus.INFO, Severity.INFO, str(r["object_count"]) + " objects, " + str(r["total_size_mb"]) + " MB.", r)
        return DiagnosticResult("Bucket Size", CheckStatus.ERROR, Severity.INFO, "Cannot get size.", r)
