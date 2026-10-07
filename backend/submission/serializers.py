import math

from problem.models import RemoteOJ

from .models import RemoteSubmissionStatus, Submission
from utils.api import serializers
from utils.serializers import LanguageNameChoiceField


class CreateSubmissionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    language = LanguageNameChoiceField()
    code = serializers.CharField(max_length=1024 * 1024)
    contest_id = serializers.IntegerField(required=False)
    captcha = serializers.CharField(required=False)


class ShareSubmissionSerializer(serializers.Serializer):
    id = serializers.CharField()
    shared = serializers.BooleanField()


class RemoteStatisticField(serializers.Field):
    """Optional provider metrics must never prevent a final verdict landing."""

    def __init__(self, *, integer=False, **kwargs):
        self.integer = integer
        super().__init__(required=False, allow_null=True, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, bool):
            return None
        try:
            value = float(str(data).strip().removesuffix("%"))
        except (ValueError, TypeError, OverflowError):
            return None
        if not math.isfinite(value) or not 0 <= value <= 2 ** 53 - 1:
            return None
        if self.integer:
            return int(value) if value.is_integer() else None
        return value

    def to_representation(self, value):
        return value


class RemoteMessageField(serializers.CharField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.replace("\x00", "")[:2048]
        return super().to_internal_value(data)


class RemoteSubmissionEventSerializer(serializers.Serializer):
    submission_id = serializers.CharField(max_length=64)
    provider = serializers.ChoiceField(choices=RemoteOJ.choices())
    status = serializers.ChoiceField(choices=[
        RemoteSubmissionStatus.QUEUED,
        RemoteSubmissionStatus.OPENING,
        RemoteSubmissionStatus.AUTH_REQUIRED,
        RemoteSubmissionStatus.VERIFICATION_REQUIRED,
        RemoteSubmissionStatus.SUBMITTED,
        RemoteSubmissionStatus.JUDGING,
        RemoteSubmissionStatus.FINISHED,
        RemoteSubmissionStatus.FAILED,
    ])
    remote_submission_id = serializers.CharField(max_length=128, allow_blank=True, required=False)
    remote_url = serializers.URLField(max_length=1024, allow_blank=True, required=False)
    verdict = serializers.CharField(max_length=128, allow_blank=True, required=False)
    message = RemoteMessageField(max_length=2048, allow_blank=True, required=False)
    time_ms = RemoteStatisticField(integer=True)
    memory_bytes = RemoteStatisticField(integer=True)
    passed_tests = RemoteStatisticField(integer=True)
    total_tests = RemoteStatisticField(integer=True)
    score = RemoteStatisticField()
    failed_verdict = serializers.CharField(max_length=128, allow_blank=True, required=False)
    verification_source = serializers.CharField(max_length=64, allow_blank=True, required=False)


class SubmissionModelSerializer(serializers.ModelSerializer):

    class Meta:
        model = Submission
        fields = "__all__"


# 不显示submission info的serializer, 用于ACM rule_type
class SubmissionSafeModelSerializer(serializers.ModelSerializer):
    problem = serializers.SlugRelatedField(read_only=True, slug_field="_id")

    class Meta:
        model = Submission
        exclude = ("info", "contest", "ip")


class SubmissionListSerializer(serializers.ModelSerializer):
    problem = serializers.SlugRelatedField(read_only=True, slug_field="_id")
    show_link = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Submission
        exclude = ("info", "contest", "code", "ip")

    def get_show_link(self, obj):
        # 没传user或为匿名user
        if self.user is None or not self.user.is_authenticated:
            return False
        return obj.check_user_permission(self.user)
