"""Independent scoring: only parse numeric artifacts and AST, never execute source."""
import ast
import csv
import json
import math
from pathlib import Path

import numpy as np

ref = json.loads(Path("/app/input/ref/reference.json").read_text())
code = ref["code"]
scores = {"public_score": 0.0, "private_score": 0.0, "accuracy": 0.0}


def array(value, shape=None):
    result = np.asarray(value, dtype=float)
    if not np.isfinite(result).all() or (shape is not None and result.shape != shape):
        raise ValueError("Non-finite value or invalid output shape")
    return result


def source_policy():
    tree = ast.parse(Path("/app/ingested_program/solution.py").read_text())
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    if code == "AI001":
        # Enforce ordinary imports and calls; this is a course constraint, not an
        # anti-cheating proof against deliberately obfuscated Python programs.
        forbidden = any(isinstance(node, ast.Attribute) and node.attr in {"Linear", "optim"}
                        or isinstance(node, ast.ImportFrom) and
                        ("optim" in (node.module or "") or any(alias.name in {"Linear", "optim"} for alias in node.names))
                        or isinstance(node, ast.Import) and any("optim" in alias.name for alias in node.names)
                        for node in ast.walk(tree))
        return not forbidden and "backward" in calls
    return {"backward", "zero_grad", "step"} <= calls


if code in {"AI001", "AI002", "AI003"}:
    answer = json.loads(Path("/app/input/res/answers.json").read_text())
    if code == "AI001":
        w, b = array(answer["w"], (2,)), float(answer["b"])
        if not math.isfinite(b):
            raise ValueError("Invalid bias")
        mse = float(np.mean((array(ref["X"]) @ w + b - array(ref["y"])) ** 2))
        passed = mse <= 0.02 and np.max(np.abs(w - array(ref["w"]))) <= 0.1 and abs(b - ref["b"]) <= 0.1
        scores["public_score"] = 100.0 if passed and source_policy() else 0.0
    elif code == "AI002":
        if not isinstance(answer, list) or len(answer) != len(ref["cases"]):
            raise ValueError("Missing test outputs")
        passed = 0
        for actual, case in zip(answer, ref["cases"]):
            logits = array(case["logits"])
            labels = np.asarray(case["y"], dtype=int)
            shifted = logits - logits.max(axis=1, keepdims=True)
            p = np.exp(shifted) / np.exp(shifted).sum(axis=1, keepdims=True)
            loss = np.mean(np.log(np.exp(shifted).sum(axis=1)) - shifted[np.arange(len(labels)), labels])
            accuracy = np.mean(logits.argmax(axis=1) == labels)
            passed += int(np.allclose(array(actual["p"], p.shape), p, atol=1e-9, rtol=1e-7))
            passed += int(np.isclose(array(actual["loss"], ()), loss, atol=1e-8, rtol=1e-7))
            passed += int(np.isclose(array(actual["accuracy"], ()), accuracy, atol=1e-9))
        scores["public_score"] = 100.0 * passed / (3 * len(answer))
    else:
        logits = array(answer["logits"], (4, 2))
        accuracy = float(np.mean(logits.argmax(axis=1) == array(ref["y"])))
        changed = float(answer["change"])
        scores["accuracy"] = accuracy
        scores["public_score"] = 100.0 if accuracy == 1 and math.isfinite(changed) and changed > 1e-6 and source_policy() else 0.0
    scores["private_score"] = scores["public_score"]
else:
    with Path("/app/input/res/predictions.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = ["id", "next_power_kwh"] if code == "AI004" else ["id", "minutes", "late_probability"]
        if reader.fieldnames != columns:
            raise ValueError("Incorrect CSV header")
        rows = list(reader)
    if len(rows) != len(ref["rows"]) or [row["id"] for row in rows] != [str(row["id"]) for row in ref["rows"]]:
        raise ValueError("Incorrect IDs or row order")
    predictions = array([[row[key] for key in columns[1:]] for row in rows])
    if code == "AI005" and ((predictions[:, 1] < 0) | (predictions[:, 1] > 1)).any():
        raise ValueError("Probability must be between zero and one")
    for private, key in ((False, "public_score"), (True, "private_score")):
        mask = np.asarray([row["private"] == private for row in ref["rows"]])
        truth = array([row["targets"] for row in ref["rows"]])[mask]
        pred = predictions[mask]
        rmse = float(np.sqrt(np.mean((pred[:, 0] - truth[:, 0]) ** 2)))
        if code == "AI004":
            score = max(0, 1 - rmse / 3)
        else:
            probability = np.clip(pred[:, 1], 1e-7, 1 - 1e-7)
            logloss = float(-np.mean(truth[:, 1] * np.log(probability) + (1 - truth[:, 1]) * np.log(1 - probability)))
            score = 0.6 * max(0, 1 - rmse / 20) + 0.4 * max(0, 1 - logloss / 1.5)
        scores[key] = 100 * score

Path("/app/output/scores.json").write_text(json.dumps(scores, allow_nan=False))
