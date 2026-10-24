from django.urls import re_path

from ..views.oj import (ContestProblemAPI, PickOneAPI, ProblemAPI, ProblemFavoriteAPI,
                        ProblemTagAPI, ProfileProblemListAPI)

urlpatterns = [
    re_path(r"^problem/tags/?$", ProblemTagAPI.as_view(), name="problem_tag_list_api"),
    re_path(r"^problem/?$", ProblemAPI.as_view(), name="problem_api"),
    re_path(r"^pickone/?$", PickOneAPI.as_view(), name="pick_one_api"),
    re_path(r"^contest/problem/?$", ContestProblemAPI.as_view(), name="contest_problem_api"),
    re_path(r"^problem/favorite/?$", ProblemFavoriteAPI.as_view(), name="problem_favorite_api"),
    re_path(r"^profile/problems/?$", ProfileProblemListAPI.as_view(), name="profile_problem_list_api"),
]
