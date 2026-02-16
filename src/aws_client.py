"""AWS S3 Client Wrapper with error handling and caching."""

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    EndpointConnectionError,
    BotoCoreError,
)
from rich.console import Console
from typing import Optional

console = Console()


class S3Client:
    """Thread-safe S3 client wrapper with built-in error handling."""

    def __init__(self, region: str = "us-east-1", profile: Optional[str] = None):
        self.region = region
        self.profile = profile
        self._client = None
        self._resource = None
        self._sts_client = None
        self._cache = {}

    @property
    def client(self):
        if self._client is None:
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
            session = boto3.Session(**session_kwargs)
            self._client = session.client("s3", region_name=self.region)
        return self._client

    @property
    def resource(self):
        if self._resource is None:
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
            session = boto3.Session(**session_kwargs)
            self._resource = session.resource("s3", region_name=self.region)
        return self._resource

    @property
    def sts_client(self):
        if self._sts_client is None:
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
            session = boto3.Session(**session_kwargs)
            self._sts_client = session.client("sts")
        return self._sts_client

    def verify_credentials(self) -> dict:
        """Verify AWS credentials are valid."""
        try:
            identity = self.sts_client.get_caller_identity()
            return {
                "valid": True,
                "account": identity["Account"],
                "arn": identity["Arn"],
                "user_id": identity["UserId"],
            }
        except (NoCredentialsError, ClientError) as e:
            return {"valid": False, "error": str(e)}

    def bucket_exists(self, bucket_name: str) -> dict:
        """Check if bucket exists and is accessible."""
        try:
            self.client.head_bucket(Bucket=bucket_name)
            return {"exists": True, "accessible": True}
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "404":
                return {
                    "exists": False,
                    "accessible": False,
                    "error": "Bucket not found",
                }
            elif code == "403":
                return {"exists": True, "accessible": False, "error": "Access denied"}
            return {"exists": False, "accessible": False, "error": str(e)}

    def get_bucket_location(self, bucket_name: str) -> Optional[str]:
        try:
            response = self.client.get_bucket_location(Bucket=bucket_name)
            location = response.get("LocationConstraint")
            return location if location else "us-east-1"
        except ClientError:
            return None

    def get_bucket_policy(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_policy(Bucket=bucket_name)
            return {"exists": True, "policy": response["Policy"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                return {"exists": False, "policy": None}
            return {"exists": False, "error": str(e)}

    def get_bucket_acl(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_acl(Bucket=bucket_name)
            return {
                "success": True,
                "owner": response["Owner"],
                "grants": response["Grants"],
            }
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def get_public_access_block(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_public_access_block(Bucket=bucket_name)
            return {
                "exists": True,
                "config": response["PublicAccessBlockConfiguration"],
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
                return {"exists": False, "config": None}
            return {"exists": False, "error": str(e)}

    def get_bucket_encryption(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_encryption(Bucket=bucket_name)
            rules = response["ServerSideEncryptionConfiguration"]["Rules"]
            return {"enabled": True, "rules": rules}
        except ClientError as e:
            if "ServerSideEncryptionConfigurationNotFoundError" in str(e):
                return {"enabled": False, "rules": []}
            return {"enabled": False, "error": str(e)}

    def get_bucket_versioning(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_versioning(Bucket=bucket_name)
            return {
                "status": response.get("Status", "Disabled"),
                "mfa_delete": response.get("MFADelete", "Disabled"),
            }
        except ClientError as e:
            return {"status": "Unknown", "error": str(e)}

    def get_lifecycle_rules(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_lifecycle_configuration(
                Bucket=bucket_name
            )
            return {"exists": True, "rules": response["Rules"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchLifecycleConfiguration":
                return {"exists": False, "rules": []}
            return {"exists": False, "error": str(e)}

    def get_cors_configuration(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_cors(Bucket=bucket_name)
            return {"exists": True, "rules": response["CORSRules"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchCORSConfiguration":
                return {"exists": False, "rules": []}
            return {"exists": False, "error": str(e)}

    def get_bucket_logging(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_logging(Bucket=bucket_name)
            logging_config = response.get("LoggingEnabled")
            return {"enabled": logging_config is not None, "config": logging_config}
        except ClientError as e:
            return {"enabled": False, "error": str(e)}

    def get_bucket_replication(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_replication(Bucket=bucket_name)
            return {"enabled": True, "config": response["ReplicationConfiguration"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "ReplicationConfigurationNotFoundError":
                return {"enabled": False, "config": None}
            return {"enabled": False, "error": str(e)}

    def get_object_lock_configuration(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_object_lock_configuration(Bucket=bucket_name)
            return {"enabled": True, "config": response["ObjectLockConfiguration"]}
        except ClientError as e:
            if "ObjectLockConfigurationNotFoundError" in str(e):
                return {"enabled": False, "config": None}
            return {"enabled": False, "error": str(e)}

    def get_transfer_acceleration(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_accelerate_configuration(
                Bucket=bucket_name
            )
            status = response.get("Status", "Suspended")
            return {"enabled": status == "Enabled", "status": status}
        except ClientError as e:
            return {"enabled": False, "error": str(e)}

    def get_bucket_tagging(self, bucket_name: str) -> dict:
        try:
            response = self.client.get_bucket_tagging(Bucket=bucket_name)
            return {"exists": True, "tags": response["TagSet"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchTagSet":
                return {"exists": False, "tags": []}
            return {"exists": False, "error": str(e)}

    def list_buckets(self) -> list:
        try:
            response = self.client.list_buckets()
            return [b["Name"] for b in response["Buckets"]]
        except ClientError as e:
            console.print(f"[red]Error listing buckets: {e}[/red]")
            return []

    def get_bucket_size_estimate(self, bucket_name: str, max_keys: int = 1000) -> dict:
        """Get approximate bucket size by sampling objects."""
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            total_size = 0
            total_objects = 0

            for page in paginator.paginate(
                Bucket=bucket_name, PaginationConfig={"MaxItems": max_keys}
            ):
                for obj in page.get("Contents", []):
                    total_size += obj["Size"]
                    total_objects += 1

            return {
                "success": True,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "object_count": total_objects,
                "sampled": total_objects >= max_keys,
            }
        except ClientError as e:
            return {"success": False, "error": str(e)}

    # ---- REMEDIATION METHODS ----

    def enable_versioning(self, bucket_name: str) -> dict:
        try:
            self.client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={"Status": "Enabled"},
            )
            return {"success": True, "message": "Versioning enabled"}
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def enable_encryption(
        self, bucket_name: str, sse_algorithm: str = "AES256"
    ) -> dict:
        try:
            config = {
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": sse_algorithm
                        }
                    }
                ]
            }
            self.client.put_bucket_encryption(
                Bucket=bucket_name,
                ServerSideEncryptionConfiguration=config,
            )
            return {
                "success": True,
                "message": f"Encryption enabled with {sse_algorithm}",
            }
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def block_public_access(self, bucket_name: str) -> dict:
        try:
            self.client.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
            return {"success": True, "message": "Public access blocked"}
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def enable_logging(
        self, bucket_name: str, target_bucket: str, prefix: str = "logs/"
    ) -> dict:
        try:
            self.client.put_bucket_logging(
                Bucket=bucket_name,
                BucketLoggingStatus={
                    "LoggingEnabled": {
                        "TargetBucket": target_bucket,
                        "TargetPrefix": prefix,
                    }
                },
            )
            return {"success": True, "message": "Logging enabled"}
        except ClientError as e:
            return {"success": False, "error": str(e)}
