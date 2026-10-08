"""Initialize private infrastructure only. Problem content is imported separately."""
import os
from pathlib import Path

import boto3
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.authtoken.models import Token
from competitions.models import Competition, Submission

os.umask(0o077)
s3 = boto3.client("s3", endpoint_url=os.environ["AWS_S3_ENDPOINT_URL"])
for bucket in ("public", "bundles"):
    try:
        s3.head_bucket(Bucket=bucket)
    except s3.exceptions.ClientError as exc:
        if str(exc.response["Error"]["Code"]) not in {"404", "NoSuchBucket"}:
            raise
        s3.create_bucket(Bucket=bucket)

with transaction.atomic():
    user, created = get_user_model().objects.get_or_create(username="oj-ai-service", defaults={"email": "oj-ai@localhost.invalid"})
    if created:
        user.set_unusable_password()
        user.save()
    token, _ = Token.objects.get_or_create(user=user)
    Path("/exports/coda-token").write_text(token.key + "\n")
    competitions = Competition.objects.filter(created_by=user)
    if Submission.objects.filter(phase__competition__in=competitions).exclude(status__in=["Finished", "Failed", "Cancelled"]).exists():
        raise ValueError("Drain Codabench before changing the evaluation image")
    competitions.update(docker_image=os.environ["XJU_EVALUATION_IMAGE"])
print("Private evaluation service initialized; import problem packages through OJ administration")
