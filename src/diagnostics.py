"""Comprehensive S3 diagnostic checks."""

import json
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.aws_client import S3Client
from src.models import DiagnosticResult, BucketReport, Severity, CheckStatus

console = Console()


class S3Diagnostics:
    """Runs all diagnostic checks against an S3 bucket."""

    def __init__(self, s3_client: S3Client):
        self.s3 = s3_client

    def run_all_checks(self, bucket_name: str) -> BucketReport:
        """Run all diagnostic checks and return a complete report."""
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

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running diagnostics...", total=len(checks))

            for check_name, check_func in checks:
                progress.update(task, description=f"Checking: {check_name}...")
                try:
                    result = check_func(bucket_name)
                    report.add_result(result)
                except Exception as e:
                    report.add_result(
                        DiagnosticResult(
                            check_name=check_name,
                            status=CheckStatus.ERROR,
                            severity=Severity.MEDIUM,
                            message=f"Check failed with error: {str(e)}",
                            details={"exception": str(e)},
                        )
                    )
                progress.advance(task)

        from datetime import datetime

        report.scan_end = datetime.utcnow().isoformat()
        report.calculate_score()
        return report

    # ------------------------------------------------------------------ #
    #                     INDIVIDUAL CHECK METHODS                        #
    # ------------------------------------------------------------------ #

    def check_bucket_exists(self, bucket_name: str) -> DiagnosticResult:
        """Check if the bucket exists and is accessible."""
        result = self.s3.bucket_exists(bucket_name)

        if result.get("exists") and result.get("accessible"):
            return DiagnosticResult(
                check_name="Bucket Existence & Access",
                status=CheckStatus.PASS,
                severity=Severity.CRITICAL,
                message=f"Bucket '{bucket_name}' exists and is accessible.",
                details=result,
            )
        elif result.get("exists") and not result.get("accessible"):
            return DiagnosticResult(
                check_name="Bucket Existence & Access",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message=f"Bucket '{bucket_name}' exists but ACCESS DENIED.",
                details=result,
                recommendation="Check IAM policies. Ensure your user/role has s3:ListBucket, "
                "s3:GetBucketLocation permissions. Check bucket policy for explicit denies.",
            )
        else:
            return DiagnosticResult(
                check_name="Bucket Existence & Access",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message=f"Bucket '{bucket_name}' does NOT exist.",
                details=result,
                recommendation="Verify the bucket name (case-sensitive, globally unique). "
                "Check for typos. The bucket may have been deleted.",
            )

    def check_bucket_policy(self, bucket_name: str) -> DiagnosticResult:
        """Analyze bucket policy for security issues."""
        result = self.s3.get_bucket_policy(bucket_name)

        if not result.get("exists"):
            return DiagnosticResult(
                check_name="Bucket Policy",
                status=CheckStatus.WARNING,
                severity=Severity.LOW,
                message="No bucket policy is configured.",
                details=result,
                recommendation="Consider adding a bucket policy to explicitly define access controls.",
            )

        # Parse and analyze the policy
        try:
            policy = json.loads(result["policy"])
            issues = []
            details = {"policy": policy, "issues": issues}

            for statement in policy.get("Statement", []):
                principal = statement.get("Principal", "")
                effect = statement.get("Effect", "")
                action = statement.get("Action", "")

                # Check for wildcard principal with Allow
                if effect == "Allow" and (
                    principal == "*" or principal == {"AWS": "*"}
                ):
                    issues.append(
                        {
                            "type": "OPEN_ACCESS",
                            "severity": "CRITICAL",
                            "detail": f"Statement allows access to everyone (*). Actions: {action}",
                        }
                    )

                # Check for overly permissive actions
                if isinstance(action, str) and action == "s3:*":
                    issues.append(
                        {
                            "type": "WILDCARD_ACTIONS",
                            "severity": "HIGH",
                            "detail": "Statement uses wildcard action s3:* — overly permissive.",
                        }
                    )

                # Check for missing conditions on sensitive actions
                sensitive_actions = [
                    "s3:DeleteBucket",
                    "s3:DeleteObject",
                    "s3:PutBucketPolicy",
                ]
                if isinstance(action, list):
                    for a in action:
                        if a in sensitive_actions and "Condition" not in statement:
                            issues.append(
                                {
                                    "type": "MISSING_CONDITION",
                                    "severity": "MEDIUM",
                                    "detail": f"Sensitive action '{a}' has no Condition block.",
                                }
                            )

            if issues:
                critical = any(i["severity"] == "CRITICAL" for i in issues)
                return DiagnosticResult(
                    check_name="Bucket Policy",
                    status=CheckStatus.FAIL if critical else CheckStatus.WARNING,
                    severity=Severity.CRITICAL if critical else Severity.HIGH,
                    message=f"Bucket policy has {len(issues)} issue(s).",
                    details=details,
                    recommendation="Review and tighten bucket policy. Remove wildcard principals, "
                    "restrict actions, and add conditions.",
                )

            return DiagnosticResult(
                check_name="Bucket Policy",
                status=CheckStatus.PASS,
                severity=Severity.HIGH,
                message="Bucket policy exists and appears properly configured.",
                details=details,
            )

        except json.JSONDecodeError:
            return DiagnosticResult(
                check_name="Bucket Policy",
                status=CheckStatus.ERROR,
                severity=Severity.HIGH,
                message="Failed to parse bucket policy JSON.",
                details=result,
            )

    def check_public_access(self, bucket_name: str) -> DiagnosticResult:
        """Check Public Access Block configuration."""
        result = self.s3.get_public_access_block(bucket_name)

        if not result.get("exists"):
            return DiagnosticResult(
                check_name="Public Access Block",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message="No Public Access Block configuration found! Bucket may be publicly accessible.",
                details=result,
                recommendation="Enable all four Public Access Block settings immediately.",
                auto_fixable=True,
                fix_description="Enable BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets.",
            )

        config = result["config"]
        all_blocked = all(
            [
                config.get("BlockPublicAcls", False),
                config.get("IgnorePublicAcls", False),
                config.get("BlockPublicPolicy", False),
                config.get("RestrictPublicBuckets", False),
            ]
        )

        if all_blocked:
            return DiagnosticResult(
                check_name="Public Access Block",
                status=CheckStatus.PASS,
                severity=Severity.CRITICAL,
                message="All public access is blocked.",
                details={"config": config},
            )

        disabled_settings = [k for k, v in config.items() if not v]
        return DiagnosticResult(
            check_name="Public Access Block",
            status=CheckStatus.FAIL,
            severity=Severity.CRITICAL,
            message=f"Public access block is INCOMPLETE. Disabled: {disabled_settings}",
            details={"config": config, "disabled": disabled_settings},
            recommendation=f"Enable these settings: {disabled_settings}",
            auto_fixable=True,
            fix_description="Set all Public Access Block settings to True.",
        )

    def check_acl_permissions(self, bucket_name: str) -> DiagnosticResult:
        """Check ACL for overly permissive grants."""
        result = self.s3.get_bucket_acl(bucket_name)

        if not result.get("success"):
            return DiagnosticResult(
                check_name="ACL Permissions",
                status=CheckStatus.ERROR,
                severity=Severity.HIGH,
                message=f"Could not retrieve ACL: {result.get('error')}",
                details=result,
            )

        grants = result["grants"]
        issues = []

        for grant in grants:
            grantee = grant.get("Grantee", {})
            permission = grant.get("Permission", "")
            grantee_uri = grantee.get("URI", "")

            # Check for public access via ACL
            if "AllUsers" in grantee_uri:
                issues.append(
                    {
                        "type": "PUBLIC_ACL",
                        "grantee": "Everyone (AllUsers)",
                        "permission": permission,
                    }
                )
            elif "AuthenticatedUsers" in grantee_uri:
                issues.append(
                    {
                        "type": "AUTHENTICATED_USERS_ACL",
                        "grantee": "All AWS Authenticated Users",
                        "permission": permission,
                    }
                )

        if issues:
            return DiagnosticResult(
                check_name="ACL Permissions",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message=f"ACL has {len(issues)} overly permissive grant(s).",
                details={"grants": grants, "issues": issues},
                recommendation="Remove public ACL grants. Use bucket policies for access control instead.",
            )

        return DiagnosticResult(
            check_name="ACL Permissions",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="ACL permissions look correct.",
            details={"grants": grants},
        )

    def check_encryption(self, bucket_name: str) -> DiagnosticResult:
        """Check server-side encryption configuration."""
        result = self.s3.get_bucket_encryption(bucket_name)

        if result.get("enabled"):
            rules = result["rules"]
            algo = (
                rules[0]
                .get("ApplyServerSideEncryptionByDefault", {})
                .get("SSEAlgorithm", "Unknown")
            )
            return DiagnosticResult(
                check_name="Server-Side Encryption",
                status=CheckStatus.PASS,
                severity=Severity.HIGH,
                message=f"Encryption enabled with {algo}.",
                details={"rules": rules, "algorithm": algo},
            )

        return DiagnosticResult(
            check_name="Server-Side Encryption",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message="Server-side encryption is NOT enabled.",
            details=result,
            recommendation="Enable default encryption (AES-256 or aws:kms).",
            auto_fixable=True,
            fix_description="Enable AES-256 default encryption.",
        )

    def check_versioning(self, bucket_name: str) -> DiagnosticResult:
        """Check versioning status."""
        result = self.s3.get_bucket_versioning(bucket_name)
        status = result.get("status", "Disabled")

        if status == "Enabled":
            return DiagnosticResult(
                check_name="Versioning",
                status=CheckStatus.PASS,
                severity=Severity.MEDIUM,
                message="Versioning is enabled.",
                details=result,
            )
        elif status == "Suspended":
            return DiagnosticResult(
                check_name="Versioning",
                status=CheckStatus.WARNING,
                severity=Severity.MEDIUM,
                message="Versioning is SUSPENDED. Previously versioned objects remain, but new versions won't be created.",
                details=result,
                recommendation="Re-enable versioning for data protection.",
                auto_fixable=True,
                fix_description="Enable bucket versioning.",
            )
        else:
            return DiagnosticResult(
                check_name="Versioning",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message="Versioning is NOT enabled.",
                details=result,
                recommendation="Enable versioning to protect against accidental deletes and overwrites.",
                auto_fixable=True,
                fix_description="Enable bucket versioning.",
            )

    def check_lifecycle(self, bucket_name: str) -> DiagnosticResult:
        """Check lifecycle rules."""
        result = self.s3.get_lifecycle_rules(bucket_name)

        if result.get("exists") and result.get("rules"):
            rules = result["rules"]
            enabled_rules = [r for r in rules if r.get("Status") == "Enabled"]
            return DiagnosticResult(
                check_name="Lifecycle Rules",
                status=CheckStatus.PASS,
                severity=Severity.LOW,
                message=f"{len(enabled_rules)} active lifecycle rule(s) configured.",
                details={
                    "total_rules": len(rules),
                    "enabled_rules": len(enabled_rules),
                },
            )

        return DiagnosticResult(
            check_name="Lifecycle Rules",
            status=CheckStatus.WARNING,
            severity=Severity.LOW,
            message="No lifecycle rules configured.",
            details=result,
            recommendation="Add lifecycle rules to manage storage costs "
            "(e.g., transition to Glacier, expire old objects).",
        )

    def check_cors(self, bucket_name: str) -> DiagnosticResult:
        """Check CORS configuration for security issues."""
        result = self.s3.get_cors_configuration(bucket_name)

        if not result.get("exists"):
            return DiagnosticResult(
                check_name="CORS Configuration",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="No CORS configuration (fine if not serving web content).",
                details=result,
            )

        rules = result["rules"]
        issues = []

        for i, rule in enumerate(rules):
            origins = rule.get("AllowedOrigins", [])
            methods = rule.get("AllowedMethods", [])

            if "*" in origins:
                issues.append(
                    {
                        "rule_index": i,
                        "type": "WILDCARD_ORIGIN",
                        "detail": "Allows requests from any origin (*)",
                    }
                )
            if "DELETE" in methods or "PUT" in methods:
                issues.append(
                    {
                        "rule_index": i,
                        "type": "WRITE_METHODS",
                        "detail": f"Allows write methods: {[m for m in methods if m in ('PUT', 'DELETE')]}",
                    }
                )

        if issues:
            return DiagnosticResult(
                check_name="CORS Configuration",
                status=CheckStatus.WARNING,
                severity=Severity.MEDIUM,
                message=f"CORS has {len(issues)} potential issue(s).",
                details={"rules": rules, "issues": issues},
                recommendation="Restrict CORS origins to specific domains. Avoid wildcard (*).",
            )

        return DiagnosticResult(
            check_name="CORS Configuration",
            status=CheckStatus.PASS,
            severity=Severity.LOW,
            message="CORS configuration looks properly scoped.",
            details={"rules": rules},
        )

    def check_logging(self, bucket_name: str) -> DiagnosticResult:
        """Check access logging."""
        result = self.s3.get_bucket_logging(bucket_name)

        if result.get("enabled"):
            return DiagnosticResult(
                check_name="Access Logging",
                status=CheckStatus.PASS,
                severity=Severity.MEDIUM,
                message="Access logging is enabled.",
                details=result,
            )

        return DiagnosticResult(
            check_name="Access Logging",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            message="Access logging is NOT enabled.",
            details=result,
            recommendation="Enable server access logging for audit and security monitoring.",
            auto_fixable=True,
            fix_description="Enable access logging to a target bucket.",
        )

    def check_replication(self, bucket_name: str) -> DiagnosticResult:
        """Check replication configuration."""
        result = self.s3.get_bucket_replication(bucket_name)

        if result.get("enabled"):
            return DiagnosticResult(
                check_name="Replication",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="Cross-region/same-region replication is configured.",
                details=result,
            )

        return DiagnosticResult(
            check_name="Replication",
            status=CheckStatus.INFO,
            severity=Severity.INFO,
            message="No replication configured (may be acceptable depending on requirements).",
            details=result,
            recommendation="Consider enabling replication for disaster recovery.",
        )

    def check_object_lock(self, bucket_name: str) -> DiagnosticResult:
        """Check Object Lock configuration."""
        result = self.s3.get_object_lock_configuration(bucket_name)

        if result.get("enabled"):
            return DiagnosticResult(
                check_name="Object Lock",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="Object Lock is enabled (WORM protection).",
                details=result,
            )

        return DiagnosticResult(
            check_name="Object Lock",
            status=CheckStatus.INFO,
            severity=Severity.INFO,
            message="Object Lock is not enabled.",
            details=result,
            recommendation="Enable Object Lock if you need WORM (Write Once Read Many) compliance.",
        )

    def check_transfer_acceleration(self, bucket_name: str) -> DiagnosticResult:
        """Check Transfer Acceleration status."""
        result = self.s3.get_transfer_acceleration(bucket_name)

        return DiagnosticResult(
            check_name="Transfer Acceleration",
            status=CheckStatus.INFO,
            severity=Severity.INFO,
            message=f"Transfer Acceleration: {result.get('status', 'Unknown')}",
            details=result,
        )

    def check_tagging(self, bucket_name: str) -> DiagnosticResult:
        """Check bucket tagging for governance."""
        result = self.s3.get_bucket_tagging(bucket_name)

        if result.get("exists") and result.get("tags"):
            tags = result["tags"]
            tag_keys = [t["Key"] for t in tags]

            recommended_tags = ["Environment", "Project", "Owner", "CostCenter"]
            missing = [t for t in recommended_tags if t not in tag_keys]

            if missing:
                return DiagnosticResult(
                    check_name="Bucket Tagging",
                    status=CheckStatus.WARNING,
                    severity=Severity.LOW,
                    message=f"Bucket has {len(tags)} tag(s) but missing recommended: {missing}",
                    details={"tags": tags, "missing_recommended": missing},
                    recommendation=f"Add these tags for governance: {missing}",
                )

            return DiagnosticResult(
                check_name="Bucket Tagging",
                status=CheckStatus.PASS,
                severity=Severity.LOW,
                message=f"Bucket has {len(tags)} tag(s) including recommended governance tags.",
                details={"tags": tags},
            )

        return DiagnosticResult(
            check_name="Bucket Tagging",
            status=CheckStatus.WARNING,
            severity=Severity.LOW,
            message="No tags configured.",
            details=result,
            recommendation="Add tags (Environment, Project, Owner, CostCenter) for governance.",
        )

    def check_bucket_size(self, bucket_name: str) -> DiagnosticResult:
        """Check bucket size and object count."""
        result = self.s3.get_bucket_size_estimate(bucket_name)

        if result.get("success"):
            return DiagnosticResult(
                check_name="Bucket Size",
                status=CheckStatus.INFO,
                severity=Severity.INFO,
                message=f"Bucket contains ~{result['object_count']} objects, "
                f"~{result['total_size_mb']} MB "
                f"{'(sampled)' if result['sampled'] else '(complete)'}.",
                details=result,
            )

        return DiagnosticResult(
            check_name="Bucket Size",
            status=CheckStatus.ERROR,
            severity=Severity.INFO,
            message=f"Could not determine bucket size: {result.get('error')}",
            details=result,
        )
