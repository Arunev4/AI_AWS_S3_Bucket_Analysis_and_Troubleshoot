"""AWS S3 Client Wrapper."""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional


class S3Client:
    def __init__(self, region="us-east-1", profile=None):
        self.region = region
        self.profile = profile
        self._client = None
        self._sts_client = None

    @property
    def client(self):
        if self._client is None:
            kw = {}
            if self.profile:
                kw["profile_name"] = self.profile
            self._client = boto3.Session(**kw).client("s3", region_name=self.region)
        return self._client

    @property
    def sts_client(self):
        if self._sts_client is None:
            kw = {}
            if self.profile:
                kw["profile_name"] = self.profile
            self._sts_client = boto3.Session(**kw).client("sts")
        return self._sts_client

    def verify_credentials(self):
        try:
            i = self.sts_client.get_caller_identity()
            return {"valid": True, "account": i["Account"], "arn": i["Arn"], "user_id": i["UserId"]}
        except (NoCredentialsError, ClientError) as e:
            return {"valid": False, "error": str(e)}

    def bucket_exists(self, bucket_name):
        try:
            self.client.head_bucket(Bucket=bucket_name)
            return {"exists": True, "accessible": True}
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "404":
                return {"exists": False, "accessible": False, "error": "Bucket not found"}
            elif code == "403":
                return {"exists": True, "accessible": False, "error": "Access denied"}
            return {"exists": False, "accessible": False, "error": str(e)}

    def get_bucket_location(self, bucket_name):
        try:
            r = self.client.get_bucket_location(Bucket=bucket_name)
            loc = r.get("LocationConstraint")
            return loc if loc else "us-east-1"
        except ClientError:
            return None

    def get_bucket_policy(self, bucket_name):
        try:
            r = self.client.get_bucket_policy(Bucket=bucket_name)
            return {"exists": True, "policy": r["Policy"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                return {"exists": False, "policy": None}
            return {"exists": False, "error": str(e)}

    def get_bucket_acl(self, bucket_name):
        try:
            r = self.client.get_bucket_acl(Bucket=bucket_name)
            return {"success": True, "owner": r["Owner"], "grants": r["Grants"]}
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def get_public_access_block(self, bucket_name):
        try:
            r = self.client.get_public_access_block(Bucket=bucket_name)
            return {"exists": True, "config": r["PublicAccessBlockConfiguration"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
                return {"exists": False, "config": None}
            return {"exists": False, "error": str(e)}

    def get_bucket_encryption(self, bucket_name):
        try:
            r = self.client.get_bucket_encryption(Bucket=bucket_name)
            return {"enabled": True, "rules": r["ServerSideEncryptionConfiguration"]["Rules"]}
        except ClientError as e:
            if "ServerSideEncryptionConfigurationNotFoundError" in str(e):
                return {"enabled": False, "rules": []}
            return {"enabled": False, "error": str(e)}

    def get_bucket_versioning(self, bucket_name):
        try:
            r = self.client.get_bucket_versioning(Bucket=bucket_name)
            return {"status": r.get("Status", "Disabled"), "mfa_delete": r.get("MFADelete", "Disabled")}
        except ClientError as e:
            return {"status": "Unknown", "error": str(e)}

    def get_lifecycle_rules(self, bucket_name):
        try:
            r = self.client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
            return {"exists": True, "rules": r["Rules"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchLifecycleConfiguration":
                return {"exists": False, "rules": []}
            return {"exists": False, "error": str(e)}

    def get_cors_configuration(self, bucket_name):
        try:
            r = self.client.get_bucket_cors(Bucket=bucket_name)
            return {"exists": True, "rules": r["CORSRules"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchCORSConfiguration":
                return {"exists": False, "rules": []}
            return {"exists": False, "error": str(e)}

    def get_bucket_logging(self, bucket_name):
        try:
            r = self.client.get_bucket_logging(Bucket=bucket_name)
            lc = r.get("LoggingEnabled")
            return {"enabled": lc is not None, "config": lc}
        except ClientError as e:
            return {"enabled": False, "error": str(e)}

    def get_bucket_replication(self, bucket_name):
        try:
            r = self.client.get_bucket_replication(Bucket=bucket_name)
            return {"enabled": True, "config": r["ReplicationConfiguration"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "ReplicationConfigurationNotFoundError":
                return {"enabled": False, "config": None}
            return {"enabled": False, "error": str(e)}

    def get_object_lock_configuration(self, bucket_name):
        try:
            r = self.client.get_object_lock_configuration(Bucket=bucket_name)
            return {"enabled": True, "config": r["ObjectLockConfiguration"]}
        except ClientError as e:
            if "ObjectLockConfigurationNotFoundError" in str(e):
                return {"enabled": False, "config": None}
            return {"enabled": False, "error": str(e)}

    def get_transfer_acceleration(self, bucket_name):
        try:
            r = self.client.get_bucket_accelerate_configuration(Bucket=bucket_name)
            s = r.get("Status", "Suspended")
            return {"enabled": s == "Enabled", "status": s}
        except ClientError as e:
            return {"enabled": False, "error": str(e)}

    def get_bucket_tagging(self, bucket_name):
        try:
            r = self.client.get_bucket_tagging(Bucket=bucket_name)
            return {"exists": True, "tags": r["TagSet"]}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchTagSet":
                return {"exists": False, "tags": []}
            return {"exists": False, "error": str(e)}

    def list_buckets(self):
        try:
            r = self.client.list_buckets()
            return [b["Name"] for b in r["Buckets"]]
        except ClientError:
            return []

    def get_bucket_size_estimate(self, bucket_name, max_keys=1000):
        try:
            p = self.client.get_paginator("list_objects_v2")
            ts = 0
            tc = 0
            for page in p.paginate(Bucket=bucket_name, PaginationConfig={"MaxItems": max_keys}):
                for obj in page.get("Contents", []):
                    ts += obj["Size"]
                    tc += 1
            return {"success": True, "total_size_bytes": ts, "total_size_mb": round(ts / (1024*1024), 2), "object_count": tc, "sampled": tc >= max_keys}
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def enable_versioning(self, bucket_name):
        try:
            self.client.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"})
            return {"success": True, "message": "Versioning enabled"}
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def enable_encryption(self, bucket_name, algo="AES256"):
        try:
            c = {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": algo}}]}
            self.client.put_bucket_encryption(Bucket=bucket_name, ServerSideEncryptionConfiguration=c)
            return {"success": True, "message": "Encryption enabled with " + algo}
        except ClientError as e:
            return {"success": False, "error": str(e)}

    def block_public_access(self, bucket_name):
        try:
            self.client.put_public_access_block(Bucket=bucket_name, PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
            return {"success": True, "message": "Public access blocked"}
        except ClientError as e:
            return {"success": False, "error": str(e)}
