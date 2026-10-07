"""Exercise the deployment HTTP check with complete and broken HTTP responses."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api-error":
            body = b'{"error":"server-error","data":"failed"}'
        elif self.path == "/api-ok":
            body = b'{"error":null,"data":{}}'
        elif self.path == "/missing-content":
            body = b"<html>fallback page</html>"
        else:
            body = b"// ==UserScript==\n" + b"// payload\n" * 100000
        self.send_response(404 if self.path == "/not-found" else 200)
        length = len(body) + (100 if self.path == "/truncated" else 0)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # curl --fail may close immediately after the HTTP error headers.
            pass

    def do_HEAD(self):
        self.send_response(301 if self.path == "/admin" else 200)
        self.send_header("Location", "/admin/301")
        self.end_headers()

    def log_message(self, *_args):
        pass


class HttpSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (Path(__file__).resolve().parents[2] / "deploy.sh").read_text()
        cls.function = source.split("http_response_smoke() (", 1)[1].split("\nfrontend_http_smoke()", 1)[0]
        cls.function = "http_response_smoke() (" + cls.function
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def check_response(self, path, status="200", content="// ==UserScript==", *args):
        # Keep the production curl invocation, but skip retry delays in failure
        # cases so the tests exercise transfer/status checking without sleeping.
        shell = self.function + '\ncurl() { command curl "$@" --retry 0; }\nattempt_dir=$1\nshift\nhttp_response_smoke "$@"\n'
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["sh", "-c", shell, "smoke-test", directory,
                 f"http://127.0.0.1:{self.server.server_port}{path}", status, content, *args],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(list(Path(directory).iterdir()), [], "temporary response must be cleaned up")
        return result

    def test_large_userscript_download_finishes_without_pipe_errors(self):
        result = self.check_response("/script")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_truncated_response_is_rejected_even_with_valid_header(self):
        self.assertNotEqual(self.check_response("/truncated").returncode, 0)

    def test_http_error_is_rejected_even_with_valid_body(self):
        self.assertNotEqual(self.check_response("/not-found").returncode, 0)

    def test_fallback_html_is_rejected(self):
        self.assertNotEqual(self.check_response("/missing-content").returncode, 0)

    def test_redirect_uses_actual_status(self):
        self.assertEqual(self.check_response("/admin", "301", "", "--head").returncode, 0)
        self.assertNotEqual(self.check_response("/wrong-status", "301", "", "--head").returncode, 0)

    def test_http_200_with_api_error_is_rejected(self):
        self.assertNotEqual(self.check_response("/api-error", "200", '"error"').returncode, 0)
        self.assertEqual(self.check_response("/api-ok", "200", '"error"').returncode, 0)


if __name__ == "__main__":
    unittest.main()
