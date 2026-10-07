"""Runs inside the untrusted container. Its output is never an official grade."""
import json
import re
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError


def main():
    data = json.load(sys.stdin)
    Path("/work/data").mkdir(exist_ok=True)
    for name, content in data.get("files", {}).items():
        if re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.csv", name):
            Path("/work/data", name).write_text(content)
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code) for code in data["cells"]])
    client = NotebookClient(notebook, timeout=data["seconds"], startup_timeout=30, kernel_name="python3",
                            store_widget_state=False, resources={"metadata": {"path": "/work"}})
    status = "SUCCEEDED"
    try:
        client.execute()
    except CellTimeoutError:
        status = "TIME_LIMIT"
    except CellExecutionError:
        status = "RUNTIME_ERROR"
    result = []
    budget = 1024 * 1024
    for cell in notebook.cells:
        texts, images = [], []
        for item in cell.get("outputs", []):
            text = item.get("text", item.get("data", {}).get("text/plain", ""))
            if item.get("output_type") == "error":
                text = "\n".join(item.get("traceback", []))
            if isinstance(text, list):
                text = "".join(text)
            text = re.sub(r"\x1b\[[0-9;]*m", "", str(text))[:min(32768, max(0, budget // 4))]
            texts.append(text)
            budget -= len(text.encode())
            png = item.get("data", {}).get("image/png")
            if isinstance(png, str) and len(png) < min(512 * 1024, budget) and len(images) < 4:
                images.append(png)
                budget -= len(png)
        result.append({"execution_count": cell.get("execution_count"), "text": "\n".join(texts), "png": images})
    output = {"cells": result}
    predictions = Path("/work/predictions.csv")
    if predictions.is_file() and not predictions.is_symlink() and predictions.stat().st_size <= 1024 * 1024:
        output["predictions"] = predictions.read_text()[:1024 * 1024]
    print(json.dumps({"status": status, "output": output}, ensure_ascii=True))


if __name__ == "__main__":
    main()
