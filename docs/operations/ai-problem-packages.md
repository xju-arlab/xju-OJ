# AI 题目导入与导出

题目是运行数据，保存在数据库与私有题包目录中，不随应用镜像发布。
后台「题目 → 导入 / 导出」可切换普通题目与 AI 题目；「AI 题库 → 导入 / 导出」直达 AI 入口。
普通 OJ 的 ZIP、FPS 和远程题导入保持原有格式。

## 导入流程

1. 选择 ZIP 并上传校验；预览题名、题型、指标、Notebook 单元格与公开文件。
2. 确认导入，默认隐藏。系统自动分配 `AI` 数字题号，不覆盖包内来源编号对应的已有题目。
3. 私有评测服务注册评分程序与数据。整批注册通过后，OJ 在一次事务中创建所有题目。
4. 导入记录显示等待、进行中、成功或失败。离开页面不取消任务；失败可重试同一记录。
5. 在题目管理中检查题面，实际运行 Notebook 并提交一次评测后再公开。

上传和导出沿用 OJ 的题目权限：`Own` 管理本人题目，`All` 管理全部题目。
导入记录只有上传者与超级管理员可查看；导出的 ZIP 含私有测试数据，只交给出题管理者。
预览记录可删除；已经导入或开始注册的题包保留为可追溯资产。

## ZIP 布局

单题 ZIP 根目录：

```text
problem.json
starter.ipynb
data/                           # 可选，仅公开 UTF-8 CSV
evaluation/
  scoring/program.py
  reference/                    # 私有参考数据，至少一个文件
  ingestion/program.py          # logic / model 必填
  input/                        # 可选，运行程序可读的评测输入
```

数据挑战 `challenge` 不带 `ingestion/` 和 `input/`，直接评分选手的 `predictions.csv`。
批量 ZIP 外层仅放 1–20 个单题 ZIP，按文件名自然顺序导入，例如 `2.zip` 在 `10.zip` 前。
不支持再嵌套一层批量 ZIP。

整包压缩后最多 16 MiB、累计展开最多 64 MiB、单文件最多 16 MiB、总计最多 1024 项。
每类评测资产（如 reference）最多 255 个文件、32 MiB 减 1 KiB，与计算沙箱的展开限制一致。
拒绝路径穿越、链接、特殊文件、重复或大小写冲突路径、文件与目录冲突、加密和损坏的 ZIP。
仅支持 Store / Deflate。普通 OJ 题包不能导入此入口。

## problem.json

以下为字段示意，不包含任何正式题目的内容：

```json
{
  "format": "xju-ai-problem",
  "version": 1,
  "source_id": "",
  "title": "题目标题",
  "type": "logic",
  "metric": "Score",
  "points": 100,
  "statement": {
    "objective": "任务目标",
    "requirements": ["实现要求"],
    "signature": "接口约定",
    "inputSpec": "输入形状",
    "outputSpec": "输出形状",
    "data": "数据说明",
    "evaluation": "评分说明"
  },
  "evaluation": {
    "public_column": "score",
    "pass_score": 100,
    "run_seconds": 120
  }
}
```

| 字段 | 约定 |
| --- | --- |
| `format` / `version` | 固定为 `xju-ai-problem` / `1`；这是题包协议版本 |
| `source_id` | 可选来源编号，仅记录和导出使用，不指定新题号 |
| `type` | `logic` 逻辑实现、`model` 模型定义、`challenge` 数据挑战 |
| `title` / `metric` | 非空纯文本，分别最多 128 / 64 字符 |
| `points` | 1–10000，默认 100；比赛仍可独立配置题目权重 |
| `statement` | 普通文本，不执行 HTML；各文本最多 32000 字符，实现要求最多 50 项 |
| `public_column` | 必须与 `scores.json` 中公榜评分字段一致，默认 `score` |
| `private_column` | 数据挑战必填，其他类型可选；只有比赛结束并公布后才返回私榜成绩 |
| `accuracy_column` | 可选，模型准确率字段，值须在 0–1 之间 |
| `pass_score` | 0–100，默认 100；逻辑实现和模型定义用它判断是否达标 |
| `run_seconds` | 5–600，默认 120，用于 Notebook 与正式评测时限 |

评分列名必须不同，以英文字母或下划线开头，随后可用字母、数字、下划线、点、短横线，最多 64 字符。
公私榜评分必须为有限的 0–100 数值；RMSE 等原始指标由评分程序转换为分数。
缺少必需评分列会失败，不补零。题包不接受服务器 Phase / Task ID、镜像名、网络或宿主执行命令。

## Notebook 与数据

`starter.ipynb` 使用 Notebook v4，最多 2 MiB；导入 1–64 个代码单元，总源码最多 512 KiB。
Markdown / raw 单元不作为题面导入；题面统一放在 `statement` 中。
输出、执行计数和其他 Notebook 元数据不会进入题目框架，导出题包也不包含学生草稿。

`data/` 最多 16 个 UTF-8 CSV，序列化后总计最多 1 MiB。文件名仅允许字母、数字、下划线、短横线和 `.csv`。
这些文件会公开下载，并在 Notebook / 代码提交的 `data/` 目录提供，不能放隐藏标签。
私有材料只放在 `evaluation/`；程序包支持同目录辅助文件，文件路径使用 ASCII 字母、数字、下划线、点、短横线和目录分隔符。
`metadata.yaml` 由平台生成，不能随题包指定。

## 评测程序接口

程序在平台固定 Python / PyTorch 镜像中隔离执行，无网络，不可安装临时依赖。
平台固定执行 `python -I /app/program/program.py`，导入与注册过程不会执行题包里的 Python。

| 阶段 | 输入 | 输出 |
| --- | --- | --- |
| 运行程序 ingestion | `/app/ingested_program/solution.py` 为拼接的选手代码；公开文件在其 `data/` 下；`/app/input_data/` 为题包评测输入 | 把供评分检查的产物写入 `/app/output/` |
| 评分程序 scoring | `/app/input/res/` 为上一阶段产物或挑战提交的 `predictions.csv`；`/app/input/ref/` 为私有参考数据 | `/app/output/scores.json`，例如 `{"score": 100}` |

运行程序与选手代码处在同一不可信容器，不接触私有参考答案。
评分程序在另一容器读取产物；应验证形状、范围、有限数值等，不执行选手代码、pickle 或其他可执行反序列化数据。
若需静态检查源码，可读取 `/app/ingested_program/solution.py`，但静态课程约束不构成防作弊证明。
按实际镜像已安装的依赖编写程序，参见 `ai/notebook/pyproject.toml`。

## 出题工具与编辑

出题目录、题包、参考解与数据都放在仓库外：

```sh
python3 ai/tools/problem_package.py build /private/problem-source /private/problem.zip
python3 ai/tools/problem_package.py validate /private/problem.zip
```

工具只依赖 Python 标准库，使用与服务端相同的校验器，拒绝覆盖已有 ZIP。
后台可编辑题面、作答框架和公开数据。编辑采用独立的 `revision` 防止并发覆盖。
题面、标题和展示指标的编辑保留评测版本及历史成绩；框架或公开数据变化增加评测版本，历史答卷和草稿仍保留。
题型、评分程序与配置随题包绑定，更换时导出修改后重新导入为新题目；比赛中使用的题目禁止编辑。

批量导出最多 20 道题，包含当前题面、框架、公开数据及原始私有评测资产。
导出不包含运行凭据、服务器 ID、学生答卷；可在另一套 OJ 导入并自动注册新的评测环境。

## 运维与既有题目归档

正常导入也可以使用后端命令，仍进入同一队列：

```sh
python manage.py import_ai_package /private/problem.zip --creator teacher --preview
python manage.py import_ai_package /private/problem.zip --creator teacher
```

不再提供生成固定练习题的 bootstrap。Codabench 初始化只准备存储与服务账号；新增 `package-agent` 负责出站领取题包注册任务。
90 秒租约及同一导入 ID 保证失联恢复不会重复创建题目或 Phase；最多自动领取三次，管理员可显式重试。
发布暂停同时阻止新计算与确认导入，已入队任务继续排空。跨库无法使用单一事务：已注册但尚未在 OJ 发布的私有资产保留，重试复用；OJ 整批创建保持原子。

旧题显示“待归档”时，不允许导出一个缺少评测数据的残缺包。
管理员应先备份，从当前 OJ 数据库导出完整题目 manifest，再在 Codabench 镜像运行
`python /opt/xju/export_existing.py /private/manifest.json /private/new-archive-directory`。
manifest 每项为 `id,title,type,metric,points,statement,cells,public_files,judge`，必须读取现存数据库值。
工具下载实际使用的私有对象并记录摘要，不重新生成测试数据；仅支持无额外参数的旧 `python -I /app/program/<entry>` 入口。
在 OJ 通过 `import_ai_package problems.zip --creator <超级管理员> --adopt-existing bindings.json` 归档。
该操作严格比对题面、框架、数据、评分配置及题包摘要，只增加归档关联，保留题号、作者、可见性、版本、草稿和成绩。
运行于私有管理挂载，禁止把 manifest、bindings 或题包置于 `/public`。

必须共同备份 OJ PostgreSQL、后端 `DATA_DIR/ai_problem_packages/`、Codabench PostgreSQL、私有对象存储及服务配置。
根 `deploy.sh` 的自动数据库备份不包含文件；`deploy/ops/backup-fixture.sh` 会额外保存题包目录。
先暂停导入、排空任务，再保存一致备份。恢复时先在隔离环境核验，不能只恢复数据库而遗漏 ZIP。
