from __future__ import annotations

import re
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests

from .common import (
    AmbiguousSubmission,
    AntiBotChallenge,
    AuthenticationRequired,
    ProbeError,
    RemoteResult,
    RemoteSubmission,
    build_session,
    response_json,
)


BASE_URL = "https://codeforces.com"
API_URL = f"{BASE_URL}/api/user.status"


def parse_problem_id(raw: str) -> tuple[int, str]:
    value = raw.strip()
    if "://" in value:
        path = urlparse(value).path
        match = re.search(r"/(?:problem|problemset/problem)/(\d+)/([A-Za-z][A-Za-z0-9]*)/?$", path)
    else:
        match = re.fullmatch(r"(\d+)[-/]?([A-Za-z][A-Za-z0-9]*)", value)
    if not match:
        raise ProbeError("Codeforces 题号格式应类似 4A 或题目 URL")
    return int(match.group(1)), match.group(2).upper()


class _Form:
    def __init__(self, attrs: dict[str, str]):
        self.attrs = attrs
        self.fields: dict[str, str] = {}
        self.file_fields: set[str] = set()
        self.languages: dict[str, str] = {}
        self.has_program_type = False


class SubmitFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[_Form] = []
        self.current: Optional[_Form] = None
        self.select_name = ""
        self.option_value = ""
        self.option_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "form":
            self.current = _Form(values)
            self.forms.append(self.current)
        elif self.current and tag == "input":
            name = values.get("name", "")
            if not name:
                return
            if values.get("type", "").lower() == "file":
                self.current.file_fields.add(name)
            else:
                self.current.fields[name] = values.get("value", "")
            if name == "programTypeId":
                self.current.has_program_type = True
        elif self.current and tag == "textarea":
            name = values.get("name", "")
            if name:
                self.current.fields.setdefault(name, "")
        elif self.current and tag == "select":
            self.select_name = values.get("name", "")
            if self.select_name == "programTypeId":
                self.current.has_program_type = True
        elif self.current and tag == "option" and self.select_name == "programTypeId":
            self.option_value = values.get("value", "")
            self.option_text = []

    def handle_data(self, data: str) -> None:
        if self.option_value:
            self.option_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.current and self.option_value:
            self.current.languages[self.option_value] = "".join(self.option_text).strip()
            self.option_value = ""
            self.option_text = []
        elif tag == "select":
            self.select_name = ""
        elif tag == "form":
            self.current = None

    def submit_form(self) -> _Form:
        for form in self.forms:
            classes = form.attrs.get("class", "").split()
            if "submitForm" in classes or form.has_program_type:
                return form
        raise AuthenticationRequired("Codeforces 页面中没有提交表单；Cookie 可能已失效")


def _looks_like_challenge(response: requests.Response) -> bool:
    text = response.text[:20000].lower()
    return response.status_code in {403, 429} or "just a moment" in text or "cf-chl-" in text


class CodeforcesProvider:
    def __init__(self, handle: str, cookie_file: Optional[str] = None):
        self.handle = handle.strip()
        self.session = build_session(cookie_file, ".codeforces.com") if cookie_file else None

    def _api_submissions(self, count: int = 20) -> list[dict[str, Any]]:
        if not self.handle:
            raise ProbeError("Codeforces 缺少账号 handle，无法通过官方 API 关联 Run ID")
        try:
            response = requests.get(
                API_URL,
                params={"handle": self.handle, "from": 1, "count": count},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise ProbeError(f"Codeforces 官方 API 请求失败: {exc}") from exc
        data = response_json(response, "Codeforces 官方 API")
        if data.get("status") != "OK" or not isinstance(data.get("result"), list):
            raise ProbeError(f"Codeforces 官方 API 返回错误: {data.get('comment', 'unknown error')}")
        return data["result"]

    def submit_requests(self, problem_id: str, language_id: str, code: str) -> RemoteSubmission:
        if self.session is None:
            raise AuthenticationRequired("requests 提交模式需要 --cookie-file")
        if not self.handle:
            raise ProbeError("Codeforces requests 提交模式必须提供 --handle")
        contest_id, index = parse_problem_id(problem_id)
        problem_url = f"{BASE_URL}/problemset/problem/{contest_id}/{index}"
        try:
            response = self.session.get(problem_url, params={"locale": "en"}, timeout=30)
        except requests.RequestException as exc:
            raise ProbeError(f"无法打开 Codeforces 提交页面: {exc}") from exc
        if _looks_like_challenge(response):
            raise AntiBotChallenge(
                "Codeforces 返回了反自动化挑战；请使用 --browser-profile 浏览器提交模式"
            )

        parser = SubmitFormParser()
        parser.feed(response.text)
        form = parser.submit_form()
        if form.languages and str(language_id) not in form.languages:
            available = ", ".join(f"{key}={value}" for key, value in form.languages.items())
            raise ProbeError(f"语言 ID {language_id} 不在当前题目可选列表中: {available}")

        before = max((int(item.get("id", 0)) for item in self._api_submissions()), default=0)
        started_at = int(time.time())
        nonce_code = code.rstrip() + "\n" + (" " * (started_at % 97 + 1)) + "\n"
        data = dict(form.fields)
        data["programTypeId"] = str(language_id)
        files = None
        if "sourceFile" in form.file_fields:
            files = {"sourceFile": ("main.txt", nonce_code.encode("utf-8"), "text/plain")}
        elif "source" in data:
            data["source"] = nonce_code
        else:
            data["source"] = nonce_code
        action = urljoin(response.url, form.attrs.get("action") or response.url)
        try:
            self.session.post(
                action,
                data=data,
                files=files,
                headers={"Referer": response.url, "Origin": BASE_URL},
                timeout=30,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            raise AmbiguousSubmission(
                f"Codeforces 提交请求结果未知，请先检查账号提交记录，不要直接重试: {exc}"
            ) from exc
        return self._wait_for_new_run(before, contest_id, index, started_at)

    def submit_browser(
        self,
        problem_id: str,
        language_id: str,
        code: str,
        profile_dir: str,
        headed: bool,
    ) -> RemoteSubmission:
        try:
            from selenium import webdriver
            from selenium.common.exceptions import NoSuchElementException, WebDriverException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import Select
        except ImportError as exc:
            raise ProbeError("浏览器提交模式需要安装 selenium") from exc

        contest_id, index = parse_problem_id(problem_id)
        problem_url = f"{BASE_URL}/problemset/problem/{contest_id}/{index}"
        profile = str(Path(profile_dir).expanduser().resolve())
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        if not headed:
            options.add_argument("--headless=new")

        driver = None
        source_file = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.get(problem_url)
            if "just a moment" in driver.title.lower():
                raise AntiBotChallenge("Codeforces 浏览器仍停留在挑战页，请先用 capture_session.py 登录")
            if not self.handle:
                profile_links = driver.find_elements(By.CSS_SELECTOR, '#header a[href^="/profile/"]')
                if profile_links:
                    profile_path = urlparse(profile_links[0].get_attribute("href") or "").path
                    match = re.match(r"^/profile/([^/?#]+)", profile_path)
                    if match:
                        self.handle = match.group(1)
            if not self.handle:
                raise AuthenticationRequired("Codeforces 页面中没有检测到已登录账号")
            before = max((int(item.get("id", 0)) for item in self._api_submissions()), default=0)
            started_at = int(time.time())
            nonce_code = code.rstrip() + "\n" + (" " * (started_at % 97 + 1)) + "\n"
            try:
                select_element = driver.find_element(By.NAME, "programTypeId")
            except NoSuchElementException as exc:
                raise AuthenticationRequired(
                    "Codeforces 页面中没有提交表单；请先用同一 --profile-dir 完成登录"
                ) from exc
            Select(select_element).select_by_value(str(language_id))

            form = select_element.find_element(By.XPATH, "ancestor::form")
            file_inputs = form.find_elements(By.CSS_SELECTOR, 'input[type="file"][name="sourceFile"]')
            if file_inputs:
                source_file = tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".txt", prefix="xju-oj-cf-", delete=False
                )
                source_file.write(nonce_code)
                source_file.close()
                file_inputs[0].send_keys(source_file.name)
            else:
                textarea = form.find_element(By.NAME, "source")
                textarea.clear()
                textarea.send_keys(nonce_code)

            submitters = form.find_elements(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
            if not submitters:
                raise ProbeError("Codeforces 提交表单没有可识别的提交按钮")
            submitters[0].click()
            time.sleep(1.0)
        except WebDriverException as exc:
            raise AmbiguousSubmission(
                f"Codeforces 浏览器提交结果未知，请先检查账号提交记录，不要直接重试: {exc.msg}"
            ) from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException:
                    pass
            if source_file is not None:
                Path(source_file.name).unlink(missing_ok=True)
        return self._wait_for_new_run(before, contest_id, index, started_at)

    def _wait_for_new_run(
        self, before: int, contest_id: int, index: str, started_at: int
    ) -> RemoteSubmission:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            for item in self._api_submissions():
                problem = item.get("problem") or {}
                if (
                    int(item.get("id", 0)) > before
                    and int(problem.get("contestId", -1)) == contest_id
                    and str(problem.get("index", "")).upper() == index
                    and int(item.get("creationTimeSeconds", 0)) >= started_at - 10
                ):
                    return RemoteSubmission(
                        provider="codeforces",
                        remote_id=str(item["id"]),
                        problem_id=f"{contest_id}{index}",
                        submitted_at=int(item.get("creationTimeSeconds") or started_at),
                    )
            time.sleep(1.5)
        raise AmbiguousSubmission(
            "Codeforces 未在官方 API 中发现对应的新 Run ID；请检查账号提交记录后再决定是否重试"
        )

    def query(self, submission: RemoteSubmission) -> RemoteResult:
        run_id = int(submission.remote_id)
        for item in self._api_submissions(count=50):
            if int(item.get("id", 0)) != run_id:
                continue
            verdict = item.get("verdict")
            phase = str(item.get("testset") or item.get("phase") or "TESTING")
            finished = bool(verdict and verdict != "TESTING")
            return RemoteResult(
                provider="codeforces",
                remote_id=submission.remote_id,
                stage="finished" if finished else "judging",
                finished=finished,
                verdict=str(verdict) if verdict else None,
                time_ms=item.get("timeConsumedMillis"),
                memory_bytes=item.get("memoryConsumedBytes"),
                passed_tests=item.get("passedTestCount"),
                message=phase,
            )
        raise ProbeError(f"Codeforces 官方 API 中暂时找不到 Run ID {run_id}")
