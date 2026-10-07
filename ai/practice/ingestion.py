"""Trusted interface harness. This process shares the student's untrusted sandbox.

It sees inputs, never the scoring reference or service credentials. Its output is
validated by a separate scorer; it cannot award a grade.
"""
import importlib.util
import json
from pathlib import Path

import torch

data = json.loads(Path("/app/input_data/input.json").read_text())
torch.set_num_threads(1)
torch.manual_seed(data["seed"])
spec = importlib.util.spec_from_file_location("solution", "/app/ingested_program/solution.py")
solution = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solution)

if data["code"] == "AI001":
    X, y = torch.tensor(data["X"]), torch.tensor(data["y"])
    w, b = solution.train(X, y, lr=0.03, epochs=20, batch_size=32)
    w, b = torch.as_tensor(w).detach(), torch.as_tensor(b).detach()
    if w.shape != (2, 1) or b.numel() != 1:
        raise ValueError("Expected w shaped (2, 1) and scalar b")
    result = {"w": w.flatten().tolist(), "b": b.item()}
elif data["code"] == "AI002":
    result = []
    for case in data["cases"]:
        logits = torch.tensor(case["logits"], dtype=torch.float64)
        y = torch.tensor(case["y"], dtype=torch.int64)
        result.append({"p": torch.as_tensor(solution.stable_softmax(logits.clone())).tolist(),
                       "loss": float(solution.cross_entropy(logits.clone(), y.clone())),
                       "accuracy": float(solution.accuracy(logits.clone(), y.clone()))})
else:
    X, y = torch.tensor(data["X"]), torch.tensor(data["y"], dtype=torch.int64)
    model = solution.XORNet()
    if not isinstance(model, torch.nn.Module):
        raise ValueError("XORNet must be an nn.Module")
    initial = torch.cat([p.detach().flatten().clone() for p in model.parameters()])
    model = solution.train_xor(model, X, y)
    model.eval()
    with torch.no_grad():
        logits = model(X)
        final = torch.cat([p.detach().flatten() for p in model.parameters()])
    result = {"logits": logits.tolist(), "change": float((final - initial).abs().max())}
Path("/app/output/answers.json").write_text(json.dumps(result, allow_nan=False))
