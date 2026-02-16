"""
S3 Troubleshooter AI - Main Entry Point
========================================
AI-powered S3 diagnostics, analysis, and auto-remediation.
"""

import os
import sys
import json
import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text

from src.aws_client import S3Client
from src.diagnostics import S3Diagnostics
from src.ai_engine import AIEngine
from src.remediator import Remediator
from src.report_generator import ReportGenerator
from src.models import BucketReport

# Load environment variables
load_dotenv()

console = Console()


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    return {}


def print_banner():
    """Print application banner."""
    banner = """
╔══════════════════════════════════════════════════════════╗
║            🪣  S3 TROUBLESHOOTER AI  🤖                  ║
║       AI-Powered S3 Diagnostics & Remediation            ║
║                     v1.0.0                               ║
╚══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold blue")


@click.group()
@click.option("--region", default=None, help="AWS region")
@click.option("--profile", default=None, help="AWS profile name")
@click.pass_context
def cli(ctx, region, profile):
    """S3 Troubleshooter AI - Diagnose, analyze, and fix S3 issues."""
    ctx.ensure_object(dict)
    config = load_config()

    region = region or config.get("aws", {}).get("default_region", "us-east-1")
    ctx.obj["config"] = config
    ctx.obj["region"] = region
    ctx.obj["profile"] = profile


@cli.command()
@click.argument("bucket_name")
@click.option("--fix", is_flag=True, help="Auto-fix issues after diagnosis")
@click.option("--auto-approve", is_flag=True, help="Skip fix confirmations")
@click.option("--no-ai", is_flag=True, help="Skip AI analysis")
@click.option(
    "--output", type=click.Choice(["console", "json", "html", "all"]), default="all"
)
@click.pass_context
def diagnose(ctx, bucket_name, fix, auto_approve, no_ai, output):
    """Run full diagnostic scan on an S3 bucket.

    Example: python main.py diagnose my-bucket-name --fix
    """
    print_banner()
    config = ctx.obj["config"]
    region = ctx.obj["region"]
    profile = ctx.obj["profile"]

    # Initialize components
    console.print("[cyan]Initializing...[/cyan]")

    s3_client = S3Client(region=region, profile=profile)

    # Verify credentials
    creds = s3_client.verify_credentials()
    if not creds.get("valid"):
        console.print(f"[red]❌ AWS credentials invalid: {creds.get('error')}[/red]")
        console.print("[yellow]Please configure AWS credentials:[/yellow]")
        console.print("  aws configure")
        console.print("  or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env")
        sys.exit(1)

    console.print(f"[green]✓ AWS Account: {creds['account']}[/green]")
    console.print(f"[green]✓ Identity: {creds['arn']}[/green]")

    # Run diagnostics
    console.print(f"\n[bold cyan]🔍 Scanning bucket: {bucket_name}[/bold cyan]\n")

    diagnostics = S3Diagnostics(s3_client)
    report = diagnostics.run_all_checks(bucket_name)

    # AI Analysis
    if not no_ai:
        ai_model = config.get("ai", {}).get("model", "gpt-4")
        ai_engine = AIEngine(model=ai_model)

        if ai_engine.is_available():
            console.print("\n[cyan]🤖 Running AI analysis...[/cyan]")
            ai_result = ai_engine.analyze_report(report)

            if isinstance(ai_result, dict):
                report.ai_analysis = ai_result.get("analysis", "")
                report.ai_summary = ai_result.get("summary", "")

                # Print priority actions
                priority_actions = ai_result.get("priority_actions", [])
                if priority_actions:
                    console.print(
                        "\n[bold yellow]🎯 AI Priority Actions:[/bold yellow]"
                    )
                    for action in priority_actions:
                        if isinstance(action, dict):
                            console.print(
                                f"  [{action.get('priority', '?')}] {action.get('action', 'N/A')}"
                            )
                            if action.get("commands"):
                                for cmd in action["commands"]:
                                    console.print(f"      $ {cmd}", style="dim")
            else:
                report.ai_analysis = str(ai_result)
        else:
            console.print("[yellow]⚠ AI analysis skipped (no API key)[/yellow]")

    # Generate reports
    report_gen = ReportGenerator(
        output_dir=config.get("reporting", {}).get("output_dir", "reports")
    )

    if output in ("console", "all"):
        report_gen.print_console_report(report)

    if output in ("json", "all"):
        report_gen.save_json_report(report)

    if output in ("html", "all"):
        report_gen.save_html_report(report)

    # Auto-remediation
    if fix:
        console.print("\n[bold yellow]🔧 Starting Auto-Remediation...[/bold yellow]")
        remediator = Remediator(s3_client, auto_approve=auto_approve)
        fix_results = remediator.remediate_all(report)

        if fix_results:
            console.print("\n[bold]Remediation Summary:[/bold]")
            for fr in fix_results:
                status = "✓" if fr.get("success") else "✗"
                color = "green" if fr.get("success") else "red"
                console.print(
                    f"  [{color}]{status} {fr['check']}: {fr.get('message', fr.get('error', 'Unknown'))}[/{color}]"
                )

    # Final summary
    console.print(f"\n[bold]{'=' * 60}[/bold]")
    console.print(
        f"[bold]Final Score: {report.score}/100 — {report.overall_health}[/bold]"
    )
    console.print(f"[bold]{'=' * 60}[/bold]\n")


@cli.command()
@click.pass_context
def list_buckets(ctx):
    """List all S3 buckets in the account."""
    print_banner()
    region = ctx.obj["region"]
    profile = ctx.obj["profile"]

    s3_client = S3Client(region=region, profile=profile)

    creds = s3_client.verify_credentials()
    if not creds.get("valid"):
        console.print(f"[red]❌ Credentials invalid: {creds.get('error')}[/red]")
        sys.exit(1)

    buckets = s3_client.list_buckets()

    if not buckets:
        console.print("[yellow]No buckets found.[/yellow]")
        return

    console.print(f"\n[bold cyan]Found {len(buckets)} bucket(s):[/bold cyan]")
    for i, bucket in enumerate(buckets, 1):
        console.print(f"  {i}. {bucket}")

    console.print(
        f"\n[dim]Use 'python main.py diagnose <bucket-name>' to scan a bucket.[/dim]"
    )


@cli.command()
@click.argument("bucket_name")
@click.pass_context
def troubleshoot(ctx, bucket_name):
    """Interactive AI troubleshooting session for a bucket.

    Example: python main.py troubleshoot my-bucket-name
    """
    print_banner()
    config = ctx.obj["config"]
    region = ctx.obj["region"]
    profile = ctx.obj["profile"]

    s3_client = S3Client(region=region, profile=profile)
    ai_model = config.get("ai", {}).get("model", "gpt-4")
    ai_engine = AIEngine(model=ai_model)

    if not ai_engine.is_available():
        console.print("[red]❌ AI engine unavailable. Set OPENAI_API_KEY in .env[/red]")
        sys.exit(1)

    creds = s3_client.verify_credentials()
    if not creds.get("valid"):
        console.print(f"[red]❌ Credentials invalid: {creds.get('error')}[/red]")
        sys.exit(1)

    console.print(f"[cyan]🤖 Interactive Troubleshooting for: {bucket_name}[/cyan]")
    console.print("[dim]Type 'quit' or 'exit' to end the session.[/dim]")
    console.print("[dim]Type 'scan' to run a full diagnostic first.[/dim]")
    console.print("[dim]Type 'policy <use-case>' to generate a bucket policy.[/dim]\n")

    # Gather initial context
    diagnostics = S3Diagnostics(s3_client)
    context = {}

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]Describe your issue[/bold green]")

            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[cyan]Session ended. Goodbye![/cyan]")
                break

            if user_input.lower() == "scan":
                console.print("[cyan]Running full diagnostic scan...[/cyan]")
                report = diagnostics.run_all_checks(bucket_name)
                report_gen = ReportGenerator()
                report_gen.print_console_report(report)
                context["last_scan"] = report.to_dict()
                continue

            if user_input.lower().startswith("policy "):
                use_case = user_input[7:].strip()
                console.print(
                    f"[cyan]Generating policy for use case: {use_case}...[/cyan]"
                )
                policy = ai_engine.generate_policy_recommendation(bucket_name, use_case)
                console.print(
                    Panel(policy, title="Generated Bucket Policy", border_style="green")
                )
                continue

            # Regular troubleshooting
            console.print("[cyan]🤖 Analyzing...[/cyan]")
            response = ai_engine.troubleshoot_issue(
                issue_description=user_input,
                bucket_name=bucket_name,
                context=context,
            )
            console.print(
                Panel(
                    response,
                    title="🤖 AI Response",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        except KeyboardInterrupt:
            console.print("\n[cyan]Session ended.[/cyan]")
            break


@cli.command()
@click.argument("bucket_name")
@click.option("--auto-approve", is_flag=True, help="Skip confirmations")
@click.pass_context
def fix(ctx, bucket_name, auto_approve):
    """Scan and auto-fix issues on a bucket.

    Example: python main.py fix my-bucket-name --auto-approve
    """
    print_banner()
    region = ctx.obj["region"]
    profile = ctx.obj["profile"]

    s3_client = S3Client(region=region, profile=profile)

    creds = s3_client.verify_credentials()
    if not creds.get("valid"):
        console.print(f"[red]❌ Credentials invalid[/red]")
        sys.exit(1)

    # Scan
    console.print(f"[cyan]🔍 Scanning {bucket_name}...[/cyan]\n")
    diagnostics = S3Diagnostics(s3_client)
    report = diagnostics.run_all_checks(bucket_name)

    # Show quick summary
    report_gen = ReportGenerator()
    report_gen.print_console_report(report)

    # Fix
    console.print("\n[bold yellow]🔧 Auto-Remediation[/bold yellow]")
    remediator = Remediator(s3_client, auto_approve=auto_approve)
    fix_results = remediator.remediate_all(report)

    if fix_results:
        # Re-scan to verify
        console.print("\n[cyan]🔍 Re-scanning to verify fixes...[/cyan]\n")
        new_report = diagnostics.run_all_checks(bucket_name)
        new_report.calculate_score()

        console.print(
            f"[bold]Before: {report.score}/100 → After: {new_report.score}/100[/bold]"
        )

        improvement = new_report.score - report.score
        if improvement > 0:
            console.print(f"[green]📈 Improved by {improvement} points![/green]")
        else:
            console.print(
                "[yellow]Score unchanged. Some issues may require manual intervention.[/yellow]"
            )


@cli.command()
@click.pass_context
def scan_all(ctx):
    """Scan ALL buckets in the account and generate a summary."""
    print_banner()
    region = ctx.obj["region"]
    profile = ctx.obj["profile"]

    s3_client = S3Client(region=region, profile=profile)

    creds = s3_client.verify_credentials()
    if not creds.get("valid"):
        console.print(f"[red]❌ Credentials invalid[/red]")
        sys.exit(1)

    buckets = s3_client.list_buckets()
    if not buckets:
        console.print("[yellow]No buckets found.[/yellow]")
        return

    console.print(f"[cyan]Found {len(buckets)} buckets. Starting scan...[/cyan]\n")

    diagnostics = S3Diagnostics(s3_client)
    report_gen = ReportGenerator()
    all_reports = []

    for bucket in buckets:
        console.print(f"\n[bold cyan]{'=' * 40}[/bold cyan]")
        console.print(f"[bold cyan]Scanning: {bucket}[/bold cyan]")
        console.print(f"[bold cyan]{'=' * 40}[/bold cyan]")

        try:
            report = diagnostics.run_all_checks(bucket)
            all_reports.append(report)
            report_gen.save_json_report(report)
            console.print(f"  Score: {report.score}/100 — {report.overall_health}")
        except Exception as e:
            console.print(f"  [red]Error scanning {bucket}: {e}[/red]")

    # Print summary table
    if all_reports:
        from rich.table import Table

        console.print(f"\n\n[bold cyan]{'=' * 60}[/bold cyan]")
        console.print(f"[bold cyan]  ACCOUNT-WIDE S3 HEALTH SUMMARY[/bold cyan]")
        console.print(f"[bold cyan]{'=' * 60}[/bold cyan]\n")

        table = Table(show_lines=True)
        table.add_column("Bucket", style="cyan")
        table.add_column("Score", justify="center")
        table.add_column("Health", justify="center")
        table.add_column("Pass", justify="center", style="green")
        table.add_column("Fail", justify="center", style="red")
        table.add_column("Warn", justify="center", style="yellow")

        for r in sorted(all_reports, key=lambda x: x.score):
            health_colors = {
                "HEALTHY": "green",
                "GOOD": "green",
                "NEEDS_ATTENTION": "yellow",
                "UNHEALTHY": "red",
                "CRITICAL": "bold red",
            }
            hc = health_colors.get(r.overall_health, "white")

            from src.models import CheckStatus

            passed = sum(1 for res in r.results if res.status == CheckStatus.PASS)
            failed = sum(1 for res in r.results if res.status == CheckStatus.FAIL)
            warned = sum(1 for res in r.results if res.status == CheckStatus.WARNING)

            table.add_row(
                r.bucket_name,
                f"[{hc}]{r.score}/100[/{hc}]",
                f"[{hc}]{r.overall_health}[/{hc}]",
                str(passed),
                str(failed),
                str(warned),
            )

        console.print(table)

        avg_score = sum(r.score for r in all_reports) / len(all_reports)
        console.print(f"\n[bold]Average Account Score: {avg_score:.0f}/100[/bold]")
        console.print(f"[bold]Total Buckets Scanned: {len(all_reports)}[/bold]\n")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    cli()
