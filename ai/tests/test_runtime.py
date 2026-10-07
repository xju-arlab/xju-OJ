"""Opt-in real Docker/Jupyter resource and privilege checks; no production data."""
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compute"))
from notebook import NotebookExecutor


@unittest.skipUnless(os.environ.get("XJU_AI_RUNTIME_TESTS") == "1", "requires local Docker and the built notebook image")
class RuntimeTests(unittest.TestCase):
    def run_cell(self, source, seconds=10):
        executor = NotebookExecutor(os.environ.get("AI_NOTEBOOK_IMAGE", "xju-ai-notebook:dev"))
        executor.preflight()
        return executor.run({"id": str(uuid.uuid4()), "lease": uuid.uuid4().hex, "judge": {"run_seconds": seconds}, "payload": {"cells": [source]}}, lambda: None)

    def test_no_root_network_credentials_or_writable_root(self):
        result = self.run_cell('''import os, socket, json
assert os.getuid() == 65532
assert not any(k in os.environ for k in ('AI_WORKER_TOKEN_FILE', 'AWS_SECRET_ACCESS_KEY', 'CODABENCH_TOKEN_FILE'))
assert not os.path.exists('/var/run/docker.sock')
try:
    open('/etc/xju-student-write', 'w')
    raise AssertionError('root filesystem writable')
except OSError:
    pass
try:
    socket.create_connection(('1.1.1.1', 80), timeout=1)
    raise AssertionError('network reachable')
except OSError:
    pass
print('ISOLATION_OK')''')
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertIn("ISOLATION_OK", result["output"]["cells"][0]["text"])

    def test_wall_clock_deadline(self):
        self.assertEqual(self.run_cell("import time\ntime.sleep(90)", 5)["status"], "TIME_LIMIT")

    def test_memory_limit(self):
        self.assertEqual(self.run_cell("allocation = bytearray(3 * 1024 ** 3)")["status"], "MEMORY_LIMIT")


if __name__ == "__main__":
    unittest.main()
