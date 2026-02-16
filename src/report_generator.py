"""Report generation in JSON and HTML formats."""

import json
import os
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from jinja2 import Template

from src.models import BucketReport, CheckStatus, Severity

console = Console()


class ReportGenerator:
    """Generates beautiful console output, JSON, and HTML reports."""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def print_console_report(self, report: BucketReport):
        """Print a rich formatted report to the console."""

        # Header
        health_colors = {
            "HEALTHY": "green",
            "GOOD": "green",
            "NEEDS_ATTENTION": "yellow",
            "UNHEALTHY": "red",
            "CRITICAL": "bold red",
        }
        color = health_colors.get(report.overall_health, "white")

        header = Text()
        header.append(f"\n{'=' * 60}\n", style="bold blue")
        header.append(f"  S3 DIAGNOSTIC REPORT\n", style="bold white")
        header.append(f"  Bucket: {report.bucket_name}\n", style="bold cyan")
        header.append(f"  Region: {report.region}\n", style="white")
        header.append(f"  Score:  {report.score}/100\n", style=f"bold {color}")
        header.append(f"  Health: {report.overall_health}\n", style=f"bold {color}")
        header.append(f"{'=' * 60}\n", style="bold blue")
        console.print(header)

        # Results table
        table = Table(title="Diagnostic Results", show_lines=True)
        table.add_column("Check", style="cyan", width=25)
        table.add_column("Status", width=10, justify="center")
        table.add_column("Severity", width=10, justify="center")
        table.add_column("Message", width=50)
        table.add_column("Fix?", width=5, justify="center")

        status_styles = {
            CheckStatus.PASS: "[green]✓ PASS[/green]",
            CheckStatus.FAIL: "[red]✗ FAIL[/red]",
            CheckStatus.WARNING: "[yellow]⚠ WARN[/yellow]",
            CheckStatus.ERROR: "[red]✗ ERR[/red]",
            CheckStatus.SKIPPED: "[dim]- SKIP[/dim]",
            CheckStatus.INFO: "[blue]ℹ INFO[/blue]",
        }

        severity_styles = {
            Severity.CRITICAL: "[bold red]CRITICAL[/bold red]",
            Severity.HIGH: "[red]HIGH[/red]",
            Severity.MEDIUM: "[yellow]MEDIUM[/yellow]",
            Severity.LOW: "[green]LOW[/green]",
            Severity.INFO: "[blue]INFO[/blue]",
        }

        for r in report.results:
            table.add_row(
                r.check_name,
                status_styles.get(r.status, str(r.status.value)),
                severity_styles.get(r.severity, str(r.severity.value)),
                r.message,
                "🔧" if r.auto_fixable else "",
            )

        console.print(table)

        # Recommendations
        recommendations = [r for r in report.results if r.recommendation]
        if recommendations:
            console.print("\n[bold yellow]📋 Recommendations:[/bold yellow]")
            for i, r in enumerate(recommendations, 1):
                icon = (
                    "🔴" if r.severity in (Severity.CRITICAL, Severity.HIGH) else "🟡"
                )
                console.print(f"  {icon} {i}. [{r.check_name}] {r.recommendation}")

        # AI Analysis
        if report.ai_analysis:
            console.print(
                Panel(
                    report.ai_analysis,
                    title="🤖 AI Analysis",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        if report.ai_summary:
            console.print(
                Panel(
                    report.ai_summary,
                    title="📝 AI Summary",
                    border_style="green",
                    padding=(1, 2),
                )
            )

    def save_json_report(self, report: BucketReport) -> str:
        """Save report as JSON."""
        filename = (
            f"{report.bucket_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        console.print(f"[green]JSON report saved: {filepath}[/green]")
        return filepath

    def save_html_report(self, report: BucketReport) -> str:
        """Save report as HTML."""
        filename = (
            f"{report.bucket_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
        )
        filepath = os.path.join(self.output_dir, filename)

        html = self._generate_html(report)

        with open(filepath, "w") as f:
            f.write(html)

        console.print(f"[green]HTML report saved: {filepath}[/green]")
        return filepath

    def _generate_html(self, report: BucketReport) -> str:
        template = Template(HTML_TEMPLATE)
        return template.render(
            report=report,
            results=report.results,
            CheckStatus=CheckStatus,
            Severity=Severity,
            generated_at=datetime.utcnow().isoformat(),
        )


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S3 Diagnostic Report - {{ report.bucket_name }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #1a1f35, #2d1b69); padding: 30px; border-radius: 12px; margin-bottom: 20px; }
        .header h1 { color: #58a6ff; font-size: 28px; }
        .header .meta { color: #8b949e; margin-top: 10px; }
        .score-badge {
            display: inline-block; padding: 8px 20px; border-radius: 20px; font-size: 24px; font-weight: bold; margin-top: 15px;
            {% if report.score >= 90 %}background: #238636; color: #fff;
            {% elif report.score >= 70 %}background: #2ea043; color: #fff;
            {% elif report.score >= 50 %}background: #d29922; color: #000;
            {% elif report.score >= 30 %}background: #da3633; color: #fff;
            {% else %}background: #8b0000; color: #fff;
            {% endif %}
        }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }
        .stat-card .number { font-size: 32px; font-weight: bold; }
        .stat-card .label { color: #8b949e; font-size: 14px; margin-top: 5px; }
        .stat-pass .number { color: #3fb950; }
        .stat-fail .number { color: #f85149; }
        .stat-warn .number { color: #d29922; }
        .stat-err .number { color: #da3633; }
        .stat-total .number { color: #58a6ff; }
        .section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        .section h2 { color: #58a6ff; margin-bottom: 15px; font-size: 20px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #21262d; color: #c9d1d9; padding: 12px; text-align: left; font-weight: 600; }
        td { padding: 12px; border-bottom: 1px solid #21262d; vertical-align: top; }
        tr:hover { background: #1c2128; }
        .status-pass { color: #3fb950; font-weight: bold; }
        .status-fail { color: #f85149; font-weight: bold; }
        .status-warning { color: #d29922; font-weight: bold; }
        .status-error { color: #da3633; font-weight: bold; }
        .status-info { color: #58a6ff; font-weight: bold; }
        .status-skipped { color: #8b949e; font-weight: bold; }
        .severity-critical { background: #8b0000; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .severity-high { background: #da3633; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .severity-medium { background: #d29922; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .severity-low { background: #238636; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .severity-info { background: #1f6feb; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .recommendation { background: #1c2128; border-left: 3px solid #d29922; padding: 10px 15px; margin-top: 8px; border-radius: 0 4px 4px 0; font-size: 14px; }
        .ai-section { background: #0d1117; border: 1px solid #1f6feb; border-radius: 8px; padding: 20px; margin-top: 20px; white-space: pre-wrap; line-height: 1.6; }
        .ai-section h3 { color: #58a6ff; margin-bottom: 10px; }
        .fix-badge { background: #1f6feb; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
        .footer { text-align: center; color: #484f58; margin-top: 30px; padding: 20px; font-size: 13px; }
        .progress-bar { width: 100%; height: 20px; background: #21262d; border-radius: 10px; overflow: hidden; margin-top: 10px; }
        .progress-fill {
            height: 100%; border-radius: 10px; transition: width 0.5s;
            {% if report.score >= 90 %}background: linear-gradient(90deg, #238636, #3fb950);
            {% elif report.score >= 70 %}background: linear-gradient(90deg, #2ea043, #56d364);
            {% elif report.score >= 50 %}background: linear-gradient(90deg, #9e6a03, #d29922);
            {% elif report.score >= 30 %}background: linear-gradient(90deg, #da3633, #f85149);
            {% else %}background: linear-gradient(90deg, #8b0000, #da3633);
            {% endif %}
            width: {{ report.score }}%;
        }
        .collapsible { cursor: pointer; user-select: none; }
        .collapsible:after { content: ' ▼'; font-size: 12px; }
        .details-content { display: none; margin-top: 10px; background: #0d1117; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 13px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <h1>🪣 S3 Diagnostic Report</h1>
            <div class="meta">
                <strong>Bucket:</strong> {{ report.bucket_name }} &nbsp;|&nbsp;
                <strong>Region:</strong> {{ report.region }} &nbsp;|&nbsp;
                <strong>Scan Start:</strong> {{ report.scan_start }} &nbsp;|&nbsp;
                <strong>Scan End:</strong> {{ report.scan_end }}
            </div>
            <div class="score-badge">Score: {{ report.score }}/100 — {{ report.overall_health }}</div>
            <div class="progress-bar"><div class="progress-fill"></div></div>
        </div>

        <!-- STATS -->
        <div class="stats">
            <div class="stat-card stat-total">
                <div class="number">{{ report.results|length }}</div>
                <div class="label">Total Checks</div>
            </div>
            <div class="stat-card stat-pass">
                <div class="number">{{ report.results|selectattr('status', 'equalto', CheckStatus.PASS)|list|length }}</div>
                <div class="label">Passed</div>
            </div>
            <div class="stat-card stat-fail">
                <div class="number">{{ report.results|selectattr('status', 'equalto', CheckStatus.FAIL)|list|length }}</div>
                <div class="label">Failed</div>
            </div>
            <div class="stat-card stat-warn">
                <div class="number">{{ report.results|selectattr('status', 'equalto', CheckStatus.WARNING)|list|length }}</div>
                <div class="label">Warnings</div>
            </div>
            <div class="stat-card stat-err">
                <div class="number">{{ report.results|selectattr('status', 'equalto', CheckStatus.ERROR)|list|length }}</div>
                <div class="label">Errors</div>
            </div>
        </div>

        <!-- RESULTS TABLE -->
        <div class="section">
            <h2>📊 Diagnostic Results</h2>
            <table>
                <thead>
                    <tr>
                        <th>Check</th>
                        <th>Status</th>
                        <th>Severity</th>
                        <th>Message</th>
                        <th>Auto-Fix</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in results %}
                    <tr>
                        <td><strong>{{ r.check_name }}</strong></td>
                        <td>
                            {% if r.status == CheckStatus.PASS %}<span class="status-pass">✓ PASS</span>
                            {% elif r.status == CheckStatus.FAIL %}<span class="status-fail">✗ FAIL</span>
                            {% elif r.status == CheckStatus.WARNING %}<span class="status-warning">⚠ WARN</span>
                            {% elif r.status == CheckStatus.ERROR %}<span class="status-error">✗ ERROR</span>
                            {% elif r.status == CheckStatus.INFO %}<span class="status-info">ℹ INFO</span>
                            {% else %}<span class="status-skipped">— SKIP</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if r.severity == Severity.CRITICAL %}<span class="severity-critical">CRITICAL</span>
                            {% elif r.severity == Severity.HIGH %}<span class="severity-high">HIGH</span>
                            {% elif r.severity == Severity.MEDIUM %}<span class="severity-medium">MEDIUM</span>
                            {% elif r.severity == Severity.LOW %}<span class="severity-low">LOW</span>
                            {% else %}<span class="severity-info">INFO</span>
                            {% endif %}
                        </td>
                        <td>
                            {{ r.message }}
                            {% if r.recommendation %}
                            <div class="recommendation">💡 {{ r.recommendation }}</div>
                            {% endif %}
                        </td>
                        <td>{% if r.auto_fixable %}<span class="fix-badge">🔧 FIX</span>{% endif %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <!-- AI ANALYSIS -->
        {% if report.ai_analysis %}
        <div class="section">
            <h2>🤖 AI Analysis</h2>
            <div class="ai-section">{{ report.ai_analysis }}</div>
        </div>
        {% endif %}

        {% if report.ai_summary %}
        <div class="section">
            <h2>📝 AI Summary</h2>
            <div class="ai-section">{{ report.ai_summary }}</div>
        </div>
        {% endif %}

        <!-- FOOTER -->
        <div class="footer">
            Generated by S3 Troubleshooter AI v1.0.0 | {{ generated_at }}
        </div>
    </div>

    <script>
        document.querySelectorAll('.collapsible').forEach(el => {
            el.addEventListener('click', () => {
                const content = el.nextElementSibling;
                content.style.display = content.style.display === 'block' ? 'none' : 'block';
            });
        });
    </script>
</body>
</html>"""
