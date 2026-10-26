from django.urls import re_path

from ..views.oj import ContestAnnouncementListAPI
from ..views.oj import ContestPasswordVerifyAPI, ContestAccessAPI
from ..views.oj import ContestRegistrationAPI
from ..views.oj import ContestListAPI, ContestAPI
from ..views.oj import ContestRankAPI
from ..views.prep import (ContestPrepCompileSPJAPI, ContestPrepFeedbackAPI, ContestPrepImportProblemAPI,
                          ContestPrepInviteAcceptAPI, ContestPrepInviteAPI, ContestPrepMemberAPI,
                          ContestPrepPlanAPI, ContestPrepProblemAPI, ContestPrepProblemCountAPI,
                          ContestPrepProblemOrderAPI, ContestPrepPublicProblemAPI,
                          ContestPrepPublishAPI, ContestPrepRankAPI, ContestPrepReviewAPI,
                          ContestPrepTestCaseAPI, ContestPrepUserSearchAPI)

urlpatterns = [
    re_path(r"^contests/?$", ContestListAPI.as_view(), name="contest_list_api"),
    re_path(r"^contest/?$", ContestAPI.as_view(), name="contest_api"),
    re_path(r"^contest/password/?$", ContestPasswordVerifyAPI.as_view(), name="contest_password_api"),
    re_path(r"^contest/announcement/?$", ContestAnnouncementListAPI.as_view(), name="contest_announcement_api"),
    re_path(r"^contest/access/?$", ContestAccessAPI.as_view(), name="contest_access_api"),
    re_path(r"^contest/register/?$", ContestRegistrationAPI.as_view(), name="contest_registration_api"),
    re_path(r"^contest_rank/?$", ContestRankAPI.as_view(), name="contest_rank_api"),
    # Contest preparation workspace (the creator and organizers).
    re_path(r"^contest/prep/review/?$", ContestPrepReviewAPI.as_view(), name="contest_prep_review_api"),
    re_path(r"^contest/prep/members/?$", ContestPrepMemberAPI.as_view(), name="contest_prep_member_api"),
    re_path(r"^contest/prep/members/search/?$", ContestPrepUserSearchAPI.as_view(),
            name="contest_prep_user_search_api"),
    re_path(r"^contest/prep/problem/?$", ContestPrepProblemAPI.as_view(), name="contest_prep_problem_api"),
    re_path(r"^contest/prep/plan/?$", ContestPrepPlanAPI.as_view(), name="contest_prep_plan_api"),
    re_path(r"^contest/prep/problem_count/?$", ContestPrepProblemCountAPI.as_view(),
            name="contest_prep_problem_count_api"),
    re_path(r"^contest/prep/problem/order/?$", ContestPrepProblemOrderAPI.as_view(),
            name="contest_prep_problem_order_api"),
    re_path(r"^contest/prep/problem/from_public/?$", ContestPrepPublicProblemAPI.as_view(),
            name="contest_prep_public_problem_api"),
    re_path(r"^contest/prep/test_case/?$", ContestPrepTestCaseAPI.as_view(), name="contest_prep_test_case_api"),
    re_path(r"^contest/prep/compile_spj/?$", ContestPrepCompileSPJAPI.as_view(),
            name="contest_prep_compile_spj_api"),
    re_path(r"^contest/prep/import_problem/?$", ContestPrepImportProblemAPI.as_view(),
            name="contest_prep_import_problem_api"),
    re_path(r"^contest/prep/publish/?$", ContestPrepPublishAPI.as_view(), name="contest_prep_publish_api"),
    re_path(r"^contest/prep/feedback/?$", ContestPrepFeedbackAPI.as_view(), name="contest_prep_feedback_api"),
    re_path(r"^contest/prep/rank/?$", ContestPrepRankAPI.as_view(), name="contest_prep_rank_api"),
    re_path(r"^contest/prep/invite/?$", ContestPrepInviteAPI.as_view(), name="contest_prep_invite_api"),
    re_path(r"^contest/prep/invite/accept/?$", ContestPrepInviteAcceptAPI.as_view(),
            name="contest_prep_invite_accept_api"),
]
