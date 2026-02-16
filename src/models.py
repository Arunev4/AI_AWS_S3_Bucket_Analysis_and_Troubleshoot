"""Data models for the S3 Troubleshooter."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CheckStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


@dataclass
class DiagnosticResult:
    """Result of a single diagnostic check."""

    check_name: str
    status: CheckStatus
    severity: Severity
    message: str
    details: dict = field(default_factory=dict)
    recommendation: str = ""
    auto_fixable: bool = False
    fix_description: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "recommendation": self.recommendation,
            "auto_fixable": self.auto_fixable,
            "fix_description": self.fix_description,
            "timestamp": self.timestamp,
        }


@dataclass
class BucketReport:
    """Complete diagnostic report for a bucket."""

    bucket_name: str
    region: str
    scan_start: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    scan_end: Optional[str] = None
    results: list[DiagnosticResult] = field(default_factory=list)
    ai_analysis: str = ""
    ai_summary: str = ""
    overall_health: str = "UNKNOWN"
    score: int = 0

    def add_result(self, result: DiagnosticResult):
        self.results.append(result)

    def to_dict(self) -> dict:
        return {
            "bucket_name": self.bucket_name,
            "region": self.region,
            "scan_start": self.scan_start,
            "scan_end": self.scan_end,
            "overall_health": self.overall_health,
            "score": self.score,
            "total_checks": len(self.results),
            "passed": sum(1 for r in self.results if r.status == CheckStatus.PASS),
            "failed": sum(1 for r in self.results if r.status == CheckStatus.FAIL),
            "warnings": sum(1 for r in self.results if r.status == CheckStatus.WARNING),
            "errors": sum(1 for r in self.results if r.status == CheckStatus.ERROR),
            "results": [r.to_dict() for r in self.results],
            "ai_analysis": self.ai_analysis,
            "ai_summary": self.ai_summary,
        }

    def calculate_score(self):
        """Calculate health score out of 100."""
        if not self.results:
            self.score = 0
            self.overall_health = "UNKNOWN"
            return

        total = len(self.results)
        weights = {
            CheckStatus.PASS: 1.0,
            CheckStatus.WARNING: 0.6,
            CheckStatus.FAIL: 0.0,
            CheckStatus.ERROR: 0.0,
            CheckStatus.SKIPPED: 0.5,
        }

        severity_multipliers = {
            Severity.CRITICAL: 3.0,
            Severity.HIGH: 2.5,
            Severity.MEDIUM: 2.0,
            Severity.LOW: 1.5,
            Severity.INFO: 1.0,
        }

        weighted_score = 0
        total_weight = 0

        for r in self.results:
            multiplier = severity_multipliers.get(r.severity, 1.0)
            weighted_score += weights.get(r.status, 0) * multiplier
            total_weight += multiplier

        self.score = (
            int((weighted_score / total_weight) * 100) if total_weight > 0 else 0
        )

        if self.score >= 90:
            self.overall_health = "HEALTHY"
        elif self.score >= 70:
            self.overall_health = "GOOD"
        elif self.score >= 50:
            self.overall_health = "NEEDS_ATTENTION"
        elif self.score >= 30:
            self.overall_health = "UNHEALTHY"
        else:
            self.overall_health = "CRITICAL"
