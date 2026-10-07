<div align="center">
  <h1>XJU-OJ</h1>
  <p><strong>面向机试、ACM、OI 与 AI 的现代在线评测平台</strong></p>
  <p>400+ 题库、本地沙箱判题与牛客 / 洛谷 / Codeforces 远程判题，统一管理比赛、提交和个人做题记录。</p>
  <p>
    <a href="https://oj.icthub.top"><img alt="OJ status" src="https://img.shields.io/website?url=https%3A%2F%2Foj.icthub.top&up_message=online&down_message=offline&label=OJ"></a>
    <a href="https://github.com/xju-arlab/xju-OJ/actions/workflows/publish-release-images.yml"><img alt="Release images" src="https://github.com/xju-arlab/xju-OJ/actions/workflows/publish-release-images.yml/badge.svg"></a>
    <a href="https://github.com/xju-arlab/xju-OJ/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/xju-arlab/xju-OJ?logo=github"></a>
    <img alt="Vue 3.5.41" src="https://img.shields.io/badge/Vue-3.5.41-42b883?logo=vuedotjs&logoColor=white">
    <img alt="Django 5.2.17" src="https://img.shields.io/badge/Django-5.2.17-092E20?logo=django&logoColor=white">
    <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  </p>
  <p>
    <a href="https://oj.icthub.top">在线体验</a> ·
    <a href="https://oj.icthub.top/remote-bridge">远程判题助手</a> ·
    <a href="#一键安装">快速部署</a> ·
    <a href="README.en.md">English</a>
  </p>
</div>

## 项目亮点

- **丰富题库**：现有 400+ 道题目，覆盖机试、ACM 与 OI 日常练习。
- **双重判题能力**：内置 JudgeServer/Judger 沙箱，并通过 ScriptCat 支持牛客、洛谷和 Codeforces 浏览器远程判题。
- **完整竞赛体验**：支持 ACM/OI 赛制、比赛报名、题目编排、实时提交状态和排名。
- **AI 工作台**：Jupyter Notebook 作答、Codabench 自动评测、逻辑实现/模型定义/数据挑战，支持 AI 比赛、公私榜与赛后补题。部署与能力边界见 [AI Studio 文档](ai/README.md)。
- **现代全栈架构**：Vue 3、Vite 8、Django 5.2、PostgreSQL 18、Redis 8，提供统一 Docker Compose 部署入口。
- **安全账户体系**：支持 Authentik OIDC、会话管理、个人资料和独立管理后台。

维护说明：[发布与恢复](docs/operations/release-and-recovery.md)、[2026-10 审计与回归范围](docs/operations/audit-2026-10.md)、[线上 20 分钟测试赛验收](docs/operations/acceptance-2026-10-07.md)。

## 一键安装

### 环境要求

- Ubuntu 22.04 或更新版本，`linux/amd64`
- 宿主内核必须启用 Landlock ABI 3 或更高版本，供 Java 和文件 IO 沙箱使用。Ubuntu 22.04 默认的 5.15 内核不满足要求，需安装官方 HWE 6.8 内核并重启；`./deploy.sh --dry-run` 会在构建和服务变更前检查实际能力。
- Docker Engine
- Docker Compose v2
- Docker Buildx
- Git、Python 3、curl
- 建议至少保留 20 GB 可用磁盘空间

Docker 安装请使用 [Docker 官方 Ubuntu 文档](https://docs.docker.com/engine/install/ubuntu/)。

### 克隆并部署

```bash
git clone https://github.com/xju-arlab/xju-OJ.git
cd xju-OJ
cp .env.example .env
./deploy.sh
```

第一次运行会在终端中依次询问：

1. PostgreSQL 密码
2. Django secret key
3. JudgeServer token
4. 初始管理员密码（输入两次）

输入内容不会回显，也不会进入 Git 或普通部署日志。Secret 默认存放在 `~/.local/share/xju-oj/secrets/`，权限为 `0600`；以后重复运行 `./deploy.sh` 不会覆盖已有 Secret、管理员或 Judge token。

默认配置只监听：

```text
http://127.0.0.1:18080
```

远程服务器上可使用 SSH 隧道访问：

```bash
ssh -N -L 18080:127.0.0.1:18080 user@server
```

浏览器打开：

```text
http://127.0.0.1:18080/
http://127.0.0.1:18080/admin/
```

首次构建会生成修补 `gosu` 的 PostgreSQL 18.6 Alpine 派生镜像，并构建 frontend、backend、Judge toolchain 和 JudgeServer；Redis 使用固定 digest 的 8.2.8 Alpine 镜像。耗时取决于网络与机器性能。

部署过程会实时显示每个构建、启动和 smoke 步骤的输出；完整日志同时保存在 `${RUNTIME_ROOT}/deployments/history/attempt-*`。默认无输出 60 秒时打印一次等待心跳，可通过 `DEPLOY_HEARTBEAT_SECONDS=120` 等方式调整为更稀疏的提示。

`deploy.sh` 会主动清除宿主继承的 `http_proxy`、`https_proxy`、`ALL_PROXY` 等变量，运行容器也不会继承这些变量。只有 `.env` 中显式填写的 `BUILD_*_PROXY` 可用于 PostgreSQL `gosu` 和 frontend 构建下载，且不会进入运行时。

## `.env` 常用配置

部署前可编辑 `.env`：

```dotenv
COMPOSE_PROJECT_NAME=xju-oj
APP_DOMAIN=oj.example.edu.cn
PUBLIC_BASE_URL=https://oj.example.edu.cn
HTTP_BIND_ADDRESS=127.0.0.1
HTTP_PORT=18080
DEPLOY_ROOT=${HOME}/.local/share/xju-oj
INITIAL_ADMIN_USERNAME=admin
DEPLOY_MODE=build
```

关键说明：

- `COMPOSE_PROJECT_NAME` 是部署身份，首次安装后不要随意修改。
- `DEPLOY_ROOT` 保存 PostgreSQL、Redis、上传文件、备份、Secret 和部署记录，必须位于 Git 仓库外。
- 推荐保持 `HTTP_BIND_ADDRESS=127.0.0.1`，由宿主 Nginx/Caddy/负载均衡器代理到 `127.0.0.1:18080`。
- 若确实要直接暴露测试端口，可改为 `HTTP_BIND_ADDRESS=0.0.0.0`；backend、Judge、PostgreSQL 和 Redis 仍不会发布宿主端口。
- `DEPLOY_MODE=pull` 只接受 `image@sha256:...`，拒绝 mutable tag。
- 外部 Secret 管理场景可设置 `SECRET_PROVISION_MODE=external` 并填写四个 `*_FILE` 路径。

完整字段和注释见 [`.env.example`](.env.example)。

### 从 Authentik 主机安全注入 OIDC

生产 OJ 不应把 Authentik client secret 贴入聊天、命令行或 `.env`。仓库提供
`ops/configure-authentik-oidc.py`：可在 OJ 主机本地隐藏输入，也可接收 Authentik
主机 root 环境通过 SSH 管道传来的两行值，并原子写入 `.env` 与 0600 secret 文件。
脚本会固定 issuer、callback、xju-OJ 专用 registration URL、`groups` scope，并关闭 OJ
本地登录/注册。

已有 Authentik 账号若未绑定邮箱，可先登录身份服务并打开
`https://auth.icthub.top/if/flow/icthub-bind-email/`，通过一次性邮件链接验证新邮箱。
已有 OJ 本地账号若没有邮箱，可在 OJ 登录窗口选择“旧 OJ 账号未绑定邮箱”，
用原 OJ 密码、图形验证码和原有两步验证码确认身份，再登录已验证邮箱的
Authentik 账号完成关联。关联成功后，OJ 将保存已验证的邮箱；此过程不会
临时开放普通本地登录。原 OJ 账号若没有可用密码，需要管理员核实身份后处理。

## 域名与 HTTPS

DNS 只能指向服务器 IP，不能指定 `18080` 端口。典型配置：

```text
A     oj     <服务器公网 IPv4>
CNAME www    oj.example.edu.cn
```

然后在宿主反向代理中配置：

```nginx
server {
    listen 80;
    server_name oj.example.edu.cn;

    client_max_body_size 256m;

    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

TLS 证书应由宿主 Nginx/Caddy/云负载均衡器管理，不要写入 `.env` 或 Git。

## 日常操作

执行完整预检但不创建目录、不构建、不启动：

```bash
./deploy.sh --dry-run
```

只验证 `.env`、Compose 渲染和端口发布边界：

```bash
./deploy.sh --config-only
```

升级或重新部署：

```bash
git pull --ff-only
./deploy.sh
```

只迭代前端时使用隔离发布路径：

```bash
git pull --ff-only
BUILD_TARGETS=frontend ./deploy.sh --frontend-only
```

该模式只构建并替换 `frontend` 容器，不执行数据库迁移、后端 bootstrap、管理员/token 初始化，也不重启 backend、Worker、Judge、PostgreSQL 或 Redis。它要求已有成功的完整 release 和本地保留的其他镜像；如果自上次 release 以来检测到 `frontend/` 以外的代码、Compose 或部署变更，会直接拒绝，避免前后端版本不匹配。前端 Dockerfile 已将 Node/pnpm 基础镜像和依赖下载分层，首次构建后后续迭代会复用本机 BuildKit/pnpm cache。

预检和回滚演练：

```bash
BUILD_TARGETS=frontend ./deploy.sh --frontend-only --dry-run
docker compose --env-file .env -f compose.yaml ps
```

前端-only 发布失败会保留 `runtime/deployments/history/attempt-*` 和 `previous.json`；不要删除旧镜像，回滚时按 [前端快速迭代计划](docs/plans/oj-modernization-2026/31-frontend-fast-iteration.md) 使用上一成功 frontend image 重建 frontend 容器。

查看状态：

```bash
docker compose --env-file .env -f compose.yaml ps
```

生成隔离备份：

```bash
./deploy/ops/backup-fixture.sh
```

停止服务但保留数据与 Secret：

```bash
docker compose --env-file .env -f compose.yaml down
```

不要使用 `down -v`、`docker volume prune` 或 `docker system prune --volumes`。

## 目录

- `frontend/`：Vue 3、Vite 8、Pinia、Element Plus 用户端和 `/admin/` 管理端
- `backend/`：Django 5.2 API 与 Dramatiq Worker
- `server/`：JudgeServer 与 Judger/Seccomp 沙箱
- `compose.yaml`：隔离服务拓扑
- `deploy.sh`：构建、初始化、迁移、启动和 smoke 入口
- `docs/`：兼容合同、升级计划和验收记录
