from __future__ import annotations

import json
import os
import sys
import time
import tempfile
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

import requests


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class ProbeError(RuntimeError):
    """A safe-to-display probe failure."""

    exit_code = 1


class AuthenticationRequired(ProbeError):
    exit_code = 2


class AntiBotChallenge(ProbeError):
    exit_code = 3


class CaptchaRequired(ProbeError):
    exit_code = 4


class AmbiguousSubmission(ProbeError):
    exit_code = 5


@dataclass
class RemoteSubmission:
    provider: str
    remote_id: str
    problem_id: str
    submitted_at: int
    query: dict[str, Any] = field(default_factory=dict, repr=False)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("query", None)
        return data


@dataclass
class RemoteResult:
    provider: str
    remote_id: str
    stage: str
    finished: bool
    verdict: Optional[str] = None
    time_ms: Optional[int] = None
    memory_bytes: Optional[int] = None
    passed_tests: Optional[int] = None
    total_tests: Optional[int] = None
    score: Optional[float] = None
    message: str = ""

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CookieBundle:
    cookies: list[dict[str, Any]]
    user_agent: str = DEFAULT_USER_AGENT


def read_source(source_path: Optional[str], inline_code: Optional[str]) -> str:
    if source_path and inline_code is not None:
        raise ProbeError("--source 和 --code 只能使用一个")
    if source_path:
        try:
            code = Path(source_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ProbeError(f"无法读取源码文件: {exc}") from exc
    elif inline_code is not None:
        code = inline_code
    else:
        if sys.stdin.isatty():
            raise ProbeError("请使用 --source、--code，或通过 stdin 输入源码")
        code = sys.stdin.read()
    if not code.strip():
        raise ProbeError("源码不能为空")
    if len(code.encode("utf-8")) > 1024 * 1024:
        raise ProbeError("PoC 限制源码大小不超过 1 MiB")
    return code


def load_cookie_bundle(path: str) -> CookieBundle:
    cookie_path = Path(path).expanduser()
    try:
        raw = cookie_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AuthenticationRequired(f"无法读取 Cookie 文件: {exc}") from exc
    if not raw:
        raise AuthenticationRequired("Cookie 文件为空")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        cookies = parsed.get("cookies")
        user_agent = parsed.get("user_agent") or DEFAULT_USER_AGENT
        if not isinstance(cookies, list):
            raise AuthenticationRequired("Cookie JSON 缺少 cookies 数组")
        return CookieBundle(cookies=cookies, user_agent=str(user_agent))
    if isinstance(parsed, list):
        return CookieBundle(cookies=parsed)

    cookies = []
    for part in raw.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value})
    if not cookies:
        raise AuthenticationRequired("无法解析 Cookie 文件")
    return CookieBundle(cookies=cookies)


def build_session(cookie_file: str, default_domain: str) -> requests.Session:
    bundle = load_cookie_bundle(cookie_file)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": bundle.user_agent,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    for cookie in bundle.cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not name:
            continue
        domain = str(cookie.get("domain") or default_domain)
        path = str(cookie.get("path") or "/")
        session.cookies.set(name, value, domain=domain, path=path)
    return session


def response_json(response: requests.Response, context: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ProbeError(f"{context}返回了非 JSON 响应（HTTP {response.status_code}）") from exc
    if not isinstance(data, dict):
        raise ProbeError(f"{context}返回格式异常")
    return data


def poll_until_finished(
    query: Callable[[], RemoteResult],
    timeout_seconds: float,
    interval_seconds: float,
    on_update: Optional[Callable[[RemoteResult], None]] = None,
) -> RemoteResult:
    deadline = time.monotonic() + timeout_seconds
    last: Optional[RemoteResult] = None
    while True:
        last = query()
        if on_update:
            on_update(last)
        if last.finished:
            return last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError(
                f"等待远程判题超时；最后状态为 {last.stage}，远程提交 ID={last.remote_id}"
            )
        time.sleep(min(interval_seconds, remaining))


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def require_confirmed(confirmed: bool) -> None:
    if not confirmed:
        raise ProbeError("这是实际远程提交；请确认测试账号和题目后增加 --confirm-submit")


def write_private_json(path: str, data: dict[str, Any]) -> Path:
    output = Path(path).expanduser().absolute()
    if output.is_symlink():
        raise ProbeError("凭据文件不能是符号链接")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".credentials-", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return output


def first_present(data: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None
