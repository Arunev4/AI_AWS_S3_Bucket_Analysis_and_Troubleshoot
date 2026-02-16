"""S3 Troubleshooter AI - Main Entry Point."""

import os
import sys
import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from src.aws_client import S3Client
from src.diagnostics import S3Diagnostics
from src.ai_engine import AIEngine
from src.remediator import Remediator
from src.report_generator import ReportGenerator

load_dotenv()
console = Console()


def load_config():
    path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f)
    return {}


def print_banner():
    console.print("")
    console.print("[bold blue]======================================================[/bold blue]")
    console.print("[bold blue]          S3 TROUBLESHOOTER AI  v1.0.0                [/bold blue]")
    console.print("[bold blue]   AI-Powered S3 Diagnostics & Remediation            [/bold blue]")
    console.print("[bold blue]======================================================[/bold blue]")
    console.print("")


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
@click.option("--fix", is_flag=True, help="Auto-fix issues after scan")
@click.option("--auto-approve", is_flag=True, help="Skip fix confirmations")
@click.option("--no-ai", is_flag=True, help="Skip AI analysis")
@click.option("--output", type=click.Choice(["console", "json", "html", "all"]), default="all")
@click.pass_context
def diagnose(ctx, bucket_name, fix, auto_approve, no_ai, output):
    """Run full diagnostic scan on an S3 bucket."""
    print_banner()
    config = ctx.obj["config"]
    region = ctx.obj["region"]
    profile = ctx.obj["profile"]

    s3_client = S3Client(region=region, profile=profile)

    creds = s3_client.verify_credentials()
    if not creds.get("valid"):
        console.print("[red]AWS credentials invalid: " + str(creds.get("error")) + "[/red]")
        console.print("[yellow]Run: aws configure[/yellow]")
        sys.exit(1)

    console.print("[green]AWS Account: " + creds["account"] + "[/green]")
    console.print("[green]Identity: " + creds["arn"] + "[/green]")
    console.print("")
    console.print("[bold cyan]Scanning bucket: " + bucket_name + "[/bold cyan]")
    console.print("")

    diagnostics = S3Diagnostics(s3_client)
    report = diagnostics.run_all_checks(bucket_name)

    if not no_ai:
        model = config.get("ai", {}).get("model", "gpt-4")
        ai = AIEngine(model=model, region=ctx.obj["region"], profile=ctx.obj["profile"])
        if ai.is_available():
            console.print("[cyan]Running AI analysis...[/cyan]")
            ai_result = ai.analyze_report(report)
            if isinstance(ai_result, dict):
                report.ai_analysis = ai_result.get("analysis", "")
                report.ai_summary = ai_result.get("summary", "")
                actions = ai_result.get("priority_actions", [])
                if actions:
                    console.print("[bold yellow]AI Priority Actions:[/bold yellow]")
                    for a in actions:
                        if isinstance(a, dict):
                            console.print("  [" + str(a.get("priority", "?")) + "] " + str(a.get("action", "N/A")))
        else:
            console.print("[yellow]AI skipped (no OPENAI_API_KEY)[/yellow]")

    rg = ReportGenerator(output_dir=config.get("reporting", {}).get("output_dir", "reports"))
    if output in ("console", "all"):
        rg.print_console_report(report)
    if output in ("json", "all"):
        rg.save_json_report(report)
    if output in ("html", "all"):
        rg.save_html_report(report)

    if fix:
        console.print("[bold yellow]Auto-Remediation...[/bold yellow]")
        rem = Remediator(s3_client, auto_approve=auto_approve)
        results = rem.remediate_all(report)
        for fr in results:
            if fr.get("success"):
                console.print("[green]  OK: " + fr["check"] + " - " + fr.get("message", "") + "[/green]")
            else:
                console.print("[red]  FAIL: " + fr["check"] + " - " + fr.get("error", "Unknown") + "[/red]")

    console.print("")
    console.print("[bold]Score: " + str(report.score) + "/100 - " + report.overall_health + "[/bold]")
    console.print("")


@cli.command()
@click.pass_context
def list_buckets(ctx):
    """List all S3 buckets in the account."""
    print_banner()
    s3 = S3Client(region=ctx.obj["region"], profile=ctx.obj["profile"])
    creds = s3.verify_credentials()
    if not creds.get("valid"):
        console.print("[red]Credentials invalid: " + str(creds.get("error")) + "[/red]")
        sys.exit(1)
    console.print("[green]AWS Account: " + creds["account"] + "[/green]")
    buckets = s3.list_buckets()
    if not buckets:
        console.print("[yellow]No buckets found.[/yellow]")
        return
    console.print("[bold cyan]Found " + str(len(buckets)) + " bucket(s):[/bold cyan]")
    for i, b in enumerate(buckets, 1):
        console.print("  " + str(i) + ". " + b)
    console.print("")
    console.print("[dim]Run: python main.py diagnose <bucket-name>[/dim]")


@cli.command()
@click.argument("bucket_name")
@click.pass_context
def troubleshoot(ctx, bucket_name):
    """Interactive AI troubleshooting session."""
    print_banner()
    config = ctx.obj["config"]
    s3 = S3Client(region=ctx.obj["region"], profile=ctx.obj["profile"])
    ai = AIEngine(model=config.get("ai", {}).get("model", "gpt-4"), region=ctx.obj["region"], profile=ctx.obj["profile"])

    if not ai.is_available():
        console.print("[red]Set OPENAI_API_KEY in .env[/red]")
        sys.exit(1)

    creds = s3.verify_credentials()
    if not creds.get("valid"):
        console.print("[red]Credentials invalid[/red]")
        sys.exit(1)

    console.print("[cyan]Troubleshooting: " + bucket_name + "[/cyan]")
    console.print("[dim]Type quit to exit, scan for diagnostics[/dim]")
    console.print("")

    diag = S3Diagnostics(s3)
    context = {}

    while True:
        try:
            q = Prompt.ask("[bold green]Describe your issue[/bold green]")
            if q.lower() in ("quit", "exit", "q"):
                console.print("[cyan]Goodbye![/cyan]")
                break
            if q.lower() == "scan":
                report = diag.run_all_checks(bucket_name)
                ReportGenerator().print_console_report(report)
                context["scan"] = report.to_dict()
                continue
            console.print("[cyan]Thinking...[/cyan]")
            resp = ai.troubleshoot_issue(q, bucket_name, context)
            console.print(Panel(resp, title="AI Response", border_style="blue"))
        except KeyboardInterrupt:
            console.print("[cyan]Bye![/cyan]")
            break


@cli.command()
@click.argument("bucket_name")
@click.option("--auto-approve", is_flag=True)
@click.pass_context
def fix(ctx, bucket_name, auto_approve):
    """Scan and auto-fix a bucket."""
    print_banner()
    s3 = S3Client(region=ctx.obj["region"], profile=ctx.obj["profile"])
    creds = s3.verify_credentials()
    if not creds.get("valid"):
        console.print("[red]Credentials invalid[/red]")
        sys.exit(1)

    console.print("[cyan]Scanning " + bucket_name + "...[/cyan]")
    diag = S3Diagnostics(s3)
    report = diag.run_all_checks(bucket_name)
    ReportGenerator().print_console_report(report)

    console.print("[bold yellow]Auto-Remediation[/bold yellow]")
    rem = Remediator(s3, auto_approve=auto_approve)
    results = rem.remediate_all(report)

    if results:
        console.print("[cyan]Re-scanning...[/cyan]")
        new_report = diag.run_all_checks(bucket_name)
        diff = new_report.score - report.score
        console.print("[bold]Before: " + str(report.score) + " -> After: " + str(new_report.score) + "[/bold]")
        if diff > 0:
            console.print("[green]Improved by " + str(diff) + " points![/green]")


@cli.command()
@click.pass_context
def scan_all(ctx):
    """Scan ALL buckets in the account."""
    print_banner()
    s3 = S3Client(region=ctx.obj["region"], profile=ctx.obj["profile"])
    creds = s3.verify_credentials()
    if not creds.get("valid"):
        console.print("[red]Credentials invalid[/red]")
        sys.exit(1)

    buckets = s3.list_buckets()
    if not buckets:
        console.print("[yellow]No buckets found.[/yellow]")
        return

    console.print("[cyan]Scanning " + str(len(buckets)) + " buckets...[/cyan]")
    diag = S3Diagnostics(s3)
    rg = ReportGenerator()
    reports = []

    for b in buckets:
        console.print("[bold cyan]--- " + b + " ---[/bold cyan]")
        try:
            r = diag.run_all_checks(b)
            reports.append(r)
            rg.save_json_report(r)
            console.print("  Score: " + str(r.score) + "/100 - " + r.overall_health)
        except Exception as e:
            console.print("[red]  Error: " + str(e) + "[/red]")

    if reports:
        from rich.table import Table
        console.print("")
        console.print("[bold cyan]ACCOUNT SUMMARY[/bold cyan]")
        t = Table(show_lines=True)
        t.add_column("Bucket", style="cyan")
        t.add_column("Score", justify="center")
        t.add_column("Health", justify="center")
        for r in sorted(reports, key=lambda x: x.score):
            c = "green" if r.score >= 70 else ("yellow" if r.score >= 40 else "red")
            t.add_row(r.bucket_name, "[" + c + "]" + str(r.score) + "[/" + c + "]", "[" + c + "]" + r.overall_health + "[/" + c + "]")
        console.print(t)
        avg = sum(r.score for r in reports) / len(reports)
        console.print("[bold]Average: " + str(int(avg)) + "/100 | Buckets: " + str(len(reports)) + "[/bold]")


if __name__ == "__main__":
    cli()
