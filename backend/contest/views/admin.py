import copy
import os
import zipfile
from datetime import timedelta
from ipaddress import ip_network

import dateutil.parser
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, HttpResponse
from django.utils.timezone import now

from account.decorators import check_contest_permission, ensure_created_by
from account.models import User
from submission.models import Submission, JudgeStatus
from utils.api import APIError, APIView, validate_serializer
from utils.cache import cache
from utils.constants import CacheKey, ContestPrepState, ContestRuleType, PREP_PLACEHOLDER_DAYS
from utils.shortcuts import rand_str
from utils.tasks import delete_files
from ..models import Contest, ContestAnnouncement, ACMContestRank, ContestTeam
from ..statement_pdf import PDF_TIMEOUT_SECONDS, StatementPDFError
from ..team_sheet import compile_team_sheet
from ..teams import create_teams, hash_team_password, team_data, team_password
from problem.models import Problem
from problem.publication import publish_due_contest_problems
from problem.tasks import schedule_contest_problem_publication
from ..serializers import (ContestAnnouncementSerializer, ContestAdminSerializer,
                           CreateConetestSeriaizer, CreateContestAnnouncementSerializer,
                           EditConetestSeriaizer, EditContestAnnouncementSerializer,
                           ACMContesHelperSerializer, ContestRankFreezeSerializer,
                           CreateContestTeamsSerializer, ContestTeamPasswordSerializer,
                           ContestTeamSheetSerializer, )


def freeze_time_error(data, rule_type, preparation):
    """Parse rank_freeze_time in place; it only applies to ACM and must fall inside the window."""
    value = data.get("rank_freeze_time")
    if not value or rule_type != ContestRuleType.ACM or preparation:
        data["rank_freeze_time"] = None
        return None
    value = dateutil.parser.parse(value)
    if not data["start_time"] < value < data["end_time"]:
        return "Freeze time must fall between start time and end time"
    data["rank_freeze_time"] = value
    return None


def forget_frozen_board(contest):
    cache.delete(f"{CacheKey.contest_rank_cache}:{contest.id}:frozen")


class ContestAPI(APIView):
    @validate_serializer(CreateConetestSeriaizer)
    def post(self, request):
        data = request.data
        data["created_by"] = request.user
        if data.pop("preparation", False):
            # AI contests keep their grading setup in tables a publish would not copy.
            if data["rule_type"] not in (ContestRuleType.ACM, ContestRuleType.OI):
                return self.error("Preparation contests support ACM and OI only")
            data["prep_state"] = ContestPrepState.PREPARATION
            data["visible"] = True
            # The real window is chosen on publish; until then the row carries a
            # placeholder that never looks like a finished contest.
            data["start_time"] = now()
            data["end_time"] = data["start_time"] + timedelta(days=PREP_PLACEHOLDER_DAYS)
        elif not data.get("start_time") or not data.get("end_time"):
            return self.error("Start time and end time are required")
        else:
            data["start_time"] = dateutil.parser.parse(data["start_time"])
            data["end_time"] = dateutil.parser.parse(data["end_time"])
        if data["end_time"] <= data["start_time"]:
            return self.error("Start time must occur earlier than end time")
        error = freeze_time_error(data, data["rule_type"], bool(data.get("prep_state")))
        if error:
            return self.error(error)
        if data.get("password") and data["password"] == "":
            data["password"] = None
        for ip_range in data["allowed_ip_ranges"]:
            try:
                ip_network(ip_range, strict=False)
            except ValueError:
                return self.error(f"{ip_range} is not a valid cidr network")
        contest = Contest.objects.create(**data)
        return self.success(ContestAdminSerializer(contest).data)

    @validate_serializer(EditConetestSeriaizer)
    def put(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("id"))
            ensure_created_by(contest, request.user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        data["start_time"] = dateutil.parser.parse(data["start_time"])
        data["end_time"] = dateutil.parser.parse(data["end_time"])
        if data["end_time"] <= data["start_time"]:
            return self.error("Start time must occur earlier than end time")
        error = freeze_time_error(data, contest.rule_type, contest.is_preparation)
        if error:
            return self.error(error)
        if not data["password"]:
            data["password"] = None
        for ip_range in data["allowed_ip_ranges"]:
            try:
                ip_network(ip_range, strict=False)
            except ValueError:
                return self.error(f"{ip_range} is not a valid cidr network")
        if not contest.real_time_rank and data.get("real_time_rank"):
            cache_key = f"{CacheKey.contest_rank_cache}:{contest.id}"
            cache.delete(cache_key)

        for k, v in data.items():
            setattr(contest, k, v)
        contest.save()
        forget_frozen_board(contest)
        publish_due_contest_problems([contest.id])
        if Problem.objects.filter(contest=contest, publish_after_contest=True).exists():
            transaction.on_commit(lambda: schedule_contest_problem_publication(
                contest.id, contest.end_time
            ))
        return self.success(ContestAdminSerializer(contest).data)

    def get(self, request):
        contest_id = request.GET.get("id")
        if contest_id:
            try:
                contest = Contest.objects.get(id=contest_id)
                ensure_created_by(contest, request.user)
                return self.success(ContestAdminSerializer(contest).data)
            except Contest.DoesNotExist:
                return self.error("Contest does not exist")

        contests = Contest.objects.all().order_by("-create_time")
        if request.user.is_admin():
            contests = contests.filter(created_by=request.user)

        keyword = request.GET.get("keyword")
        if keyword:
            contests = contests.filter(title__contains=keyword)
        return self.success(self.paginate_data(request, contests, ContestAdminSerializer))

    def delete(self, request):
        contest_id = request.GET.get("id")
        if not contest_id:
            return self.error("Invalid parameter, id is required")
        try:
            contest = Contest.objects.get(id=contest_id)
            ensure_created_by(contest, request.user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        if contest.rule_type == "AI":
            from ai_studio.models import AIJob
            if AIJob.objects.filter(contest=contest).exists():
                return self.error("This AI contest has submissions. Hide it to preserve grading records.")
        contest.delete()
        return self.success()


class ContestAnnouncementAPI(APIView):
    @validate_serializer(CreateContestAnnouncementSerializer)
    def post(self, request):
        """
        Create one contest_announcement.
        """
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("contest_id"))
            ensure_created_by(contest, request.user)
            data["contest"] = contest
            data["created_by"] = request.user
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        announcement = ContestAnnouncement.objects.create(**data)
        return self.success(ContestAnnouncementSerializer(announcement).data)

    @validate_serializer(EditContestAnnouncementSerializer)
    def put(self, request):
        """
        update contest_announcement
        """
        data = request.data
        try:
            contest_announcement = ContestAnnouncement.objects.get(id=data.pop("id"))
            ensure_created_by(contest_announcement, request.user)
        except ContestAnnouncement.DoesNotExist:
            return self.error("Contest announcement does not exist")
        for k, v in data.items():
            setattr(contest_announcement, k, v)
        contest_announcement.save()
        return self.success()

    def delete(self, request):
        """
        Delete one contest_announcement.
        """
        contest_announcement_id = request.GET.get("id")
        if contest_announcement_id:
            if request.user.is_admin():
                ContestAnnouncement.objects.filter(id=contest_announcement_id,
                                                   contest__created_by=request.user).delete()
            else:
                ContestAnnouncement.objects.filter(id=contest_announcement_id).delete()
        return self.success()

    def get(self, request):
        """
        Get one contest_announcement or contest_announcement list.
        """
        contest_announcement_id = request.GET.get("id")
        if contest_announcement_id:
            try:
                contest_announcement = ContestAnnouncement.objects.get(id=contest_announcement_id)
                ensure_created_by(contest_announcement, request.user)
                return self.success(ContestAnnouncementSerializer(contest_announcement).data)
            except ContestAnnouncement.DoesNotExist:
                return self.error("Contest announcement does not exist")

        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Parameter error")
        contest_announcements = ContestAnnouncement.objects.filter(contest_id=contest_id)
        if request.user.is_admin():
            contest_announcements = contest_announcements.filter(created_by=request.user)
        keyword = request.GET.get("keyword")
        if keyword:
            contest_announcements = contest_announcements.filter(title__contains=keyword)
        return self.success(ContestAnnouncementSerializer(contest_announcements, many=True).data)


class ACMContestHelper(APIView):
    @check_contest_permission(check_type="ranks")
    def get(self, request):
        ensure_created_by(self.contest, request.user)
        ranks = ACMContestRank.objects.filter(contest=self.contest, accepted_number__gt=0) \
            .values("id", "user_id", "user__username", "user__userprofile__real_name", "submission_info")
        # Balloons go to teams; their accounts' real names are the members.
        teams = dict(ContestTeam.objects.filter(contest=self.contest).values_list("user_id", "name"))
        results = []
        for rank in ranks:
            for problem_id, info in rank["submission_info"].items():
                if info["is_ac"]:
                    results.append({
                        "id": rank["id"],
                        "username": rank["user__username"],
                        "team": teams.get(rank["user_id"]),
                        "real_name": rank["user__userprofile__real_name"],
                        "problem_id": problem_id,
                        "ac_info": info,
                        "checked": info.get("checked", False)
                    })
        results.sort(key=lambda x: -x["ac_info"]["ac_time"])
        return self.success(results)

    @check_contest_permission(check_type="ranks")
    @validate_serializer(ACMContesHelperSerializer)
    @transaction.atomic
    def put(self, request):
        ensure_created_by(self.contest, request.user)
        data = request.data
        try:
            rank = ACMContestRank.objects.select_for_update().get(pk=data["rank_id"], contest=self.contest)
        except ACMContestRank.DoesNotExist:
            return self.error("Rank id does not exist")
        problem_rank_status = rank.submission_info.get(data["problem_id"])
        if not problem_rank_status:
            return self.error("Problem id does not exist")
        problem_rank_status["checked"] = data["checked"]
        rank.save(update_fields=("submission_info",))
        return self.success()


class DownloadContestSubmissions(APIView):
    def _dump_submissions(self, contest, exclude_admin=True):
        problem_ids = contest.problem_set.all().values_list("id", "_id")
        id2display_id = {k[0]: k[1] for k in problem_ids}
        ac_map = {k[0]: False for k in problem_ids}
        submissions = Submission.objects.filter(contest=contest, result=JudgeStatus.ACCEPTED).order_by("-create_time")
        user_ids = submissions.values_list("user_id", flat=True)
        users = User.objects.filter(id__in=user_ids)
        path = f"/tmp/{rand_str()}.zip"
        with zipfile.ZipFile(path, "w") as zip_file:
            for user in users:
                if user.is_admin_role() and exclude_admin:
                    continue
                user_ac_map = copy.deepcopy(ac_map)
                user_submissions = submissions.filter(user_id=user.id)
                for submission in user_submissions:
                    problem_id = submission.problem_id
                    if user_ac_map[problem_id]:
                        continue
                    file_name = f"{user.username}_{id2display_id[submission.problem_id]}.txt"
                    compression = zipfile.ZIP_DEFLATED
                    zip_file.writestr(zinfo_or_arcname=f"{file_name}",
                                      data=submission.code,
                                      compress_type=compression)
                    user_ac_map[problem_id] = True
        return path

    def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Parameter error")
        try:
            contest = Contest.objects.get(id=contest_id)
            ensure_created_by(contest, request.user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        exclude_admin = request.GET.get("exclude_admin") == "1"
        zip_path = self._dump_submissions(contest, exclude_admin)
        delete_files.send_with_options(args=(zip_path,), delay=300_000)
        resp = FileResponse(open(zip_path, "rb"))
        resp["Content-Type"] = "application/zip"
        resp["Content-Disposition"] = f"attachment;filename={os.path.basename(zip_path)}"
        return resp


class ContestRankFreezeAPI(APIView):
    @validate_serializer(ContestRankFreezeSerializer)
    def post(self, request):
        """Unfreeze the ACM board, or freeze it again."""
        try:
            contest = Contest.objects.get(id=request.data["contest_id"], rule_type=ContestRuleType.ACM,
                                          rank_freeze_time__isnull=False)
            ensure_created_by(contest, request.user)
        except Contest.DoesNotExist:
            return self.error("Contest has no frozen board")
        contest.rank_unfrozen = request.data["unfrozen"]
        contest.save(update_fields=["rank_unfrozen"])
        forget_frozen_board(contest)
        return self.success({"rank_unfrozen": contest.rank_unfrozen})


class ContestTeamAPI(APIView):
    """Team accounts of one contest: generated from a roster, one login per team."""

    def load_contest(self, request, contest_id):
        try:
            contest = Contest.objects.get(id=contest_id, prep_state__isnull=True)
        except (Contest.DoesNotExist, ValueError, TypeError):
            raise APIError("Contest does not exist")
        ensure_created_by(contest, request.user)
        return contest

    def get(self, request):
        contest = self.load_contest(request, request.GET.get("contest_id"))
        teams = ContestTeam.objects.filter(contest=contest).select_related("user")
        return self.success([team_data(team) for team in teams])

    @validate_serializer(CreateContestTeamsSerializer)
    def post(self, request):
        """Create one account per roster row and register it; plaintext passwords are returned only here."""
        contest = self.load_contest(request, request.data["contest_id"])
        with transaction.atomic():
            created = create_teams(contest, request.data["teams"])
        cache.delete(f"{CacheKey.contest_rank_cache}:{contest.id}")
        forget_frozen_board(contest)
        return self.success(created)

    @validate_serializer(ContestTeamPasswordSerializer)
    def put(self, request):
        """Issue a new password for one team account."""
        contest = self.load_contest(request, request.data["contest_id"])
        try:
            team = ContestTeam.objects.select_related("user").get(id=request.data["id"], contest=contest)
        except ContestTeam.DoesNotExist:
            return self.error("Team does not exist")
        password = team_password()
        team.user.password = hash_team_password(password)
        team.user.save(update_fields=["password"])
        return self.success(dict(team_data(team), password=password))

    def delete(self, request):
        """Remove a team account that has not submitted yet."""
        contest = self.load_contest(request, request.GET.get("contest_id"))
        try:
            team = ContestTeam.objects.get(id=request.GET.get("id"), contest=contest)
        except (ContestTeam.DoesNotExist, ValueError):
            return self.error("Team does not exist")
        if Submission.objects.filter(user_id=team.user_id).exists():
            return self.error("This team has submissions and cannot be deleted")
        try:
            team.user.delete()
        except ProtectedError:
            return self.error("This team has submissions and cannot be deleted")
        cache.delete(f"{CacheKey.contest_rank_cache}:{contest.id}")
        forget_frozen_board(contest)
        return self.success()


class ContestTeamSheetAPI(APIView):
    @validate_serializer(ContestTeamSheetSerializer)
    def post(self, request):
        """Typeset the given team accounts as A4 slips to cut apart."""
        data = request.data
        try:
            contest = Contest.objects.get(id=data["contest_id"], prep_state__isnull=True)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        ensure_created_by(contest, request.user)
        header = contest.title + (f" · 登录 {data['link']}" if data.get("link") else "")
        # One typesetting run per contest at a time.
        lock = f"contest_team_sheet:{contest.id}"
        if not cache.add(lock, 1, timeout=PDF_TIMEOUT_SECONDS * 3):
            return self.error("The team sheet is being typeset; try again shortly")
        try:
            pdf = compile_team_sheet(header, data["teams"])
        except StatementPDFError as error:
            return self.error(str(error))
        finally:
            cache.delete(lock)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="contest-{contest.id}-teams.pdf"'
        return response
