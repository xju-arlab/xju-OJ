import re

from django import forms

from options.options import SysOptions
from utils.api import UsernameSerializer, serializers
from utils.constants import Difficulty
from utils.serializers import LanguageNameMultiChoiceField, SPJLanguageNameChoiceField, LanguageNameChoiceField

from .models import (Problem, ProblemRuleType, ProblemTag, ProblemIOMode,
                     ProblemJudgeMode, RemoteOJ)
from .utils import parse_problem_template


class TestCaseUploadForm(forms.Form):
    spj = forms.CharField(max_length=12)
    file = forms.FileField()


class CreateSampleSerializer(serializers.Serializer):
    input = serializers.CharField(trim_whitespace=False)
    output = serializers.CharField(trim_whitespace=False)


class CreateTestCaseScoreSerializer(serializers.Serializer):
    input_name = serializers.CharField(max_length=32)
    output_name = serializers.CharField(max_length=32)
    score = serializers.IntegerField(min_value=0)


class CreateProblemCodeTemplateSerializer(serializers.Serializer):
    pass


class ProblemIOModeSerializer(serializers.Serializer):
    io_mode = serializers.ChoiceField(choices=ProblemIOMode.choices())
    input = serializers.CharField()
    output = serializers.CharField()

    def validate(self, attrs):
        if attrs["input"] == attrs["output"]:
            raise serializers.ValidationError("Invalid io mode")
        for item in (attrs["input"], attrs["output"]):
            if not re.match("^[a-zA-Z0-9.]+$", item):
                raise serializers.ValidationError("Invalid io file name format")
        return attrs


class CreateOrEditProblemSerializer(serializers.Serializer):
    _id = serializers.CharField(max_length=32, allow_blank=True, allow_null=True,
                                required=False, default="")
    title = serializers.CharField(max_length=1024)
    description = serializers.CharField()
    input_description = serializers.CharField()
    output_description = serializers.CharField()
    samples = serializers.ListField(child=CreateSampleSerializer(), allow_empty=True)
    test_case_id = serializers.CharField(max_length=32, allow_blank=True)
    test_case_score = serializers.ListField(child=CreateTestCaseScoreSerializer(), allow_empty=True)
    time_limit = serializers.IntegerField(min_value=1, max_value=1000 * 60)
    memory_limit = serializers.IntegerField(min_value=1, max_value=1024)
    languages = LanguageNameMultiChoiceField()
    template = serializers.DictField(child=serializers.CharField(min_length=1))
    rule_type = serializers.ChoiceField(choices=[ProblemRuleType.ACM, ProblemRuleType.OI])
    io_mode = ProblemIOModeSerializer()
    spj = serializers.BooleanField()
    spj_language = SPJLanguageNameChoiceField(allow_blank=True, allow_null=True)
    spj_code = serializers.CharField(allow_blank=True, allow_null=True)
    spj_compile_ok = serializers.BooleanField(default=False)
    visible = serializers.BooleanField()
    difficulty = serializers.ChoiceField(choices=Difficulty.choices())
    tags = serializers.ListField(child=serializers.CharField(max_length=32), allow_empty=False)
    hint = serializers.CharField(allow_blank=True, allow_null=True)
    source = serializers.CharField(max_length=256, allow_blank=True, allow_null=True)
    share_submission = serializers.BooleanField()
    judge_mode = serializers.ChoiceField(choices=ProblemJudgeMode.choices(), default=ProblemJudgeMode.LOCAL)
    remote_oj = serializers.ChoiceField(choices=RemoteOJ.choices(), allow_null=True, required=False, default=None)
    remote_problem_id = serializers.CharField(max_length=128, allow_blank=True, allow_null=True,
                                              required=False, default=None)
    remote_problem_data = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        if attrs["judge_mode"] == ProblemJudgeMode.REMOTE:
            if not attrs.get("remote_oj") or not attrs.get("remote_problem_id"):
                raise serializers.ValidationError("Remote judge metadata is required")
            if attrs["rule_type"] != ProblemRuleType.ACM:
                raise serializers.ValidationError("Remote judge currently supports ACM problems only")
            if attrs["spj"]:
                raise serializers.ValidationError("Remote judge problem cannot use local SPJ")
        else:
            if not attrs["samples"]:
                raise serializers.ValidationError("Sample is required")
            if not attrs["test_case_id"]:
                raise serializers.ValidationError("Test case is required")
            attrs["remote_oj"] = None
            attrs["remote_problem_id"] = None
            attrs["remote_problem_data"] = {}
        return attrs


class CreateProblemSerializer(CreateOrEditProblemSerializer):
    pass


class EditProblemSerializer(CreateOrEditProblemSerializer):
    id = serializers.IntegerField()


class CreateContestProblemSerializer(CreateOrEditProblemSerializer):
    contest_id = serializers.IntegerField()


class EditContestProblemSerializer(CreateOrEditProblemSerializer):
    id = serializers.IntegerField()
    contest_id = serializers.IntegerField()


class CreatePrepContestProblemSerializer(CreateContestProblemSerializer):
    # Problems uploaded while preparing a contest start hidden as drafts.
    visible = serializers.BooleanField(required=False, default=False)


class EditPrepContestProblemSerializer(EditContestProblemSerializer):
    pass


class RemoteProblemImportSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=RemoteOJ.choices())
    remote_id = serializers.CharField(max_length=512)
    contest_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    page_html = serializers.CharField(max_length=2 * 1024 * 1024, allow_blank=True,
                                      required=False, default="", trim_whitespace=False)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProblemTag
        fields = "__all__"


class CompileSPJSerializer(serializers.Serializer):
    spj_language = SPJLanguageNameChoiceField()
    spj_code = serializers.CharField()


class BaseProblemSerializer(serializers.ModelSerializer):
    tags = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    created_by = UsernameSerializer()

    def get_public_template(self, obj):
        ret = {}
        for lang, code in obj.template.items():
            ret[lang] = parse_problem_template(code)["template"]
        return ret


class ProblemAdminSerializer(BaseProblemSerializer):
    class Meta:
        model = Problem
        fields = "__all__"


class ProblemSerializer(BaseProblemSerializer):
    template = serializers.SerializerMethodField("get_public_template")

    class Meta:
        model = Problem
        exclude = ("test_case_score", "test_case_id", "visible", "is_public",
                   "spj_code", "spj_version", "spj_compile_ok", "remote_problem_data")


class ProblemSafeSerializer(BaseProblemSerializer):
    template = serializers.SerializerMethodField("get_public_template")

    class Meta:
        model = Problem
        exclude = ("test_case_score", "test_case_id", "visible", "is_public",
                   "spj_code", "spj_version", "spj_compile_ok",
                   "difficulty", "submission_number", "accepted_number", "statistic_info",
                   "remote_problem_data")


class ContestProblemMakePublicSerializer(serializers.Serializer):
    id = serializers.IntegerField()


class ExportProblemSerializer(serializers.ModelSerializer):
    display_id = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    input_description = serializers.SerializerMethodField()
    output_description = serializers.SerializerMethodField()
    test_case_score = serializers.SerializerMethodField()
    hint = serializers.SerializerMethodField()
    spj = serializers.SerializerMethodField()
    template = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    tags = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)

    def get_display_id(self, obj):
        return obj._id

    def _html_format_value(self, value):
        return {"format": "html", "value": value}

    def get_description(self, obj):
        return self._html_format_value(obj.description)

    def get_input_description(self, obj):
        return self._html_format_value(obj.input_description)

    def get_output_description(self, obj):
        return self._html_format_value(obj.output_description)

    def get_hint(self, obj):
        return self._html_format_value(obj.hint)

    def get_test_case_score(self, obj):
        return [{"score": item["score"] if obj.rule_type == ProblemRuleType.OI else 100,
                 "input_name": item["input_name"], "output_name": item["output_name"]}
                for item in obj.test_case_score]

    def get_spj(self, obj):
        return {"code": obj.spj_code,
                "language": obj.spj_language} if obj.spj else None

    def get_template(self, obj):
        ret = {}
        for k, v in obj.template.items():
            ret[k] = parse_problem_template(v)
        return ret

    def get_source(self, obj):
        return obj.source or f"{SysOptions.website_name} {SysOptions.website_base_url}"

    class Meta:
        model = Problem
        fields = ("display_id", "title", "description", "tags",
                  "input_description", "output_description",
                  "test_case_score", "hint", "time_limit", "memory_limit", "samples",
                  "template", "spj", "rule_type", "source", "difficulty", "visible",
                  "languages")


class AddContestProblemSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_id = serializers.IntegerField()


class ExportProblemRequestSerialzier(serializers.Serializer):
    problem_id = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class UploadProblemForm(forms.Form):
    file = forms.FileField()


class FormatValueSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["html", "markdown"])
    value = serializers.CharField(allow_blank=True)


class TestCaseScoreSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=1)
    input_name = serializers.CharField(max_length=32)
    output_name = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")


class TemplateSerializer(serializers.Serializer):
    prepend = serializers.CharField()
    template = serializers.CharField()
    append = serializers.CharField()


class SPJSerializer(serializers.Serializer):
    code = serializers.CharField()
    language = SPJLanguageNameChoiceField()


class AnswerSerializer(serializers.Serializer):
    code = serializers.CharField()
    language = LanguageNameChoiceField()


class ImportProblemSerializer(serializers.Serializer):
    display_id = serializers.CharField(
        max_length=128, allow_blank=True, required=False, default=""
    )
    title = serializers.CharField(max_length=128)
    description = FormatValueSerializer()
    input_description = FormatValueSerializer()
    output_description = FormatValueSerializer()
    hint = FormatValueSerializer()
    test_case_score = serializers.ListField(
        child=TestCaseScoreSerializer(), allow_null=True, required=False, default=list
    )
    time_limit = serializers.IntegerField(min_value=1, max_value=60000)
    memory_limit = serializers.IntegerField(min_value=1, max_value=10240)
    samples = serializers.ListField(child=CreateSampleSerializer())
    template = serializers.DictField(child=TemplateSerializer())
    spj = SPJSerializer(allow_null=True)
    rule_type = serializers.ChoiceField(choices=ProblemRuleType.choices())
    source = serializers.CharField(max_length=200, allow_blank=True, allow_null=True)
    answers = serializers.ListField(child=AnswerSerializer(), required=False, default=list)
    tags = serializers.ListField(child=serializers.CharField(max_length=32), required=False, default=list)
    difficulty = serializers.ChoiceField(
        choices=Difficulty.choices(), required=False, default=Difficulty.MID
    )
    visible = serializers.BooleanField(required=False, default=False)
    languages = LanguageNameMultiChoiceField(required=False, allow_empty=False)


class FPSProblemSerializer(serializers.Serializer):
    class UnitSerializer(serializers.Serializer):
        unit = serializers.ChoiceField(choices=["MB", "s", "ms"])
        value = serializers.IntegerField(min_value=1, max_value=60000)

    title = serializers.CharField(max_length=128)
    description = serializers.CharField()
    input = serializers.CharField()
    output = serializers.CharField()
    hint = serializers.CharField(allow_blank=True, allow_null=True)
    time_limit = UnitSerializer()
    memory_limit = UnitSerializer()
    samples = serializers.ListField(child=CreateSampleSerializer())
    source = serializers.CharField(max_length=200, allow_blank=True, allow_null=True)
    spj = SPJSerializer(allow_null=True)
    template = serializers.ListField(child=serializers.DictField(), allow_empty=True, allow_null=True)
    append = serializers.ListField(child=serializers.DictField(), allow_empty=True, allow_null=True)
    prepend = serializers.ListField(child=serializers.DictField(), allow_empty=True, allow_null=True)


class ProblemFavoriteSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()


class ProfileProblemSerializer(serializers.ModelSerializer):
    tags = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)

    class Meta:
        model = Problem
        fields = ("id", "_id", "title", "difficulty", "rule_type", "tags",
                  "submission_number", "accepted_number", "create_time")
