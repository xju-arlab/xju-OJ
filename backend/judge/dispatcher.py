import hashlib
import json
import logging
from urllib.parse import urljoin

import requests
from django.db import transaction
from django.db.models import F

from conf.models import JudgeServer
from options.options import SysOptions
from problem.models import Problem, ProblemRuleType
from problem.utils import parse_problem_template
from submission.models import JudgeStatus, Submission, SubmissionJudgeMode
from utils.cache import cache
from utils.constants import CacheKey

logger = logging.getLogger(__name__)


# 继续处理在队列中的问题
def process_pending_task():
    if cache.llen(CacheKey.waiting_queue):
        # 防止循环引入
        from judge.tasks import judge_task
        tmp_data = cache.rpop(CacheKey.waiting_queue)
        if tmp_data:
            data = json.loads(tmp_data.decode("utf-8"))
            try:
                judge_task.send(**data)
            except Exception:
                cache.rpush(CacheKey.waiting_queue, tmp_data)
                raise


class ChooseJudgeServer:
    def __init__(self):
        self.server = None

    def __enter__(self) -> [JudgeServer, None]:
        with transaction.atomic():
            servers = JudgeServer.objects.select_for_update().filter(is_disabled=False).order_by("task_number")
            servers = [s for s in servers if s.status == "normal"]
            for server in servers:
                if server.task_number < server.cpu_core * 2:
                    server.task_number = F("task_number") + 1
                    server.save(update_fields=["task_number"])
                    self.server = server
                    return server
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.server:
            JudgeServer.objects.filter(id=self.server.id).update(task_number=F("task_number") - 1)


class DispatcherBase(object):
    def __init__(self):
        self.token = hashlib.sha256(SysOptions.judge_server_token.encode("utf-8")).hexdigest()

    def _request(self, url, data=None):
        kwargs = {"headers": {"X-Judge-Server-Token": self.token}, "timeout": (5, 600)}
        if data:
            kwargs["json"] = data
        try:
            return requests.post(url, **kwargs).json()
        except Exception as e:
            logger.exception(e)


class SPJCompiler(DispatcherBase):
    def __init__(self, spj_code, spj_version, spj_language):
        super().__init__()
        spj_compile_config = list(filter(lambda config: spj_language == config["name"], SysOptions.spj_languages))[0]["spj"][
            "compile"]
        self.data = {
            "src": spj_code,
            "spj_version": spj_version,
            "spj_compile_config": spj_compile_config
        }

    def compile_spj(self):
        with ChooseJudgeServer() as server:
            if not server:
                return "No available judge_server"
            result = self._request(urljoin(server.service_url, "compile_spj"), data=self.data)
            if not result:
                return "Failed to call judge server"
            if result["err"]:
                return result["data"]


class JudgeDispatcher(DispatcherBase):
    def __init__(self, submission_id, problem_id):
        super().__init__()
        self.submission = Submission.objects.get(id=submission_id)
        self.contest_id = self.submission.contest_id

        if self.contest_id:
            self.problem = Problem.objects.select_related("contest").get(id=problem_id, contest_id=self.contest_id)
            self.contest = self.problem.contest
        else:
            self.problem = Problem.objects.get(id=problem_id)

    def _compute_statistic_info(self, resp_data):
        # 用时和内存占用保存为多个测试点中最长的那个
        self.submission.statistic_info["time_cost"] = max([x["cpu_time"] for x in resp_data])
        self.submission.statistic_info["memory_cost"] = max([x["memory"] for x in resp_data])

        # sum up the score in OI mode
        if self.problem.rule_type == ProblemRuleType.OI:
            score = 0
            try:
                for i in range(len(resp_data)):
                    if resp_data[i]["result"] == JudgeStatus.ACCEPTED:
                        resp_data[i]["score"] = self.problem.test_case_score[i]["score"]
                        score += resp_data[i]["score"]
                    else:
                        resp_data[i]["score"] = 0
            except IndexError:
                logger.error(f"Index Error raised when summing up the score in problem {self.problem.id}")
                self.submission.statistic_info["score"] = 0
                return
            self.submission.statistic_info["score"] = score

    def judge(self):
        language = self.submission.language
        sub_config = list(filter(lambda item: language == item["name"], SysOptions.languages))[0]
        spj_config = {}
        if self.problem.spj_code:
            for lang in SysOptions.spj_languages:
                if lang["name"] == self.problem.spj_language:
                    spj_config = lang["spj"]
                    break

        if language in self.problem.template:
            template = parse_problem_template(self.problem.template[language])
            prepend = template["prepend"]
            append = template["append"]
            code = f"{prepend}\n{self.submission.code}\n{append}"
        else:
            code = self.submission.code

        data = {
            "language_config": sub_config["config"],
            "src": code,
            "max_cpu_time": self.problem.time_limit,
            "max_memory": 1024 * 1024 * self.problem.memory_limit,
            "test_case_id": self.problem.test_case_id,
            "output": False,
            "spj_version": self.problem.spj_version,
            "spj_config": spj_config.get("config"),
            "spj_compile_config": spj_config.get("compile"),
            "spj_src": self.problem.spj_code,
            "io_mode": self.problem.io_mode
        }

        with ChooseJudgeServer() as server:
            if not server:
                data = {"submission_id": self.submission.id, "problem_id": self.problem.id}
                cache.lpush(CacheKey.waiting_queue, json.dumps(data))
                return
            claimed = Submission.objects.filter(
                id=self.submission.id, result=JudgeStatus.PENDING,
                judge_mode=SubmissionJudgeMode.LOCAL).update(result=JudgeStatus.JUDGING)
            if not claimed:
                return
            self.submission.statistic_info = {}
            self.submission.info = {}
            resp = self._request(urljoin(server.service_url, "/judge"), data=data)

        if not resp or (not resp.get("err") and not resp.get("data")):
            self.submission.result = JudgeStatus.SYSTEM_ERROR
            self.submission.statistic_info = {"score": 0, "err_info": "Judge server returned no test results"}
        elif resp["err"]:
            self.submission.result = (JudgeStatus.COMPILE_ERROR if resp["err"] == "CompileError"
                                      else JudgeStatus.SYSTEM_ERROR)
            self.submission.statistic_info["err_info"] = resp["data"]
            self.submission.statistic_info["score"] = 0
        else:
            resp["data"].sort(key=lambda x: int(x["test_case"]))
            self.submission.info = resp
            self._compute_statistic_info(resp["data"])
            error_test_case = list(filter(lambda case: case["result"] != 0, resp["data"]))
            # ACM模式下,多个测试点全部正确则AC，否则取第一个错误的测试点的状态
            # OI模式下, 若多个测试点全部正确则AC， 若全部错误则取第一个错误测试点状态，否则为部分正确
            if not error_test_case:
                self.submission.result = JudgeStatus.ACCEPTED
            elif self.problem.rule_type == ProblemRuleType.ACM or len(error_test_case) == len(resp["data"]):
                self.submission.result = error_test_case[0]["result"]
            else:
                self.submission.result = JudgeStatus.PARTIALLY_ACCEPTED
        self.submission.save()

        self.finalize_submission()

        # 至此判题结束，尝试处理任务队列中剩余的任务
        process_pending_task()

    def finalize_submission(self):
        """Reconcile projections after local or browser-bridged final verdicts."""
        from judge.statistics import refresh_submission_statistics
        refresh_submission_statistics(self.submission)
