"""AI Engine - AWS Bedrock only (no OpenAI)."""

import json
import boto3
from botocore.exceptions import ClientError
from rich.console import Console

console = Console()


class AIEngine:
    def __init__(self, api_key=None, model="gpt-4"):
        self.bedrock_client = None
        try:
            self.bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")
            console.print("[green]AI Engine: AWS Bedrock ready[/green]")
        except Exception as e:
            console.print("[yellow]Bedrock init failed: " + str(e)[:100] + "[/yellow]")

    def is_available(self):
        return self.bedrock_client is not None

    def _call_bedrock(self, system_prompt, user_prompt, max_tokens=4000):
        models = [
            "anthropic.claude-3-sonnet-20240229-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "anthropic.claude-v2:1",
            "anthropic.claude-v2",
            "anthropic.claude-instant-v1",
            "amazon.titan-text-express-v1",
        ]
        for model_id in models:
            try:
                if "claude-3" in model_id:
                    body = json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}]
                    })
                    r = self.bedrock_client.invoke_model(
                        modelId=model_id, body=body,
                        contentType="application/json", accept="application/json"
                    )
                    result = json.loads(r["body"].read())
                    return result["content"][0]["text"]

                elif "claude" in model_id:
                    body = json.dumps({
                        "prompt": "\n\nHuman: " + system_prompt + "\n\n" + user_prompt + "\n\nAssistant:",
                        "max_tokens_to_sample": max_tokens,
                        "temperature": 0.2,
                    })
                    r = self.bedrock_client.invoke_model(
                        modelId=model_id, body=body,
                        contentType="application/json", accept="application/json"
                    )
                    result = json.loads(r["body"].read())
                    return result["completion"]

                elif "titan" in model_id:
                    body = json.dumps({
                        "inputText": system_prompt + "\n\n" + user_prompt,
                        "textGenerationConfig": {"maxTokenCount": max_tokens, "temperature": 0.2}
                    })
                    r = self.bedrock_client.invoke_model(
                        modelId=model_id, body=body,
                        contentType="application/json", accept="application/json"
                    )
                    result = json.loads(r["body"].read())
                    return result["results"][0]["outputText"]

            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("AccessDeniedException", "ValidationException"):
                    continue
                raise
            except Exception:
                continue

        raise Exception("No Bedrock model available. Enable model access in AWS Console > Bedrock > Model access.")

    def analyze_report(self, report):
        if not self.is_available():
            return {"analysis": "AI unavailable.", "summary": "N/A", "priority_actions": []}
        prompt = self._build_analysis_prompt(report)
        try:
            text = self._call_bedrock(self._get_system_prompt(), prompt)
            clean = text.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                return {"analysis": text, "summary": text[:500], "priority_actions": []}
        except Exception as e:
            return {"analysis": "AI failed: " + str(e), "summary": "Error", "priority_actions": []}

    def troubleshoot_issue(self, issue_description, bucket_name, context=None):
        if not self.is_available():
            return "AI unavailable."
        ctx = json.dumps(context, indent=2, default=str) if context else "None"
        system = "You are an expert AWS S3 troubleshooting assistant. Provide step-by-step guidance with AWS CLI commands."
        user = "Bucket: " + bucket_name + "\nIssue: " + issue_description + "\nContext: " + ctx
        user += "\nProvide: 1) Root causes 2) Step-by-step fix 3) AWS CLI commands 4) Prevention"
        try:
            return self._call_bedrock(system, user, 3000)
        except Exception as e:
            return "Failed: " + str(e)

    def generate_policy_recommendation(self, bucket_name, use_case):
        if not self.is_available():
            return "AI unavailable."
        system = "You are an AWS S3 security expert. Generate secure bucket policies."
        user = "Generate a secure S3 bucket policy for bucket '" + bucket_name + "'. Use case: " + use_case
        try:
            return self._call_bedrock(system, user, 2000)
        except Exception as e:
            return "Failed: " + str(e)

    def _get_system_prompt(self):
        return """You are an expert AWS S3 troubleshooting AI. Analyze diagnostic results and provide actionable recommendations.

Respond in valid JSON with this structure:
{
    "summary": "Brief overall health summary",
    "health_assessment": "CRITICAL|POOR|FAIR|GOOD|EXCELLENT",
    "analysis": "Detailed analysis of all findings",
    "priority_actions": [
        {"priority": 1, "action": "What to do", "reason": "Why", "commands": ["aws cli command"]}
    ],
    "security_recommendations": ["rec1", "rec2"],
    "cost_optimization": ["tip1", "tip2"]
}"""

    def _build_analysis_prompt(self, report):
        items = [{"check": r.check_name, "status": r.status.value, "severity": r.severity.value, "message": r.message} for r in report.results]
        return "Analyze this S3 diagnostic report:\nBucket: " + report.bucket_name + " | Region: " + report.region + " | Score: " + str(report.score) + "/100\nResults: " + json.dumps(items, indent=2)
