from django.urls import re_path

from ..views.admin import SubmissionRejudgeAPI

urlpatterns = [
    re_path(r"^submission/rejudge/?$", SubmissionRejudgeAPI.as_view(), name="submission_rejudge_api"),
]
