from __future__ import annotations

import re
import time
from math import isfinite
from typing import Any
from urllib.parse import urlparse

import requests

from .common import (
    AmbiguousSubmission,
    AuthenticationRequired,
    ProbeError,
    RemoteResult,
    RemoteSubmission,
    build_session,
    first_present,
    response_json,
)


WEB_BASE = "https://www.nowcoder.com"
GATEWAY_BASE = "https://gw-c.nowcoder.com"
JUDGE_BASE = "https://victorinox.nowcoder.com"


def parse_problem_reference(raw: str) -> tuple[str, str | None]:
    value = raw.strip()
    if "://" in value:
        path = urlparse(value).path
        acm_match = re.search(r"/acm/problem/(\d+)", path)
        if acm_match:
            return f"NC{acm_match.group(1)}", None
        match = re.search(r"/questionTerminal/([A-Za-z0-9]+)", path)
        if not match:
            raise ProbeError("牛客题目应为 acm/problem 或 questionTerminal URL")
        return match.group(1), None
    acm_match = re.fullmatch(r"NC(\d+)", value, re.I)
    if acm_match:
        return f"NC{acm_match.group(1)}", None
    if value.isdigit():
        return value, value
    if re.fullmatch(r"[A-Za-z0-9]{16,}", value):
        return value, None
    raise ProbeError("牛客题目请提供 questionTerminal UUID/URL 或数字 questionId")


def parse_question_id(html: str) -> str:
    match = re.search(r"window\.problem\s*=\s*\{.*?\bid\s*:\s*(\d+)", html, re.S)
    if not match:
        raise ProbeError("无法从牛客公开题目页解析数字 questionId")
    return match.group(1)


def parse_acm_page_info(html: str) -> tuple[str, str]:
    block = re.search(r"window\.pageInfo\s*=\s*\{(.*?)\}\s*;", html, re.S)
    if not block:
        raise ProbeError("无法从牛客 ACM 题目页解析 pageInfo")

    def value(name: str) -> str:
        match = re.search(rf"\b{name}\s*:\s*['\"]?([A-Za-z0-9_-]+)", block.group(1))
        if not match:
            raise ProbeError(f"牛客 ACM pageInfo 缺少 {name}")
        return match.group(1)

    return value("questionId"), value("tagId")


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


class NowcoderProvider:
    def __init__(self, cookie_file: str):
        self.session = build_session(cookie_file, ".nowcoder.com")
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Origin": WEB_BASE,
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _resolve_question(self, reference: str) -> tuple[str, str, int]:
        public_id, numeric_id = parse_problem_reference(reference)
        if numeric_id:
            return numeric_id, f"{WEB_BASE}/questionTerminal/{public_id}", 0
        is_acm = public_id.upper().startswith("NC") and public_id[2:].isdigit()
        url = (
            f"https://ac.nowcoder.com/acm/problem/{public_id[2:]}"
            if is_acm
            else f"{WEB_BASE}/questionTerminal/{public_id}"
        )
        try:
            response = self.session.get(url, timeout=25)
        except requests.RequestException as exc:
            raise ProbeError(f"无法打开牛客题目页: {exc}") from exc
        if response.status_code != 200:
            raise ProbeError(f"牛客题目页返回 HTTP {response.status_code}")
        if is_acm:
            question_id, tag_id = parse_acm_page_info(response.text)
            return question_id, url, int(tag_id)
        return parse_question_id(response.text), url, 0

    def _access_token(self, referer: str) -> str:
        try:
            response = self.session.get(
                f"{GATEWAY_BASE}/api/sparta/base-oauth/access-token",
                params={"sceneType": 1},
                headers={"Referer": referer},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise ProbeError(f"牛客判题 Token 请求失败: {exc}") from exc
        data = response_json(response, "牛客判题 Token 接口")
        nested = data.get("data")
        token = nested.get("accessToken") if isinstance(nested, dict) else None
        if not data.get("success") or not token:
            message = str(data.get("msg") or "牛客 Cookie 已失效")
            if "登录" in message or "授权" in message:
                raise AuthenticationRequired(message)
            raise ProbeError(message)
        return str(token)

    def _account_context(self, referer: str) -> tuple[int, int]:
        try:
            response = self.session.get(
                f"{WEB_BASE}/profile/user-info-v2",
                headers={"Referer": referer},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise ProbeError(f"牛客账号信息请求失败: {exc}") from exc
        data = response_json(response, "牛客账号信息接口")
        nested = data.get("data")
        if data.get("code") not in {0, "0"} or not isinstance(nested, dict):
            message = str(data.get("msg") or "牛客 Cookie 已失效")
            raise AuthenticationRequired(message)
        user_id = nested.get("userId")
        if not isinstance(user_id, int) or user_id <= 0:
            raise AuthenticationRequired("牛客账号信息中缺少 userId")
        app_id = 9 if nested.get("isMember") else 5
        return user_id, app_id

    def submit(self, reference: str, language_id: str, code: str) -> RemoteSubmission:
        resolved = self._resolve_question(reference)
        if len(resolved) == 2:
            question_id, referer = resolved
            tag_id = 0
        else:
            question_id, referer, tag_id = resolved
        user_id, app_id = self._account_context(referer)
        token = self._access_token(referer)
        body = {
            "content": code,
            "questionId": question_id,
            "language": str(language_id),
            "submitType": 1,
            "tagId": tag_id,
            "appId": app_id,
            "userId": user_id,
            "remark": "",
            "token": token,
        }
        try:
            response = self.session.post(
                f"{JUDGE_BASE}/api/service/judge/submit",
                json=body,
                headers={"Referer": referer},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AmbiguousSubmission(
                f"牛客提交请求结果未知，请先检查账号记录，不要直接重试: {exc}"
            ) from exc
        data = response_json(response, "牛客判题提交接口")
        if data.get("code") not in {0, "0", None}:
            message = str(data.get("msg") or f"牛客提交失败，code={data.get('code')}")
            if "登录" in message or "token" in message.lower() or data.get("code") in {682, 683, 999}:
                raise AuthenticationRequired(message)
            raise ProbeError(message)
        nested = data.get("data")
        result_data = nested if isinstance(nested, dict) else data
        submission_id = first_present(result_data, ("submissionId", "id"))
        if submission_id is None:
            raise AmbiguousSubmission("牛客提交接口未返回 submissionId；请检查账号提交记录")
        query = dict(result_data)
        query.update(
            {
                "submissionId": submission_id,
                "token": token,
                "submitType": 1,
                "tagId": tag_id,
                "appId": app_id,
                "userId": user_id,
                "remark": "",
            }
        )
        return RemoteSubmission(
            provider="nowcoder",
            remote_id=str(submission_id),
            problem_id=question_id,
            submitted_at=int(time.time()),
            query=query,
        )

    def query(self, submission: RemoteSubmission) -> RemoteResult:
        try:
            response = self.session.get(
                f"{JUDGE_BASE}/api/service/judge/submit-status",
                params=submission.query,
                headers={"Referer": WEB_BASE},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise ProbeError("牛客结果查询失败，请检查网络后重试查询") from None
        data = response_json(response, "牛客判题结果接口")
        if data.get("code") not in {0, "0", None}:
            message = str(data.get("msg") or f"牛客查询失败，code={data.get('code')}")
            if data.get("code") in {682, 683, 999} or "token" in message.lower():
                raise AuthenticationRequired(message)
            raise ProbeError(message)
        nested = data.get("data")
        result = nested if isinstance(nested, dict) else data
        status = int(result.get("status", -1))
        finished = status >= 3
        verdict = str(
            first_present(result, ("judgeReplyDesc", "judgeReply", "desc")) or f"STATUS_{status}"
        )
        memory_kib = _optional_int(result.get("memoryConsumption"))
        return RemoteResult(
            provider="nowcoder",
            remote_id=submission.remote_id,
            stage="finished" if finished else "judging",
            finished=finished,
            verdict=verdict if finished else None,
            time_ms=_optional_int(result.get("timeConsumption")),
            memory_bytes=memory_kib * 1024 if memory_kib is not None else None,
            passed_tests=_optional_int(result.get("rightCaseNum")),
            total_tests=_optional_int(result.get("allCaseNum")),
            score=_optional_float(result.get("rightHundredRate")),
            message=str(result.get("memo") or verdict),
        )
