import contextlib
import errno
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "check_judge_host", Path(__file__).parents[1] / "ops" / "check-judge-host.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class JudgeHostPreflightTests(unittest.TestCase):
    def run_check(self, **probe):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(host, "probe_landlock_abi", **probe), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = host.main()
        return result, output.getvalue(), errors.getvalue()

    def test_abi_three_and_newer_are_accepted(self):
        for abi in (3, 4, 6):
            with self.subTest(abi=abi):
                result, output, errors = self.run_check(return_value=abi)
                self.assertEqual(result, 0)
                self.assertIn(f"Landlock ABI {abi}", output)
                self.assertEqual(errors, "")

    def test_older_abis_cannot_silently_pass(self):
        for abi in (1, 2):
            with self.subTest(abi=abi):
                result, output, errors = self.run_check(return_value=abi)
                self.assertEqual(result, 1)
                self.assertEqual(output, "")
                self.assertIn("reboot before deployment", errors)

    def test_missing_kernel_support_is_actionable(self):
        result, _, errors = self.run_check(side_effect=OSError(errno.ENOSYS, "Function not implemented"))
        self.assertEqual(result, 1)
        self.assertIn("Java and File IO", errors)

    def test_denied_probe_does_not_disable_sandbox(self):
        result, _, errors = self.run_check(side_effect=OSError(errno.EPERM, "Operation not permitted"))
        self.assertEqual(result, 1)
        self.assertIn("do not disable sandboxing", errors)


if __name__ == "__main__":
    unittest.main()
