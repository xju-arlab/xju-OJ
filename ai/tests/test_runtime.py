"""Opt-in real Docker/Jupyter resource and privilege checks; no production data."""
import json
import copy
import os
from pathlib import Path
import sys
import subprocess
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compute"))
from notebook import NotebookExecutor


@unittest.skipUnless(os.environ.get("XJU_AI_RUNTIME_TESTS") == "1", "requires local Docker and the built notebook image")
class RuntimeTests(unittest.TestCase):
    def run_cell(self, source, seconds=10):
        executor = NotebookExecutor(os.environ.get("AI_NOTEBOOK_IMAGE", "xju-ai-notebook:dev"))
        executor.preflight()
        self.addCleanup(executor.close)
        return executor.run({"id": str(uuid.uuid4()), "lease": uuid.uuid4().hex, "judge": {"run_seconds": seconds}, "payload": {"cells": [source]}}, lambda **data: None)

    def test_sequential_progress_shared_kernel_and_explicit_recovery(self):
        executor = NotebookExecutor(os.environ.get("AI_NOTEBOOK_IMAGE", "xju-ai-notebook:dev"), max_kernels=1)
        self.addCleanup(executor.close)
        kernel = uuid.uuid4().hex
        progress = []

        def run(cells, index=None, generation="", key=kernel, job_id=None):
            return executor.run({"id": job_id or str(uuid.uuid4()), "lease": uuid.uuid4().hex, "judge": {"run_seconds": 15},
                                 "payload": {"cells": cells, "kernel_id": key, "cell_index": index,
                                             "kernel_generation": generation}},
                                lambda **data: progress.append(copy.deepcopy(data)))

        cells = ["import time\ncounter = 40\ntime.sleep(1)", "counter += 1\ntime.sleep(1)\nprint(counter)"]
        first = run(cells)
        self.assertEqual(first["status"], "SUCCEEDED")
        self.assertIn("41", first["output"]["cells"][1]["text"])
        self.assertTrue(any(item.get("output", {}).get("cells", [{}])[0].get("status") == "RUNNING" for item in progress))
        self.assertTrue(any([cell["status"] for cell in item.get("output", {}).get("cells", [])] ==
                            ["SUCCEEDED", "RUNNING"] for item in progress))
        second_id = str(uuid.uuid4())
        second = run(cells, 1, first["output"]["kernel_id"], job_id=second_id)
        self.assertEqual(second["status"], "SUCCEEDED")
        self.assertIn("42", second["output"]["cells"][1]["text"])
        self.assertEqual(second["output"]["cells"][1]["execution_count"], 3)
        self.assertEqual(run(cells, 1, first["output"]["kernel_id"], job_id=second_id), second)
        self.assertEqual(subprocess.check_output(["docker", "inspect", "--format", "{{.State.Paused}}",
                                                  executor.sessions[kernel]["name"]], text=True).strip(), "true")
        run(["print('separate notebook')"], key=uuid.uuid4().hex)
        recovered = run(cells, 1, first["output"]["kernel_id"])
        self.assertEqual(recovered["status"], "CANCELLED")
        self.assertTrue(recovered["output"]["kernel_reset"])
        self.assertTrue(all(cell["execution_count"] is None for cell in recovered["output"]["cells"]))

    def test_run_all_stops_at_error_and_keeps_prior_variables(self):
        executor = NotebookExecutor(os.environ.get("AI_NOTEBOOK_IMAGE", "xju-ai-notebook:dev"))
        self.addCleanup(executor.close)
        key = uuid.uuid4().hex
        job = {"id": str(uuid.uuid4()), "lease": uuid.uuid4().hex, "judge": {"run_seconds": 10},
               "payload": {"kernel_id": key, "cells": ["value = 7", "raise ValueError('expected')", "value = 0"]}}
        result = executor.run(job, lambda **data: None)
        self.assertEqual(result["status"], "RUNTIME_ERROR")
        self.assertEqual([cell["status"] for cell in result["output"]["cells"]], ["SUCCEEDED", "ERROR", "SKIPPED"])
        job["id"] = str(uuid.uuid4())
        job["payload"].update(cell_index=2, cells=["value = 7", "raise ValueError('expected')", "print(value)"])
        self.assertIn("7", executor.run(job, lambda **data: None)["output"]["cells"][2]["text"])

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
