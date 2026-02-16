"""Auto-remediation engine for S3 issues."""

from rich.console import Console
from rich.prompt import Confirm

from src.aws_client import S3Client
from src.models import BucketReport, DiagnosticResult, CheckStatus

console = Console()


class Remediator:
    """Applies fixes for identified S3 issues."""

    def __init__(self, s3_client: S3Client, auto_approve: bool = False):
        self.s3 = s3_client
        self.auto_approve = auto_approve

    def remediate_all(self, report: BucketReport) -> list[dict]:
        """Attempt to fix all auto-fixable issues."""
        fixable = [
            r
            for r in report.results
            if r.auto_fixable and r.status in (CheckStatus.FAIL, CheckStatus.WARNING)
        ]

        if not fixable:
            console.print("[green]No auto-fixable issues found.[/green]")
            return []

        console.print(f"\n[yellow]Found {len(fixable)} auto-fixable issue(s):[/yellow]")
        for i, issue in enumerate(fixable, 1):
            console.print(
                f"  {i}. [{issue.severity.value}] {issue.check_name}: {issue.fix_description}"
            )

        if not self.auto_approve:
            if not Confirm.ask("\nDo you want to apply these fixes?"):
                console.print("[yellow]Remediation cancelled.[/yellow]")
                return []

        results = []
        for issue in fixable:
            result = self._apply_fix(report.bucket_name, issue)
            results.append(result)

        return results

    def _apply_fix(self, bucket_name: str, issue: DiagnosticResult) -> dict:
        """Route fix to appropriate method."""
        fix_map = {
            "Public Access Block": self._fix_public_access,
            "Server-Side Encryption": self._fix_encryption,
            "Versioning": self._fix_versioning,
        }

        fix_func = fix_map.get(issue.check_name)
        if fix_func:
            console.print(f"\n[cyan]Fixing: {issue.check_name}...[/cyan]")
            result = fix_func(bucket_name)
            if result.get("success"):
                console.print(f"  [green]✓ {result['message']}[/green]")
            else:
                console.print(f"  [red]✗ Failed: {result.get('error')}[/red]")
            return {"check": issue.check_name, **result}

        return {
            "check": issue.check_name,
            "success": False,
            "message": "No automated fix available for this check.",
        }

    def _fix_public_access(self, bucket_name: str) -> dict:
        return self.s3.block_public_access(bucket_name)

    def _fix_encryption(self, bucket_name: str) -> dict:
        return self.s3.enable_encryption(bucket_name)

    def _fix_versioning(self, bucket_name: str) -> dict:
        return self.s3.enable_versioning(bucket_name)
