"""Execute the shipped entrypoint with hostile-but-valid string values."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class RuntimeConfigTest(unittest.TestCase):
    def render(self, **values):
        source = (Path(__file__).resolve().parents[2] /
                  "frontend/docker-entrypoint.d/20-runtime-config.sh").read_text()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "runtime-config.js"
            source = source.replace("/usr/share/nginx/html/runtime-config.js", str(output))
            result = subprocess.run(["sh", "-c", source], env={**os.environ, **values},
                                    capture_output=True, text=True, timeout=5)
            if result.returncode:
                return result, None
            body = output.read_text()
        return result, json.loads(body.split("=", 1)[1].strip().removesuffix(";"))

    def test_quotes_unicode_and_control_characters_round_trip(self):
        value = '测试"\\\n\r\t\x01'
        result, config = self.render(APP_DOMAIN=value, AUTHENTIK_OIDC_ENABLED="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config["APP_DOMAIN"], value)
        self.assertIs(config["AUTHENTIK_OIDC_ENABLED"], True)
        self.assertIs(config["OJ_FRONTEND_DEV_MODE"], False)

    def test_boolean_cannot_inject_javascript(self):
        result, _ = self.render(AUTHENTIK_LOCAL_LOGIN_ENABLED="true};alert(1);//")
        self.assertNotEqual(result.returncode, 0)
