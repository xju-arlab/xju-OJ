"""Runs inside the untrusted container. Its output is never an official grade."""
import json
import re
import sys
from pathlib import Path

import nbformat
from jupyter_core.utils import run_sync
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError, DeadKernelError


def emit(event):
    # Newline-delimited frames let the trusted host report progress before exit.
    print(json.dumps(event, ensure_ascii=True), flush=True)


class ProgressNotebookClient(NotebookClient):
    def __init__(self, notebook, **kwargs):
        super().__init__(notebook, **kwargs)
        self.results = []
        self.output_budget = 1024 * 1024
        self.data_loaded = False

    def prepare(self, data):
        self.nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code) for code in data["cells"]])
        self.timeout = data["seconds"]
        self.results = self.results[:len(self.nb.cells)]
        while len(self.results) < len(self.nb.cells):
            self.results.append({"status": "IDLE", "execution_count": None, "text": "", "png": []})
        indices = ([] if data.get("reset_only") else range(len(self.nb.cells)) if data.get("cell_index") is None
                   else [data["cell_index"]])
        for index in indices:
            self.results[index] = {"status": "PENDING", "execution_count": None, "text": "", "png": []}
        self.output_budget = max(0, 1024 * 1024 - sum(len(cell["text"].encode()) + sum(map(len, cell["png"]))
                                                     for cell in self.results))
        emit({"event": "start", "output": {"cells": self.results}})
        return indices

    async def async_execute_cell(self, cell, cell_index, **kwargs):
        state = "RUNNING" if cell.source.strip() else "SKIPPED"
        self.results[cell_index]["status"] = state
        emit({"event": "cell", "index": cell_index, "cell": self.results[cell_index]})
        if state == "SKIPPED":
            return await super().async_execute_cell(cell, cell_index, **kwargs)
        try:
            result = await super().async_execute_cell(cell, cell_index, **kwargs)
            self.results[cell_index]["status"] = "SUCCEEDED"
            return result
        except Exception:
            self.results[cell_index]["status"] = "ERROR"
            raise
        finally:
            texts, images = [], []
            for item in cell.get("outputs", []):
                text = item.get("text", item.get("data", {}).get("text/plain", ""))
                if item.get("output_type") == "error":
                    text = "\n".join(item.get("traceback", []))
                if isinstance(text, list):
                    text = "".join(text)
                text = re.sub(r"\x1b\[[0-9;]*m", "", str(text))[:min(32768, max(0, self.output_budget // 4))]
                texts.append(text)
                self.output_budget -= len(text.encode())
                png = item.get("data", {}).get("image/png")
                if isinstance(png, str) and len(png) < min(512 * 1024, self.output_budget) and len(images) < 4:
                    images.append(png)
                    self.output_budget -= len(png)
            self.results[cell_index].update(execution_count=cell.get("execution_count"), text="\n".join(texts), png=images)
            emit({"event": "cell", "index": cell_index, "cell": self.results[cell_index]})

    execute_cell = run_sync(async_execute_cell)


def execute(client, data):
    # Initialize before any student code runs. Later requests share this filesystem;
    # never follow a student-created symlink while reloading public files.
    if not client.data_loaded:
        for name, content in data.get("files", {}).items():
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.csv", name):
                Path("/work/data", name).write_text(content)
        client.data_loaded = True
    indices = client.prepare(data)
    status = "CANCELLED" if data.get("reset_only") else "SUCCEEDED"
    try:
        for index in indices:
            client.execute_cell(client.nb.cells[index], index, execution_count=client.code_cells_executed + 1)
    except CellTimeoutError:
        status = "TIME_LIMIT"
    except CellExecutionError:
        status = "RUNTIME_ERROR"
    except DeadKernelError:
        status = "SYSTEM_ERROR"
    for cell in client.results:
        if cell["status"] == "PENDING":
            cell["status"] = "SKIPPED"
    output = {"cells": client.results}
    predictions = Path("/work/predictions.csv")
    if predictions.is_file() and not predictions.is_symlink() and predictions.stat().st_size <= 1024 * 1024:
        output["predictions"] = predictions.read_text()[:1024 * 1024]
    emit({"event": "result", "status": status, "output": output})


def main():
    Path("/work/data").mkdir(exist_ok=True)
    client = ProgressNotebookClient(nbformat.v4.new_notebook(), startup_timeout=30, kernel_name="python3",
                                    store_widget_state=False, resources={"metadata": {"path": "/work"}})
    # The trusted host pauses this isolated container between commands. Variables,
    # imports and Jupyter execution counts survive single-cell and run-all requests.
    with client.setup_kernel():
        for line in sys.stdin:
            execute(client, json.loads(line))


if __name__ == "__main__":
    main()
