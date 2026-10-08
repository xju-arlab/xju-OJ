"""AI work is separate from the ACM/OI submission and statistics tables."""
import uuid

from django.conf import settings
from django.db import models


class AIProblem(models.Model):
    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=128)
    category = models.CharField(max_length=16, choices=[(v, v) for v in ("logic", "model", "challenge")])
    # Public statement and starter only. Judge configuration never goes to students.
    statement = models.JSONField(default=dict)
    cells = models.JSONField(default=list)
    public_files = models.JSONField(default=dict)
    metric = models.CharField(max_length=64, default="Score")
    points = models.PositiveIntegerField(default=100)
    visible = models.BooleanField(default=False)
    judge = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
    package_import = models.ForeignKey("AIProblemImport", null=True, on_delete=models.PROTECT, related_name="problems")
    package_index = models.PositiveSmallIntegerField(null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)


class AIContestConfig(models.Model):
    contest = models.OneToOneField("contest.Contest", on_delete=models.CASCADE, related_name="ai_config")
    selection = models.CharField(max_length=8, default="latest", choices=[("latest", "latest"), ("best", "best")])
    private_published = models.BooleanField(default=False)
    practice_enabled = models.BooleanField(default=True)


class AIContestProblem(models.Model):
    contest = models.ForeignKey("contest.Contest", on_delete=models.CASCADE, related_name="ai_problems")
    problem = models.ForeignKey(AIProblem, on_delete=models.PROTECT)
    position = models.PositiveIntegerField()
    points = models.PositiveIntegerField(default=20)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("contest", "problem"), name="ai_contest_problem_unique"),
            models.UniqueConstraint(fields=("contest", "position"), name="ai_contest_position_unique"),
        ]


class AIDraft(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    problem = models.ForeignKey(AIProblem, on_delete=models.CASCADE)
    scope = models.CharField(max_length=32, default="practice")
    cells = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "problem", "scope"), name="ai_draft_scope_unique")]


class AIJob(models.Model):
    """The database is the durable queue; claims and results are fenced by a lease."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    problem = models.ForeignKey(AIProblem, on_delete=models.PROTECT)
    contest = models.ForeignKey("contest.Contest", null=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=[("notebook", "notebook"), ("evaluation", "evaluation")])
    official = models.BooleanField(default=False)
    category = models.CharField(max_length=16)
    problem_version = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    source_sha256 = models.CharField(max_length=64)
    judge = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default="PENDING", db_index=True)
    public_score = models.FloatField(null=True)
    private_score = models.FloatField(null=True)
    accuracy = models.FloatField(null=True)
    output = models.JSONField(default=dict)
    message = models.CharField(max_length=512, blank=True)
    remote_id = models.PositiveBigIntegerField(null=True)
    dispatch_started = models.BooleanField(default=False)
    worker = models.CharField(max_length=64, blank=True)
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("contest", "official", "user"), name="ai_official_user_idx")]


class AIWorker(models.Model):
    name = models.CharField(max_length=64, primary_key=True)
    kinds = models.JSONField(default=list)
    last_seen = models.DateTimeField()


class AIServiceState(models.Model):
    # One durable admission gate. Existing jobs continue to drain while paused.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    paused = models.BooleanField(default=False)


class AIProblemImport(models.Model):
    """Private archive plus durable, retryable registration of a whole problem batch."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source_sha256 = models.CharField(max_length=64)
    filename = models.CharField(max_length=128)
    manifest = models.JSONField(default=list)  # Public content/configuration and hashes; private assets stay in the ZIP.
    status = models.CharField(max_length=16, default="PREVIEW", db_index=True)
    publish = models.BooleanField(default=False)
    result = models.JSONField(default=list)
    message = models.CharField(max_length=256, blank=True)
    worker = models.CharField(max_length=64, blank=True)
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=("created_by", "source_sha256"), name="ai_import_owner_digest_unique")]
