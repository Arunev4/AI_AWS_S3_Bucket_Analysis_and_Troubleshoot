"""Flask API backend for S3 Troubleshooter Chrome Extension."""

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from src.aws_client import S3Client
from src.diagnostics import S3Diagnostics
from src.ai_engine import AIEngine
from src.remediator import Remediator
from src.models import CheckStatus

app = Flask(__name__)
CORS(app)

print("Initializing clients...")
s3_client = S3Client(region="us-east-1")
diagnostics = S3Diagnostics(s3_client)
ai_engine = AIEngine()
print("AI available:", ai_engine.is_available())


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "version": "1.0.0", "ai_available": ai_engine.is_available()})


@app.route("/api/credentials", methods=["GET"])
def check_credentials():
    try:
        return jsonify(s3_client.verify_credentials())
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 500


@app.route("/api/buckets", methods=["GET"])
def list_buckets():
    try:
        buckets = s3_client.list_buckets()
        return jsonify({"buckets": buckets, "count": len(buckets)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/diagnose/<bucket_name>", methods=["GET"])
def diagnose_bucket(bucket_name):
    try:
        report = diagnostics.run_all_checks(bucket_name)
        return jsonify(report.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/diagnose-ai/<bucket_name>", methods=["GET"])
def diagnose_with_ai(bucket_name):
    try:
        report = diagnostics.run_all_checks(bucket_name)
        if ai_engine.is_available():
            ai_result = ai_engine.analyze_report(report)
            if isinstance(ai_result, dict):
                report.ai_analysis = ai_result.get("analysis", "")
                report.ai_summary = ai_result.get("summary", "")
        else:
            report.ai_analysis = "AI not available."
        return jsonify(report.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fix/<bucket_name>", methods=["POST"])
def fix_bucket(bucket_name):
    try:
        report = diagnostics.run_all_checks(bucket_name)

        fixable = [r for r in report.results if r.auto_fixable and r.status in (CheckStatus.FAIL, CheckStatus.WARNING)]

        results = []
        for issue in fixable:
            fix_map = {
                "Public Access Block": s3_client.block_public_access,
                "Server-Side Encryption": s3_client.enable_encryption,
                "Versioning": s3_client.enable_versioning,
            }
            func = fix_map.get(issue.check_name)
            if func:
                r = func(bucket_name)
                results.append({"check": issue.check_name, **r})

        new_report = diagnostics.run_all_checks(bucket_name)

        # AI recommendations for remaining issues
        ai_advice = ""
        if ai_engine.is_available():
            failed = [r for r in new_report.results if r.status.value in ("FAIL", "WARNING", "ERROR")]
            if failed:
                issue_list = []
                for r in failed:
                    issue_list.append(r.check_name + ": " + r.message)
                issues_text = chr(10).join(issue_list)

                system = "You are an AWS S3 expert. For each issue provide: 1) Exact steps to fix 2) AWS CLI commands 3) AWS documentation link 4) Why it matters."
                user = "Bucket: " + bucket_name + chr(10) + chr(10) + "Remaining issues after auto-fix:" + chr(10) + issues_text
                try:
                    ai_advice = ai_engine._call_bedrock(system, user, 4000)
                except Exception as e:
                    ai_advice = "AI analysis failed: " + str(e)

        return jsonify({
            "fixes_applied": results,
            "before_score": report.score,
            "after_score": new_report.score,
            "improvement": new_report.score - report.score,
            "report": new_report.to_dict(),
            "ai_recommendations": ai_advice,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/troubleshoot", methods=["POST"])
def troubleshoot():
    try:
        data = request.json
        bucket_name = data.get("bucket_name", "")
        issue = data.get("issue", "")
        context = data.get("context", {})

        if not ai_engine.is_available():
            return jsonify({"response": "AI not available."})

        response = ai_engine.troubleshoot_issue(issue, bucket_name, context)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan-all", methods=["GET"])
def scan_all():
    try:
        buckets = s3_client.list_buckets()
        results = []
        for b in buckets:
            try:
                report = diagnostics.run_all_checks(b)
                results.append({
                    "bucket": b,
                    "score": report.score,
                    "health": report.overall_health,
                    "passed": sum(1 for r in report.results if r.status == CheckStatus.PASS),
                    "failed": sum(1 for r in report.results if r.status == CheckStatus.FAIL),
                    "warnings": sum(1 for r in report.results if r.status == CheckStatus.WARNING),
                })
            except Exception as e:
                results.append({"bucket": b, "score": 0, "health": "ERROR", "error": str(e)})

        avg = sum(r["score"] for r in results) / len(results) if results else 0
        return jsonify({"buckets": results, "total": len(results), "average_score": int(avg)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("")
    print("=" * 50)
    print("S3 Troubleshooter API - http://localhost:5000")
    print("AI available:", ai_engine.is_available())
    print("=" * 50)
    app.run(debug=False, port=5000)
