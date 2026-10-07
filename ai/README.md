# AI Studio / AI 评测赛制

OJ 负责账号、题库、比赛门禁、草稿、答卷和排名；Jupyter 执行公开调试；
Codabench 在独立 ingestion/scoring 容器中产生正式成绩。导航沿用「AI 工作台 / AI Studio」，
比赛赛制为 AI，普通比赛列表与 AI 工作台都能进入同一场比赛。

## 当前能力

- 逻辑实现：全部通过、部分通过、未通过；模型定义：Accuracy 与达标状态；
  数据挑战：公榜得分，比赛结束且管理员公布后才返回私榜得分。
- 题目框架、公开 CSV、按账号/题目/比赛隔离的云端草稿、冲突检测、本机备份、Notebook 导出。
- 「运行全部」启动真实 Jupyter 内核，返回文本、PNG 和 `predictions.csv`。
  每次运行是一个新内核，当前不提供持续在线的 JupyterLab 文件系统或终端。
- 正式提交保存不可变答卷；浏览器不能上报成绩。按服务器收到提交的时刻确定正式参赛资格，
  赛中提交在赛后完成仍计入成绩。赛后练习不改变正式排名。
- 密码报名、赛前锁题、赛中 IP 限制、赛后补题开关、比赛公告、最后一次提交/最高分、
  题目分值、私榜发布。比赛开始后锁定题目编排、权重和计分方式。
- 后台「AI 题库」管理题面、框架、公开数据和私有评分配置；比赛编辑页提供 AI 评测设置。
  已有答卷的 AI 比赛只能隐藏，保留评测记录。

五道 `AI001`–`AI005` 是可执行的练习题，覆盖线性回归、稳定 Softmax、XOR 训练和两项数据挑战。
初始化不会创建正式考试。考试应使用独立的隐藏题目及 Codabench Phase；不要把已公开练习题当作保密试题。
数据由私有随机种子生成；参考标签和参考解不进入 OJ 公开 API。
线性回归的 AST 检查用于约束普通 `nn.Linear`/`torch.optim` 调用，不能证明恶意混淆代码没有绕过课程要求。

## 隔离与容量

学生容器使用 UID 65532、无网络、只读根目录、移除 capabilities、禁止提权，
不挂载 Docker socket、服务令牌或数据库。Notebook 上限 2 CPU / 2 GiB / 128 进程；
评测上限 1 CPU / 1536 MiB / 128 进程。可写文件使用有界 tmpfs，ZIP 拒绝路径越界、链接和超限解压。
可信代理和 Codabench compute 服务需要 Docker socket；它们只运行受信任的仓库代码。

默认一个 Notebook 槽位和一个正式评测槽位，适合本次 15 人的小数据集考核。
本地 15 人同时提交的实际结果见验收文档；生产容量仍需按部署主机实测。
H100 SSH 当前进入现有容器，缺少可用 Docker/隔离能力，因此没有启用 GPU，
也没有在其 root 环境直接执行学生代码。五道练习题使用 CPU PyTorch。

## 构建与首次部署

OJ 主应用先按根目录 `./deploy.sh` 发布并完成 Django 迁移，再启动 AI 附属服务。
AI 运行目录必须在 Git 仓库外，权限保持私有。下列命令中的路径、镜像和 OJ 地址按环境填写。

```sh
git pull --ff-only
./deploy.sh
sh ai/build.sh                      # 干净 HEAD，输出 git-<12位提交> 标签
python3 ai/prepare.py \
  --runtime /absolute/private/xju-ai \
  --project xju-ai \
  --oj-url https://oj.example.edu/api/ai/ \
  --tag git-<12位提交> \
  --postgres-image <已验证的PostgreSQL18镜像>
```

将私有运行目录 `secrets/oj_worker_token` 复制到 OJ 后端的
`runtime/backend/config/ai-worker-token`，文件权限 0600、所有者与后端容器内 `backend` 用户一致。
用 `docker compose exec -T backend-api id backend` 核对实际 UID/GID，不使用宿主登录用户的 UID。
两个位置必须是同一个值；不要放进 `.env`、提交记录或命令输出。

```sh
sh ai/deploy.sh /absolute/private/xju-ai
# 用 OJ 的管理命令，将 exports/oj-practice.json 导入后端；文件须放在后端能读取的私有挂载下。
python manage.py import_ai_practice /private/oj-practice.json --creator <已有超级管理员> --publish
```

导入命令只创建缺失题目，已有内容不一致时拒绝覆盖。`exports` 内另有私有种子和验收参考解，
不要整个目录放入 `/public`。Docker 服务没有宿主公开端口；Codabench 不单独提供学生登录入口。
首次导入后必须实测一次 Notebook 和一次正式评测，再组织真实考试。

## 升级、备份与故障恢复

1. 提交并推送源码，在服务器 `git pull --ff-only`，构建或加载绑定该 HEAD 的三个 AI 镜像。
2. 发布前用旧镜像运行 `python /opt/bridge/control.py pause --wait 1800`（在 evaluation-agent 中）。
   新计算请求暂停，已有任务继续排空，草稿可保存/导出。无需删除队列。
3. 发布 OJ；修改私有 `compose.env` 中三个 AI 镜像标签；运行 `ai/deploy.sh`。
   脚本验证源码和镜像修订，确认任务排空，备份 Codabench PostgreSQL、对象存储、配置、种子和令牌，
   然后迁移、幂等初始化并恢复接收任务。OJ 自身的数据库备份由根部署脚本负责。
4. 检查 `/api/ai/health`，运行真实答卷，核对两端任务数和成绩。

配置已存在时 `prepare.py` 会拒绝重新生成密钥。不要运行 `down -v`、清 Redis 或删除提交来“排空”。
备份是私有数据；恢复时先暂停接收并停止相关消费者，将数据库和对象存储恢复到新的隔离卷验证，
再切换。恢复旧备份会丢失其后的新答卷，不能作为普通代码回滚使用。
失败的部署保持暂停状态；修复后通过 `control.py status` 核验并显式 `resume`。
工作空间 tmpfs 只存临时评测文件，重启后任务由 OJ 的 90 秒租约重新认领；最多三次。
已发送到 Codabench 的任务按远程 ID 或唯一文件名恢复查询，发送结果不确定时不会盲目重交。

## 验证

```sh
python3 -m unittest discover -s ai/tests -p 'test_*.py'
XJU_AI_RUNTIME_TESTS=1 AI_NOTEBOOK_IMAGE=xju-ai-notebook:dev \
  python3 -m unittest discover -s ai/tests -p test_runtime.py
```

另运行后端全量 Django 测试、前端 lint/routes/build、Playwright。
`tests/live_acceptance.py` 使用明确准备的 1 个管理员和 15 个受控学生会话，
实际运行 20 分钟，验证密码、并发评测、五道题、草稿冲突、私榜和补题。
该脚本会创建一场可见的密码测试赛，结束后隐藏，保留答卷证据；只对明确选定的环境运行。
外部 Authentik 登录、真实邮件投递和第三方 OJ 提交不由这些会话测试证明。

## 上游与许可证

Codabench：[codalab/codabench](https://github.com/codalab/codabench)，
锁定提交 `e40d067ea3b61b9d7fa0146b7c075ed3d677862c`，Apache-2.0。
构建使用仓库外的干净上游 checkout，并在两个运行镜像的
`/usr/share/licenses/codabench/LICENSE.TXT` 保留原始许可。
`secure_worker.py` 是本项目对该固定版本的隔离边界适配，升级上游时必须重新验证这些方法及完整评测流程。
