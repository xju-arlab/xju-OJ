from __future__ import annotations

import base64
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from remote_probe.codeforces import CodeforcesProvider, SubmitFormParser, parse_problem_id as parse_cf_problem
from remote_probe.common import ProbeError, RemoteSubmission, load_cookie_bundle, read_source, write_private_json
from remote_probe.luogu import (
    LuoguOpenPlatformProvider,
    QuotaExceeded,
    load_openapp_token,
    parse_openapp_token,
    parse_problem_id as parse_luogu_problem,
)
from remote_probe import luogu as luogu_module
from remote_probe.nowcoder import (
    NowcoderProvider,
    parse_acm_page_info,
    parse_problem_reference,
    parse_question_id,
)


def json_response(data: dict, status_code: int = 200) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = data
    return response


class CommonTests(unittest.TestCase):
    def test_private_json_replaces_existing_file_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text("old")
            path.chmod(0o644)
            write_private_json(path, {"test": "synthetic"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {"test": "synthetic"})
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises((ProbeError, ValueError, OSError)):
                write_private_json(link, {"test": "changed"})
            self.assertEqual(json.loads(path.read_text()), {"test": "synthetic"})

    def test_cookie_json_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.json"
            path.write_text(
                json.dumps(
                    {
                        "user_agent": "test-agent",
                        "cookies": [{"name": "session", "value": "secret"}],
                    }
                ),
                encoding="utf-8",
            )
            bundle = load_cookie_bundle(str(path))
        self.assertEqual(bundle.user_agent, "test-agent")
        self.assertEqual(bundle.cookies[0]["name"], "session")

    def test_read_source_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.cpp"
            path.write_text("int main() {}\n", encoding="utf-8")
            self.assertEqual(read_source(str(path), None), "int main() {}\n")


class CodeforcesTests(unittest.TestCase):
    def test_requests_submission_initializes_source_and_tracks_new_run(self):
        provider = CodeforcesProvider("synthetic")
        provider.session = Mock()
        provider.session.get.return_value = Mock(
            status_code=200, url="https://codeforces.com/problemset/problem/4/A",
            text='<form class="submitForm"><textarea name="source"></textarea><input name="programTypeId"></form>',
        )
        provider._api_submissions = Mock(return_value=[{"id": 42}])
        provider._wait_for_new_run = Mock(return_value="new-run")
        self.assertEqual(provider.submit_requests("4A", "54", "int main(){}"), "new-run")
        body = provider.session.post.call_args.kwargs["data"]
        self.assertTrue(body["source"].startswith("int main(){}\n"))
        self.assertEqual(provider._wait_for_new_run.call_args.args[:3], (42, 4, "A"))

    def test_problem_ids(self) -> None:
        self.assertEqual(parse_cf_problem("4A"), (4, "A"))
        self.assertEqual(
            parse_cf_problem("https://codeforces.com/problemset/problem/2030/A"),
            (2030, "A"),
        )

    def test_submit_form_parser(self) -> None:
        parser = SubmitFormParser()
        parser.feed(
            """
            <form class="submitForm" action="/problemset/submit">
              <input type="hidden" name="csrf_token" value="token">
              <select name="programTypeId">
                <option value="54">GNU G++17</option>
                <option value="89">GNU G++20</option>
              </select>
              <input type="file" name="sourceFile">
            </form>
            """
        )
        form = parser.submit_form()
        self.assertEqual(form.fields["csrf_token"], "token")
        self.assertEqual(form.languages["54"], "GNU G++17")
        self.assertIn("sourceFile", form.file_fields)


class LuoguTests(unittest.TestCase):
    def test_problem_id(self) -> None:
        self.assertEqual(parse_luogu_problem("https://www.luogu.com.cn/problem/P1001"), "P1001")

    def test_openapp_token(self) -> None:
        self.assertEqual(parse_openapp_token("client:secret"), ("client", "secret"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "luogu-openapp.json"
            path.write_text(
                json.dumps({"client_id": "client", "secret": "secret"}),
                encoding="utf-8",
            )
            self.assertEqual(load_openapp_token(str(path)), "client:secret")
        with patch.dict("os.environ", {"LUOGU_OPENAPP_TOKEN": "env-client:env-secret"}):
            self.assertEqual(load_openapp_token(), "env-client:env-secret")

    def test_submit_returns_request_id(self) -> None:
        session = Mock()
        session.headers = {}
        session.post.return_value = json_response({"requestId": "request-123"})
        provider = LuoguOpenPlatformProvider("client:secret", session=session)
        submission = provider.submit(
            "P1001", "cxx/17/gcc", "int main(){}", o2=True, track_id="local-1"
        )
        self.assertEqual(session.auth, ("client", "secret"))
        self.assertEqual(submission.remote_id, "request-123")
        body = session.post.call_args.kwargs["json"]
        self.assertEqual(body["lang"], "cxx/17/gcc")
        self.assertTrue(body["o2"])
        self.assertEqual(body["trackId"], "local-1")

    def test_query_maps_final_status_and_cases(self) -> None:
        session = Mock()
        session.headers = {}
        response = json_response(
            {
                "requestId": "request-123",
                "data": {
                    "compile": {"success": True, "message": ""},
                    "judge": {
                        "status": 12,
                        "time": 10,
                        "memory": 128,
                        "score": 100,
                        "subtasks": [
                            {"id": 1, "cases": [{"id": 1, "status": 12}, {"id": 2, "status": 12}]}
                        ],
                    },
                },
            }
        )
        session.get.return_value = response
        provider = LuoguOpenPlatformProvider("client:secret", session=session)
        result = provider.query(
            RemoteSubmission("luogu", "request-123", "P1001", 1)
        )
        self.assertTrue(result.finished)
        self.assertEqual(result.verdict, "ACCEPTED")
        self.assertEqual(result.memory_bytes, 128 * 1024)
        self.assertEqual(result.passed_tests, 2)
        self.assertEqual(result.total_tests, 2)

    def test_query_handles_no_content_and_compile_error(self) -> None:
        session = Mock()
        session.headers = {}
        session.get.return_value = Mock(status_code=204)
        provider = LuoguOpenPlatformProvider("client:secret", session=session)
        submission = RemoteSubmission("luogu", "request-123", "P1001", 1)
        self.assertFalse(provider.query(submission).finished)

        session.get.return_value = json_response(
            {"data": {"compile": {"success": False, "message": "compile failed"}, "judge": None}}
        )
        result = provider.query(submission)
        self.assertTrue(result.finished)
        self.assertEqual(result.verdict, "COMPILATION_ERROR")
        self.assertEqual(result.message, "compile failed")

    def test_submit_maps_quota_error(self) -> None:
        session = Mock()
        session.headers = {}
        session.post.return_value = json_response(
            {"errorMessage": "insufficient quota"}, status_code=402
        )
        provider = LuoguOpenPlatformProvider("client:secret", session=session)
        with self.assertRaises(QuotaExceeded):
            provider.submit("P1001", "cxx/17/gcc", "int main(){}")

    def test_quota(self) -> None:
        session = Mock()
        session.headers = {}
        session.get.return_value = json_response(
            {"quotas": [{"availablePoints": 1234}]}
        )
        provider = LuoguOpenPlatformProvider("client:secret", session=session)
        self.assertEqual(provider.quota()["quotas"][0]["availablePoints"], 1234)

    def test_real_http_submit_and_poll_transport(self) -> None:
        state = {"polls": 0, "body": None, "authorization": None}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                state["authorization"] = self.headers.get("Authorization")
                length = int(self.headers.get("Content-Length", "0"))
                state["body"] = json.loads(self.rfile.read(length))
                payload = json.dumps({"requestId": "request-http"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                state["polls"] += 1
                if state["polls"] == 1:
                    self.send_response(204)
                    self.end_headers()
                    return
                payload = json.dumps(
                    {
                        "requestId": "request-http",
                        "data": {
                            "compile": {"success": True, "message": ""},
                            "judge": {
                                "status": 12,
                                "time": 3,
                                "memory": 64,
                                "score": 100,
                                "subtasks": [],
                            },
                        },
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args) -> None:
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.object(luogu_module, "BASE_URL", base_url):
                provider = LuoguOpenPlatformProvider("client:secret")
                submission = provider.submit("P1001", "cxx/17/gcc", "int main(){}")
                self.assertFalse(provider.query(submission).finished)
                result = provider.query(submission)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        expected_auth = "Basic " + base64.b64encode(b"client:secret").decode()
        self.assertEqual(state["authorization"], expected_auth)
        self.assertEqual(state["body"]["pid"], "P1001")
        self.assertEqual(submission.remote_id, "request-http")
        self.assertTrue(result.finished)
        self.assertEqual(result.verdict, "ACCEPTED")


class NowcoderTests(unittest.TestCase):
    def test_problem_reference(self) -> None:
        uuid = "c4030190499f4da3acd744d33f39627b"
        self.assertEqual(parse_problem_reference(uuid), (uuid, None))
        self.assertEqual(parse_problem_reference("11742270"), ("11742270", "11742270"))
        self.assertEqual(parse_problem_reference("NC322024"), ("NC322024", None))
        self.assertEqual(
            parse_problem_reference("https://ac.nowcoder.com/acm/problem/322024"),
            ("NC322024", None),
        )

    def test_question_id(self) -> None:
        html = "window.problem = { id: 11742270, uuid: 'abc', type: 4 };"
        self.assertEqual(parse_question_id(html), "11742270")
        self.assertEqual(
            parse_acm_page_info("window.pageInfo = {questionId: '11776488', tagId: '4'};"),
            ("11776488", "4"),
        )

    def test_submit_and_query_current_judge_api(self) -> None:
        provider = object.__new__(NowcoderProvider)
        provider.session = Mock()
        provider._resolve_question = Mock(return_value=(
            "11742270", "https://www.nowcoder.com/questionTerminal/example", 4
        ))
        provider._account_context = Mock(return_value=(12345, 5))
        provider._access_token = Mock(return_value="judge-token")
        provider.session.post.return_value = json_response(
            {"code": 0, "data": {"submissionId": 9988}}
        )
        submission = provider.submit("example", "2", "int main(){}")
        self.assertEqual(submission.remote_id, "9988")
        self.assertNotIn("judge-token", submission.public_dict().values())
        submit_body = provider.session.post.call_args.kwargs["json"]
        self.assertEqual(submit_body["userId"], 12345)
        self.assertEqual(submit_body["appId"], 5)
        self.assertEqual(submit_body["tagId"], 4)

        provider.session.get.return_value = json_response(
            {
                "code": 0,
                "data": {
                    "status": 5,
                    "judgeReplyDesc": "答案正确",
                    "rightCaseNum": 6,
                    "allCaseNum": 6,
                    "rightHundredRate": "100.0",
                },
            }
        )
        result = provider.query(submission)
        self.assertTrue(result.finished)
        self.assertEqual(result.passed_tests, 6)
        self.assertEqual(result.score, 100.0)


if __name__ == "__main__":
    unittest.main()
