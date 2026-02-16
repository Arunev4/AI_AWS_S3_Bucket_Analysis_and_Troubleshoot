"""AI Engine - AWS Bedrock + OpenAI fallback."""

import json
import os
import boto3
from botocore.exceptions import ClientError
from rich.console import Console
from src.models import BucketReport, CheckStatus

console = Console()


class AIEngine:
    def __init__(self, api_key=None, model="gpt-4", region="us-east-1", profile=None, provider=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.region = region
        self.profile = profile
        self.provider = provider  # "bedrock", "openai", or None (auto-detect)
        self.openai_client = None
        self.bedrock_client = None

        # Auto-detect: try Bedrock first, then OpenAI
        if self.provider in (None, "bedrock"):
            try:
                kw = {}
                if self.profile:
                    kw["profile_name"] = self.profile
                session = boto3.Session(**kw)
                self.bedrock_client = session.client(
                    "bedrock-runtime",
                    region_name=self.region
                )
                # Quick test
                self.bedrock_client.meta.endpoint_url
                self.provider = "bedrock"
                console.print("[green]AI Engine: Using AWS Bedrock[/green]")
            except Exception as e:
                console.print("[yellow]Bedrock not available: " + str(e)[:100] + "[/yellow]")
                self.bedrock_client = None

        if self.provider != "bedrock" and self.api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.api_key)
                self.provider = "openai"
                console.print("[green]AI Engine: Using OpenAI[/green]")
            except ImportError:
                pass

        if not self.provider:
            self.provider = "none"

    def is_available(self):
        return self.provider in ("bedrock", "openai")

    def _call_bedrock(self, system_prompt, user_prompt, max_tokens=4000):
        """Call AWS Bedrock Claude model."""
        # Try Claude models in order of preference
        models_to_try = [
            "anthropic.claude-3-sonnet-20240229-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "anthropic.claude-v2:1",
            "anthropic.claude-v2",
            "anthropic.claude-instant-v1",
            "amazon.titan-text-express-v1",
        ]

        for model_id in models_to_try:
            try:
                if model_id.startswith("anthropic.claude-3"):
                    # Claude 3 Messages API
                    body = json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": [
                            {"role": "user", "content": user_prompt}
                        ]
                    })
                    response = self.bedrock_client.invoke_model(
                        modelId=model_id,
                        body=body,
                        contentType="application/json",
                        accept="application/json"
                    )
                    result = json.loads(response["body"].read())
                    return result["content"][0]["text"]

                elif model_id.startswith("anthropic.claude"):
                    # Claude 2 Text Completions API
                    body = json.dumps({
                        "prompt": "\n\nHuman: " + system_prompt + "\n\n" + user_prompt + "\n\nAssistant:",
                        "max_tokens_to_sample": max_tokens,
                        "temperature": 0.2,
                    })
                    response = self.bedrock_client.invoke_model(
                        modelId=model_id,
                        body=body,
                        contentType="application/json",
                        accept="application/json"
                    )
                    result = json.loads(response["body"].read())
                    return result["completion"]

                elif model_id.startswith("amazon.titan"):
                    # Titan API
                    body = json.dumps({
                        "inputText": system_prompt + "\n\n" + user_prompt,
                        "textGenerationConfig": {
                            "maxTokenCount": max_tokens,
                            "temperature": 0.2,
                        }
                    })
                    response = self.bedrock_client.invoke_model(
                        modelId=model_id,
                        body=body,
                        contentType="application/json",
                        accept="application/json"
                    )
                    result = json.loads(response["body"].read())
                    return result["results"][0]["outputText"]

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("AccessDeniedException", "ValidationException"):
                    continue  # Try next model
                raise
            except Exception:
                continue  # Try next model

        raise Exception("No Bedrock model available. Enable model access in AWS Console > Bedrock > Model access.")

    def _call_openai(self, system_prompt, user_prompt, max_tokens=4000):
        """Call OpenAI API."""
        response = self.openai_client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        return response.choices[0].message.content

    def _call_ai(self, system_prompt, user_prompt, max_tokens=4000):
        """Route to available provider."""
        if self.provider == "bedrock":
            return self._call_bedrock(system_prompt, user_prompt, max_tokens)
        elif self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt, max_tokens)
        else:
            return "AI unavailable."

    def analyze_report(self, report):
        if not self.is_available():
            return {"analysis": "AI analysis unavailable (no provider).", "summary": "N/A", "priority_actions": []}
        prompt = self._build_analysis_prompt(report)
        try:
            text = self._call_ai(self._get_system_prompt(), prompt)
            # Strip markdown code fences if present
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
            return "AI analysis unavailable."
        ctx = json.dumps(context, indent=2, default=str) if context else "None"
        system = "You are an expert AWS S3 troubleshooting assistant. Provide step-by-step guidance with AWS CLI commands."
        user = "Bucket: " + bucket_name + "\nIssue: " + issue_description + "\nContext: " + ctx
        user += "\n\nProvide: 1) Root causes 2) Step-by-step fix 3) AWS CLI commands 4) Prevention"
        try:
            return self._call_ai(system, user, 3000)
        except Exception as e:
            return "Failed: " + str(e)

    def generate_policy_recommendation(self, bucket_name, use_case):
        if not self.is_available():
            return "AI unavailable."
        system = "You are an AWS S3 security expert. Generate secure, least-privilege bucket policies."
        user = "Generate a secure S3 bucket policy for bucket '" + bucket_name + "'. Use case: " + use_case
        try:
            return self._call_ai(system, user, 2000)
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
    "security_recommendations": ["recommendation 1", "recommendation 2"],
    "cost_optimization": ["tip 1", "tip 2"]
}"""

    def _build_analysis_prompt(self, report):
        items = [{"check": r.check_name, "status": r.status.value, "severity": r.severity.value, "message": r.message} for r in report.results]
        return "Analyze this S3 diagnostic report:\nBucket: " + report.bucket_name + " | Region: " + report.region + " | Score: " + str(report.score) + "/100\nResults: " + json.dumps(items, indent=2)
