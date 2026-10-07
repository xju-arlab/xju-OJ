"""Exercise the real CLI parser without launching privileged user code."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class CliLimitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.executable = Path(cls.directory.name) / "judger-cli"
        source = Path(__file__).resolve().parents[1] / "src"
        stub = Path(cls.directory.name) / "runner-stub.c"
        stub.write_text('''#include "runner.h"
void run(struct config *c, struct result *r) {
    r->memory = c->max_memory;
    while (c->args[r->cpu_time]) r->cpu_time++;
    r->exit_code = c->input_path == NULL && c->output_path == NULL && c->error_path == NULL;
    r->real_time = c->max_stack == c->max_memory && c->max_output_size == c->max_memory;
}
''')
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu99", "-I", str(source),
                        str(source / "main.c"), str(source / "argtable3.c"), str(stub),
                        "-lm", "-o", str(cls.executable)], check=True, capture_output=True)

    def run_cli(self, *args):
        return subprocess.run([str(self.executable), "--exe_path=/synthetic", *args],
                              capture_output=True, text=True, timeout=5)

    def test_large_resource_values_and_compatible_suffixes(self):
        for value in ("3221225472", "3GB", "0xc0000000", "+3072MB", "3145728kb", "-1"):
            with self.subTest(value=value):
                result = self.run_cli(*[f"--{key}={value}" for key in ("max_memory", "max_stack", "max_output_size")])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data["memory"], -1 if value == "-1" else 3 * 1024 ** 3)
                self.assertEqual(data["real_time"], 1)

    def test_overflow_negative_and_malformed_values_fail(self):
        for value in ("9223372036854775808", "9223372036854775807GB", "-2", "-1KB", "", "3.5GB", "1;id"):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_cli(f"--max_memory={value}").returncode, 0)

    def test_argument_array_boundary_and_inherited_stdio(self):
        good = self.run_cli(*["--args=x"] * 254)
        self.assertEqual(good.returncode, 0, good.stdout)
        self.assertEqual(json.loads(good.stdout)["cpu_time"], 255)
        self.assertEqual(json.loads(good.stdout)["exit_code"], 1)
        self.assertNotEqual(self.run_cli(*["--args=x"] * 255).returncode, 0)


if __name__ == "__main__":
    unittest.main()
