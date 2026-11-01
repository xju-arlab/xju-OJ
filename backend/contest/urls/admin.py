from django.urls import re_path

from ..views.admin import (ContestAnnouncementAPI, ContestAPI, ACMContestHelper, ContestRankAwardsAPI, ContestRankFreezeAPI,
                           ContestTeamAPI, ContestTeamGroupAPI, ContestTeamSheetAPI, DownloadContestSubmissions)

urlpatterns = [
    re_path(r"^contest/?$", ContestAPI.as_view(), name="contest_admin_api"),
    re_path(r"^contest/announcement/?$", ContestAnnouncementAPI.as_view(), name="contest_announcement_admin_api"),
    re_path(r"^contest/acm_helper/?$", ACMContestHelper.as_view(), name="acm_contest_helper"),
    re_path(r"^contest/rank_freeze/?$", ContestRankFreezeAPI.as_view(), name="contest_rank_freeze_api"),
    re_path(r"^contest/rank_awards/?$", ContestRankAwardsAPI.as_view(), name="contest_rank_awards_api"),
    re_path(r"^contest/teams/?$", ContestTeamAPI.as_view(), name="contest_team_admin_api"),
    re_path(r"^contest/teams/sheet/?$", ContestTeamSheetAPI.as_view(), name="contest_team_sheet_api"),
    re_path(r"^contest/team_groups/?$", ContestTeamGroupAPI.as_view(), name="contest_team_group_api"),
    re_path(r"^download_submissions/?$", DownloadContestSubmissions.as_view(), name="download_contest_submissions"),
]
