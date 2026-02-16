"""Auto-remediation engine."""

from rich.console import Console
from rich.prompt import Confirm
from src.aws_client import S3Client
from src.models import BucketReport, CheckStatus

console = Console()


class Remediator:
    def __init__(self, s3_client, auto_approve=False):
        self.s3 = s3_client
        self.auto_approve = auto_approve

    def remediate_all(self, report):
        fixable = [r for r in report.results if r.auto_fixable and r.status in (CheckStatus.FAIL, CheckStatus.WARNING)]
        if not fixable:
            console.print("[green]No auto-fixable issues.[/green]")
            return []
        console.print("[yellow]Found " + str(len(fixable)) + " fixable issue(s)[/yellow]")
        if not self.auto_approve and not Confirm.ask("Apply fixes?"):
            return []
        results = []
        for issue in fixable:
            results.append(self._apply_fix(report.bucket_name, issue))
        return results

    def _apply_fix(self, bucket_name, issue):
        fixes = {"Public Access Block": self.s3.block_public_access, "Server-Side Encryption": self.s3.enable_encryption, "Versioning": self.s3.enable_versioning}
        func = fixes.get(issue.check_name)
        if func:
            r = func(bucket_name)
            return {"check": issue.check_name, **r}
        return {"check": issue.check_name, "success": False, "message": "No auto-fix."}
