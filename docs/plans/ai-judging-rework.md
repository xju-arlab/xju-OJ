# AI 判题口径重做与重判方案

## 一、结论

- 现在的"只有一个端到端考点"把逻辑写对的人清零了：AI019 的 11 条正式提交里，8 条能把
  `linreg` / `squared_loss` / `sgd` 写对，只在 `train` 里错一处（`NameError`、大小写、缩进），
  现在全部记 0。
- 改为分层判分：**接口行为 60 + 端到端 40**，一项报错只扣该项。已按此方案在赛中执行（见第九节）。
- 重判代价很小：只有 AI019 需要重跑（14 条，约 3 分钟），其余 6 题本来就是分项或连续分。

## 二、现状（2026-10-31 16:45 北京时间）

| 指标 | 数值 |
| --- | --- |
| 比赛 26 正式提交 | 46 条（9 题） |
| 状态分布 | 通过 4 / 部分分 15 / 未通过 26 / 待评阅 1 |
| AI019 | 9 人 11 条，全部 0 分 |

AI019 的 9 份提交已在本地沙箱用线上同一题包逐条复跑，分数与报错和线上完全一致——
**不是判题机 bug，是口径问题**。

## 三、判题原则

1. 只判每个接口的输入→输出；不判 dtype、原地、`requires_grad`、`leaf`、梯度数值这类中间状态。
2. 一项出错只扣该项；一个 `NameError` 不能吞掉整题。
3. 保留：禁用 API 归零、隐藏数据、答案与阈值不外泄。
4. 反馈必须分项：`linreg 15/15，squared_loss 15/15，sgd 30/30，train 0/40：<原因>`，≤160 字。
5. 通过线：`logic` 题保持 100（"通过"是比赛语义）；分层只体现在分数与 OI 得分上。
   —— 若希望"大部分逻辑写对"也算通过，可把 `logic` 的 `pass_score` 降到 80，需要显式决定。

## 四、AI019 分值表（其余 6 题不动）

| 考点 | 分值 | 判定 |
| --- | --- | --- |
| `linreg` 3 组隐藏输入 | 15 | 返回值形状与数值 |
| `squared_loss` 3 组 | 15 | 逐样本损失的形状与数值 |
| `sgd` 参数更新 + 梯度清零 | 30 | 更新后的参数值、梯度是否清零 |
| `train` | 40 | 隐藏数据上的 MSE 达标 |

去掉两项"死卡"：

- `train.params`（20 分）：要求训练出的 `w,b` 与参考轨迹逐位一致，换个合法写法就 0。
- `sgd.leaf`（5 分）：检查张量是否叶子节点，属于实现细节。

## 五、试算结果（原型已跑，非估算）

| 学生 | 现在 | 分层后 | 主要扣分 |
| --- | --- | --- | --- |
| user-5196dc5e5d | 0 | **60** | `train`：`NameError: name 'loss' is not defined` |
| sqzc | 0 | **50** | `train`：`NameError: name 'y_hat' is not defined` |
| dlw | 0 | **50** | 同上；`squared_loss` 漏 reshape |
| user-32eca5d381 | 0 | **30** | `sgd`：`gard` 拼写错误 |
| user-cd3c8de022 | 0 | **30** | `train`：`zeros(dim=...)` 参数名错误 |
| user-e0f69d46d4 | 0 | **15** | `w` 形状写死成 (2,1) |
| zhouchangan | 0 | 0 | `Linreg` 大小写错误导致整段没跑起来 |
| user-3ceb045c6f | 0 | 0 | `X_batch` 未定义，函数体没跑通 |
| 20261403004 | 0 | 0 | 第 27 行缩进错误 |

9 人里 6 人能拿到 15–60 分，OI 榜上每题权重 10 分，对应 1.5–6 分。

## 六、重判流程

1. 改私有题源 `linreg-scratch`：
   - `package/evaluation/scoring/program.py`：按第四节分值表打分，末行输出 `XJU_FEEDBACK`；
   - `package/evaluation/reference/answers.json`：恢复 `linreg` / `squared_loss` / `sgd` 的期望值，
     去掉 `train.params`、`sgd.leaf`；
   - `package/problem.json`：更新 `statement.evaluation`。
2. 本地验收：参考解 3 次 100；starter 0；6 个错解分数符合预期；反馈不含阈值与期望值。
3. `problem_package.py build` + `validate`。
4. 重新导入得到新的评测注册，再把 judge 换到 AI019（保留题号、题面、历史提交）。
5. 重判：把 AI019 在比赛 26 的正式提交重置为 `PENDING`（约 11 条，队列约 3 分钟）。
6. 若下调通过线：按 `pass_score` 重算已有提交的 `status`，不需要重跑。
7. 核对：分数分布、反馈文案、OI 榜；回滚 = 恢复 judge + 使用 `~/backups/oj-ai-studio-*.dump`。

## 七、时间与风险

- **赛中做**：暂停 AI 准入 2–3 分钟 + 重判 3 分钟，学生立刻能看到分项并重交；比赛还剩约 45 分钟。
- **赛后做**（更稳）：比赛结束后统一重判，最终成绩以新口径为准，不存在先交后交差异。
- 风险：通过线下调会改变名次；重判期间评测队列被占满；反馈文案需要过一遍不得泄露阈值。

## 八、验收清单

- [ ] 参考解 100，连续 3 次稳定
- [ ] starter 原样提交 0 分且不崩
- [ ] 上面 9 条提交的分数与试算一致
- [ ] 反馈文案：分项得分 + 首个失败原因，≤160 字，无期望值/阈值
- [ ] 禁用 API 仍然整题归零
- [ ] 改完后 AI019–AI025 的 judge 与题面一致，旧提交可回滚

## 九、执行记录（2026-10-31 16:40 北京时间）

决定：**赛中立即执行**，通过线保持 100，只改 AI019。

1. 评分程序改为分层给分，反馈为分项 + 首个失败原因；`reference/answers.json` 恢复
   `linreg` / `squared_loss` / `sgd` 的期望值，删掉 `train.params`、`sgd.leaf`。
2. 题面 `evaluation` 同步为三行分值说明。
3. 本地验收：参考解 100（×3）、`edge_own_names` 100、`edge_sgd_no_batch` 80、
   `wrong_optim` / `wrong_lstsq` 0、`wrong_squared_loss_mean` 45、`wrong_sgd_no_zero_grad` 50、
   starter 0。
4. 重新打包导入，把 judge 换到 AI019（phase 29，version 3），重判 14 条正式提交，
   再删除临时导入的题目。
5. 重判结果与试算一致：60 两条、50 三条、35、30 两条、15、0 三条。

遗留：AI026/AI027 与其余 6 道代码题未改；`batch-code.zip` 已用新包重建。
