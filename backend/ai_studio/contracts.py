"""Validate all browser and compute-node input before it enters the queue."""
import json
import math
import re

from utils.api import APIError

ACTIVE = ("PENDING", "JUDGING", "TRAINING", "SCORING", "RUNNING")
TERMINAL = ("ACCEPTED", "WRONG_ANSWER", "PARTIAL", "SCORED", "RUNTIME_ERROR", "TIME_LIMIT",
            "MEMORY_LIMIT", "SYSTEM_ERROR", "SUCCEEDED", "CANCELLED")
MAX_SOURCE_BYTES = 512 * 1024
MAX_PREDICTION_BYTES = 1024 * 1024


def require(condition, message):
    if not condition:
        raise APIError(message)


def cells_input(value):
    require(isinstance(value, list) and 1 <= len(value) <= 64, "Notebook requires 1–64 code cells")
    require(all(isinstance(cell, str) and "\x00" not in cell for cell in value), "Invalid code cells")
    require(sum(len(cell.encode("utf-8")) for cell in value) <= MAX_SOURCE_BYTES, "Notebook is too large")
    return value


def finite_score(value, maximum=100):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum, "Invalid score")
    return float(value)


def judge_input(value):
    require(isinstance(value, dict), "Invalid judge configuration")
    allowed = {"phase_id", "task_id", "public_column", "private_column", "accuracy_column", "pass_score", "run_seconds"}
    require(not set(value) - allowed, "Unknown judge configuration field")
    require(type(value.get("phase_id")) is int and value["phase_id"] > 0, "Codabench phase_id is required")
    if "task_id" in value:
        require(type(value["task_id"]) is int and value["task_id"] > 0, "Invalid task_id")
    for key in ("public_column", "private_column", "accuracy_column"):
        if value.get(key):
            require(isinstance(value[key], str) and re.fullmatch(r"[\w.-]{1,64}", value[key]), "Invalid score column")
    require(bool(value.get("public_column")), "public_column is required")
    finite_score(value.get("pass_score", 100))
    require(type(value.get("run_seconds", 120)) is int and 5 <= value.get("run_seconds", 120) <= 600, "Invalid run limit")
    return value


def notebook_output(value):
    # Only inert text and bounded PNGs are returned, never HTML/JS/SVG/widget output.
    require(isinstance(value, dict) and set(value) <= {"cells", "predictions"}, "Invalid notebook output")
    if "predictions" in value:
        require(isinstance(value["predictions"], str) and len(value["predictions"].encode()) <= MAX_PREDICTION_BYTES,
                "Prediction output is too large")
    cells = value.get("cells", [])
    require(isinstance(cells, list) and len(cells) <= 64, "Invalid notebook output")
    for cell in cells:
        require(isinstance(cell, dict) and set(cell) <= {"text", "png", "execution_count"}, "Invalid cell output")
        require(isinstance(cell.get("text", ""), str), "Invalid output text")
        require(isinstance(cell.get("png", []), list) and len(cell.get("png", [])) <= 4, "Invalid images")
        for png in cell.get("png", []):
            require(isinstance(png, str) and len(png) < 512 * 1024 and re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", png), "Invalid PNG")
        require(cell.get("execution_count") is None or type(cell["execution_count"]) is int, "Invalid execution count")
    require(len(json.dumps(value).encode()) <= 2 * 1024 * 1024, "Notebook output is too large")
    return value


def public_files_input(value):
    require(isinstance(value, dict) and len(value) <= 16, "Invalid public files")
    for name, content in value.items():
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.csv", name), "Only simple CSV filenames are allowed")
        require(isinstance(content, str) and "\x00" not in content, "Invalid CSV")
    require(len(json.dumps(value).encode()) <= 1024 * 1024, "Public data exceeds 1 MiB")
    return value
