from utils.api import UsernameSerializer, serializers

from utils.constants import ContestPrepRole, ContestPrepState
from .models import Contest, ContestAnnouncement, ContestPrepMember, ContestProblemFeedback, ContestRuleType
from .models import ACMContestRank, OIContestRank


class CreateConetestSeriaizer(serializers.Serializer):
    title = serializers.CharField(max_length=128)
    description = serializers.CharField(allow_blank=True)
    # Required for a normal contest; a preparation contest is scheduled when published.
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(required=False)
    rule_type = serializers.ChoiceField(choices=[ContestRuleType.ACM, ContestRuleType.OI, ContestRuleType.AI])
    password = serializers.CharField(allow_blank=True, max_length=32)
    visible = serializers.BooleanField()
    real_time_rank = serializers.BooleanField()
    allowed_ip_ranges = serializers.ListField(child=serializers.CharField(max_length=32), allow_empty=True)
    # Create a private preparation workspace instead of a normal contest.
    preparation = serializers.BooleanField(required=False, default=False)


class EditConetestSeriaizer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=128)
    description = serializers.CharField(allow_blank=True)
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    password = serializers.CharField(allow_blank=True, allow_null=True, max_length=32)
    visible = serializers.BooleanField()
    real_time_rank = serializers.BooleanField()
    allowed_ip_ranges = serializers.ListField(child=serializers.CharField(max_length=32))


class ContestAdminSerializer(serializers.ModelSerializer):
    created_by = UsernameSerializer()
    status = serializers.CharField()
    contest_type = serializers.CharField()

    class Meta:
        model = Contest
        fields = "__all__"


class ContestSerializer(ContestAdminSerializer):
    class Meta:
        model = Contest
        exclude = ("password", "visible", "allowed_ip_ranges", "published_from")


class ContestAnnouncementSerializer(serializers.ModelSerializer):
    created_by = UsernameSerializer()

    class Meta:
        model = ContestAnnouncement
        fields = "__all__"


class CreateContestAnnouncementSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    title = serializers.CharField(max_length=128)
    content = serializers.CharField()
    visible = serializers.BooleanField()


class EditContestAnnouncementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=128, required=False)
    content = serializers.CharField(required=False, allow_blank=True)
    visible = serializers.BooleanField(required=False)


class ContestPasswordVerifySerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    password = serializers.CharField(max_length=30, required=True)


class ContestRegistrationSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    password = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ACMContestRankSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = ACMContestRank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.is_contest_admin = kwargs.pop("is_contest_admin", False)
        super().__init__(*args, **kwargs)

    def get_user(self, obj):
        return UsernameSerializer(obj.user, need_real_name=self.is_contest_admin).data


class OIContestRankSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = OIContestRank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.is_contest_admin = kwargs.pop("is_contest_admin", False)
        super().__init__(*args, **kwargs)

    def get_user(self, obj):
        return UsernameSerializer(obj.user, need_real_name=self.is_contest_admin).data


class ACMContesHelperSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_id = serializers.CharField()
    rank_id = serializers.IntegerField()
    checked = serializers.BooleanField()


class ContestPrepStateSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    state = serializers.ChoiceField(choices=ContestPrepState.choices())


class ContestPrepMemberSerializer(serializers.ModelSerializer):
    # The team sees each other's real names on the members tab.
    user = UsernameSerializer(need_real_name=True)

    class Meta:
        model = ContestPrepMember
        fields = ("id", "user", "role", "create_time")


class CreateContestPrepMemberSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    username = serializers.CharField(max_length=32)
    role = serializers.ChoiceField(choices=[ContestPrepRole.SETTER, ContestPrepRole.VERIFIER])


class EditContestPrepMemberSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=[ContestPrepRole.SETTER, ContestPrepRole.VERIFIER])


class ContestPrepProblemOrderSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=500)


class ContestPrepProblemVisibleSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    id = serializers.IntegerField()
    visible = serializers.BooleanField()


class ContestPrepPublishSerializer(serializers.Serializer):
    """Optional overrides; omitted fields keep the preparation contest's values."""
    contest_id = serializers.IntegerField()
    title = serializers.CharField(max_length=128, required=False)
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(required=False)
    password = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    real_time_rank = serializers.BooleanField(required=False)


class ContestProblemFeedbackSerializer(serializers.ModelSerializer):
    user = UsernameSerializer()
    problem = serializers.SerializerMethodField()

    class Meta:
        model = ContestProblemFeedback
        fields = ("id", "user", "problem", "content", "resolved", "create_time")

    def get_problem(self, obj):
        return {"id": obj.problem_id, "_id": obj.problem._id, "title": obj.problem.title}


class CreateContestProblemFeedbackSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_id = serializers.IntegerField()
    content = serializers.CharField(max_length=2000)


class EditContestProblemFeedbackSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    id = serializers.IntegerField()
    resolved = serializers.BooleanField()


class CreateContestPrepInviteSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=[ContestPrepRole.SETTER, ContestPrepRole.VERIFIER])


class AcceptContestPrepInviteSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=16, max_length=128)


class ContestPrepPublicProblemSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_id = serializers.IntegerField()
