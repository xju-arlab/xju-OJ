# 发布与恢复

生产统一使用一个主分支检出目录和一套 Compose 项目。开发桥仅用于本地，不加载到 huawei1 生产。

```sh
git pull --ff-only origin main
./deploy.sh
```

发布前检查工作树干净、运行根和 `COMPOSE_PROJECT_NAME` 与既有部署一致。服务器临时修改先保存私有补丁或本地归档分支并整合回主仓库，不直接覆盖。`.env` 和密钥留在 Git 之外。

`deploy.sh` 使用运行根下的排他锁，按组件的镜像修订号判断复用。`current.json` 记录本次检出提交与每个组件实际来源，两者允许不同；未改变的数据库和工具链无需重建。只有镜像、服务和 HTTP/Worker/心跳冒烟通过，才前移发布指针。

每次全栈迁移前，数据库以 `pg_dump -Fc` 保存到私有 `BACKUP_ROOT`，成功后才执行迁移。失败留下 `.partial`，不会当作完整备份。数据库备份不包含题目测试文件、头像、Redis 和外部密钥；涉及数据迁移或恢复时还需独立保护这些资产。禁止 `docker compose down -v`，禁止清空判题队列。

## GitHub 网络受限时

2026-10-07 验收时，huawei1 原有 Git 代理 `127.0.0.1:10808` 没有监听，GitHub HTTPS 直连也超时。本次发布通过 SSH 转发运维工作站已有的本地 HTTP 代理完成拉取；代理可用性属于发布前置条件，不影响已运行的 OJ。

如果工作站的 `127.0.0.1:10808` 确实提供可访问 GitHub 的 HTTP 代理，可在工作站保持以下独立连接：

```sh
ssh -o ControlMaster=no -o ControlPath=none -o ExitOnForwardFailure=yes \
  -N -R 127.0.0.1:19480:127.0.0.1:10808 huawei1
```

在服务器的主检出目录中，仅为本次 Git 命令覆盖代理：

```sh
git -c http.proxy=http://127.0.0.1:19480 \
  -c http.lowSpeedLimit=100 -c http.lowSpeedTime=20 pull --ff-only origin main
```

完成后在工作站按 Ctrl-C 关闭该独立连接。转发只监听服务器回环地址；不要把临时端口写入长期 Git 配置或业务容器环境。没有可用代理时应先恢复网络出口，保留当前服务，不用来源不明的镜像站替换仓库。

## 判题宿主机

Java 和文件 IO 的写入隔离要求宿主支持 Landlock ABI 3 或更高版本。容器内核来自宿主，升级判题镜像不能补足旧内核能力。全栈部署和 `--dry-run` 在构建前运行 `deploy/ops/check-judge-host.py`；`--frontend-only` 与只解析配置的 `--config-only` 不执行此检查。

Ubuntu 22.04 默认的 5.15 内核只有 ABI 1。可安装官方 `linux-image-generic-hwe-22.04`，保留旧内核并在维护窗口重启，再运行能力检查和真实判题测试。不要降低 ABI 要求或关闭沙箱来绕过失败。依据：[Linux Landlock 文档](https://docs.kernel.org/userspace-api/landlock.html)、[Ubuntu HWE 生命周期](https://ubuntu.com/kernel/lifecycle)。

替换 JudgeServer 或重启宿主前，先停止接受新的提交，再让 Worker 完成已有任务；确认执行中本地提交及判题节点 `task_number` 为零，并保留待判和 broker 队列。不要在仍有任务时停止判题容器。停止服务前记录其重启策略；`unless-stopped` 容器被手工停止后不会因宿主重启自动恢复，需要显式启动。重启后检查 API、Worker 实际消费、判题新鲜心跳和一次真实提交。

## TLS 入口与客户端 IP

frontend 默认不信任客户端传来的转发头。若 Caddy 等 TLS 入口在前面，设置 `TRUSTED_PROXY_CIDRS` 为 **frontend 实际看到的入口源地址**，例如宿主入口通过 Docker 发布端口连接时的专用桥网关 `/32`。不填写整段公共地址或 `0.0.0.0/0`。直连 frontend 时保持为空。

Nginx 只接受这些入口传来的客户端 IP 和协议。修改网络后重新核对来源；IP 白名单比赛、会话 IP 记录和 HTTPS CSRF 都依赖该配置。公开端口仍默认只绑定回环。

## 回退

发布失败先保留日志与现场，检查 `deployments/history/attempt-*`、`current.json` 和 `previous.json`。无数据格式变化时，可选择上一成功发布的不可变应用镜像引用，按正常脚本更新对应服务，并再次检查提交判题和登录。

数据库已开放新写入后不能直接恢复旧 dump，否则会丢失新提交。需要恢复时，先冻结写入、备份当前现场、在独立数据库恢复验证，明确合并或保留新增数据后再切换。Caddy、数据库、缓存、测试数据与应用镜像分别记录恢复边界。
