"""Five small CPU practice tasks; generated labels are runtime data, not Git assets."""
import csv
import io
import math
import random

IMPORTS = "import torch\nfrom torch import nn\nimport numpy as np\nimport pandas as pd\n"
LINEAR = '''def train(X, y, lr=0.03, epochs=10, batch_size=32):
    w = torch.zeros(X.shape[1], 1, requires_grad=True)
    b = torch.zeros(1, requires_grad=True)
    for _ in range(epochs):
        order = torch.randperm(len(X))
        for start in range(0, len(X), batch_size):
            idx = order[start:start + batch_size]
            loss = ((X[idx] @ w + b - y[idx]) ** 2).mean() / 2
            loss.backward()
            with torch.no_grad():
                w -= lr * w.grad
                b -= lr * b.grad
                w.grad.zero_()
                b.grad.zero_()
    return w.detach(), b.detach()
'''
SOFTMAX = '''def stable_softmax(logits):
    shifted = logits - logits.max(dim=1, keepdim=True).values
    return shifted.exp() / shifted.exp().sum(dim=1, keepdim=True)

def cross_entropy(logits, y):
    return (torch.logsumexp(logits, dim=1) - logits[torch.arange(len(y)), y]).mean()

def accuracy(logits, y):
    return (logits.argmax(dim=1) == y).double().mean()
'''
XOR = '''class XORNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2, 8), nn.Tanh(), nn.Linear(8, 2))

    def forward(self, x):
        return self.net(x)

def train_xor(model, X, y):
    optimizer = torch.optim.Adam(model.parameters(), lr=0.03)
    for _ in range(500):
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(model(X), y)
        loss.backward()
        optimizer.step()
    return model
'''


def csv_text(columns, rows):
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue()


def base(code, title, category, metric, objective, signature, requirements, evaluation, starter, reference):
    return {"id": code, "title": title, "type": category, "metric": metric, "points": 20,
            "statement": {"objective": objective, "signature": signature, "requirements": requirements,
                          "evaluation": evaluation, "data": "本题为合成数据练习，使用 CPU 即可完成。每次运行启动全新内核；请把所需代码保存在 Notebook 中。"},
            "cells": [IMPORTS, starter], "reference_cells": [IMPORTS, reference], "public_files": {}}


def generate(seed):
    rng = random.Random(seed)
    problems = []
    linear = base("AI001", "线性回归从零实现", "logic", "MSE",
                  "使用自动求导实现小批量 SGD，返回权重与偏置。", "train(X, y, lr=0.03, epochs=10, batch_size=32) → (w, b)",
                  ["禁用 nn.Linear 和 torch.optim；使用 loss.backward()。", "w 形状为 (2, 1)，b 为单元素张量。",
                   "参考流程：randperm 打乱、按批次计算平方损失、backward、no_grad 更新、清空梯度。"],
                  "评测提供 1024 个训练样本，训练 20 轮；参数最大误差 ≤ 0.1 且独立数据 MSE ≤ 0.02 得 100 分，否则 0 分。",
                  "def train(X, y, lr=0.03, epochs=10, batch_size=32):\n    # 按题面流程实现 SGD\n    raise NotImplementedError\n", LINEAR)
    w, b = [rng.uniform(-4, 4) for _ in range(2)], rng.uniform(-2, 2)
    X = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(1024)]
    y = [[sum(a * v for a, v in zip(row, w)) + b + rng.gauss(0, 0.01)] for row in X]
    test = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(128)]
    linear["input"] = {"code": "AI001", "seed": rng.randrange(2**31), "X": X, "y": y}
    linear["reference"] = {"code": "AI001", "w": w, "b": b, "X": test,
                            "y": [sum(a * v for a, v in zip(row, w)) + b for row in test]}
    linear["cells"].append("# 公开样例\nX = torch.randn(128, 2)\ny = X @ torch.tensor([[2.], [-1.]]) + 1\nw, b = train(X, y, epochs=20)\nprint(w, b)")
    problems.append(linear)

    softmax = base("AI002", "稳定 Softmax", "logic", "测试通过率",
                   "实现数值稳定的 Softmax、平均交叉熵和准确率。", "stable_softmax(logits) / cross_entropy(logits, y) / accuracy(logits, y)",
                   ["支持 float64 的 [batch, classes] 有限 logits，标签形状 [batch]。",
                    "交叉熵输入为 logits；极端数值也应返回有限结果。", "参考：按行减最大值；交叉熵使用 logsumexp 减真实类别的 logit。"],
                   "6 组数据分别检查概率、损失、准确率，共 18 项等权。相对误差 ≤ 1e-7；全部通过为通过测试。",
                   "def stable_softmax(logits):\n    raise NotImplementedError\n\ndef cross_entropy(logits, y):\n    raise NotImplementedError\n\ndef accuracy(logits, y):\n    raise NotImplementedError\n", SOFTMAX)
    cases = [{"logits": [[10000., 9999.], [-10000., -9999.]], "y": [0, 1]},
             {"logits": [[1000000., -1000000.], [-1000000., 1000000.]], "y": [1, 1]},
             {"logits": [[0., 0., 0.], [100000., 100000., 100000.]], "y": [2, 0]}]
    for scale in (1, 100, 10000):
        cases.append({"logits": [[rng.gauss(0, scale) for _ in range(5)] for _ in range(7)],
                      "y": [rng.randrange(5) for _ in range(7)]})
    softmax["input"] = {"code": "AI002", "seed": 42, "cases": cases}
    softmax["reference"] = {"code": "AI002", "cases": cases}
    problems.append(softmax)

    xor = base("AI003", "补全 PyTorch 训练循环", "model", "Accuracy",
               "定义包含非线性激活的 nn.Module，训练 XOR 数据。", "XORNet.forward(x) → logits; train_xor(model, X, y) → model",
               ["输出形状 [4, 2]，返回训练后的 nn.Module。", "训练函数须调用 zero_grad、backward 和 step。",
                "参考结构：Linear(2, 8)、Tanh、Linear(8, 2)，Adam 学习率 0.03，训练 500 轮。"],
               "训练预算 120 秒；参数发生更新且四个样本准确率达到 100% 得 100 分，否则 0 分。",
               XOR.replace("return self.net(x)", "raise NotImplementedError  # 补全 forward")
                  .replace("loss.backward()", "# TODO: 反向传播").replace("optimizer.step()", "# TODO: 更新参数"), XOR)
    xor["input"] = {"code": "AI003", "seed": 42, "X": [[0., 0.], [0., 1.], [1., 0.], [1., 1.]], "y": [0, 1, 1, 0]}
    xor["reference"] = {"code": "AI003", "y": [0, 1, 1, 0]}
    problems.append(xor)

    for code in ("AI004", "AI005"):
        power = code == "AI004"
        features = ["previous_power", "temperature", "occupants", "hour"] if power else ["merchant", "distance_km", "hour", "rain", "orders"]
        targets = ["next_power_kwh"] if power else ["minutes", "late"]
        columns = ["id", *features]
        allrows = []
        for idx in range(920):
            if power:
                previous, temp, occupants, hour = rng.uniform(1, 8), rng.uniform(5, 35), rng.randint(1, 6), rng.randrange(24)
                x = [previous, temp, occupants, hour]
                target = [max(0, 0.6 * previous + 0.05 * temp + 0.35 * occupants + 0.025 * hour + rng.gauss(0, 0.12))]
            else:
                merchant, distance, hour, rain, orders = rng.randrange(4), rng.uniform(0.2, 10), rng.randrange(24), rng.randrange(2), rng.randrange(1, 30)
                x = [merchant, distance, hour, rain, orders]
                minutes = 10 + merchant + 2.8 * distance + 0.12 * hour + 5 * rain + 0.3 * orders + rng.gauss(0, 2)
                target = [minutes, int(minutes > 40)]
            allrows.append([idx + 1, *x, *target])
        target_names = ["next_power_kwh"] if power else ["minutes", "late_probability"]
        baseline = f'''train_df = pd.read_csv("data/train.csv")
test_df = pd.read_csv("data/test.csv")
features = {features!r}
X = np.column_stack([np.ones(len(train_df)), train_df[features].to_numpy()])
T = np.column_stack([np.ones(len(test_df)), test_df[features].to_numpy()])
coef = np.linalg.lstsq(X, train_df[{targets[0]!r}].to_numpy(), rcond=None)[0]
prediction = T @ coef
result = pd.DataFrame({{"id": test_df["id"], {target_names[0]!r}: prediction}})
'''
        if not power:
            baseline += 'result["late_probability"] = 1 / (1 + np.exp(-(prediction - 40) / 2))\n'
        baseline += 'result.to_csv("predictions.csv", index=False)\nprint(result.head())\n'
        item = base(code, "宿舍用电量预测" if power else "外卖送达时间与超时风险预测", "challenge",
                    "RMSE ↓" if power else "RMSE + LogLoss",
                    "使用提供的训练数据建模，并提交 test.csv 对应的预测结果。",
                    "predictions.csv: " + ",".join(["id", *target_names]),
                    ["公开 train.csv 含 600 行、valid.csv 含 160 行；test.csv 含 160 行且不含标签。",
                     "CSV 列名和测试集 id 顺序必须与接口一致，禁止重复或缺失，数值须有限。",
                     "特征均为数值编码；只在训练集拟合预处理。" + ("" if power else "merchant 为商家类别 0–3，rain 为 0/1；late 表示送达超过 40 分钟，预测概率须在 [0,1]。"),
                     "参考起点：添加常数列，用 np.linalg.lstsq 拟合回归；风险概率可由预测分钟数映射后进一步校准。"],
                    ("分数 = 100 × max(0, 1 − RMSE/3)。" if power else
                     "分数 = 100 × [0.6×max(0,1−RMSE/20) + 0.4×max(0,1−LogLoss/1.5)]；计算 LogLoss 前概率裁剪至 [1e-7,1−1e-7]。") +
                    "测试集 40% 用于公榜、60% 用于私榜，分组固定；私榜只在比赛结束且管理员公布后可见。",
                    "train_df = pd.read_csv('data/train.csv')\ntest_df = pd.read_csv('data/test.csv')\n# TODO: 训练模型，按接口生成 predictions.csv\nprint(train_df.head())", baseline)
        item["public_files"] = {"train.csv": csv_text(columns + targets, allrows[:600]),
                                "valid.csv": csv_text(columns + targets, allrows[600:760]),
                                "test.csv": csv_text(columns, [row[:len(columns)] for row in allrows[760:]])}
        partition = [False] * 64 + [True] * 96
        rng.shuffle(partition)
        item["reference"] = {"code": code, "rows": [{"id": row[0], "targets": row[len(columns):], "private": private}
                                                        for row, private in zip(allrows[760:], partition)]}
        problems.append(item)
    return problems
