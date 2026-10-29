# backend

这是单仓库中的 Django 业务 API 与异步任务模块，保留内部包名和 app label：`oj`、`account`、`announcement`、`conf`、`contest`、`fps`、`judge`、`options`、`problem`、`submission`、`utils`。

- `oj.settings`、`oj.wsgi`、`manage.py` 和所有迁移依赖保持原路径语义。
- 浏览器 API 继续挂在 `/api`，响应包装、Session/CSRF、数据库表名和 JudgeServer 心跳协议不变。
- PostgreSQL 保存业务数据；Redis DB 1 继续承载 Session/cache/waiting queue，DB 4 继续承载 Dramatiq broker/result。
- `OJ_DATA_DIR`/`RUNTIME_ROOT` 控制运行时目录；`data/test_case/<test_case_id>` 与 `Problem.test_case_id` 保持绑定，测试数据只供后端/判题服务使用。
- API、Worker、一次性 bootstrap/migrate/admin 命令由 `deploy/entrypoint.sh` 显式启动；frontend 负责静态资源、`/api` 和 `/public` 网关。
- `deploy/nginx/` 与 `deploy/supervisord.conf` 仅保留为迁移/回滚参考，不进入 backend 镜像运行路径。

## 原始模块说明

以下保留原 OnlineJudge 的开发说明。

### OnlineJudge 2.0

[![Python](https://img.shields.io/badge/python-3.8.0-blue.svg?style=flat-square)](https://www.python.org/downloads/release/python-362/)
[![Django](https://img.shields.io/badge/django-3.2.9-blue.svg?style=flat-square)](https://www.djangoproject.com/)
[![Django Rest Framework](https://img.shields.io/badge/django_rest_framework-3.12.0-blue.svg?style=flat-square)](http://www.django-rest-framework.org/)
[![Build Status](https://travis-ci.org/QingdaoU/OnlineJudge.svg?branch=master)](https://travis-ci.org/QingdaoU/OnlineJudge)

> #### An onlinejudge system based on Python and Vue. [Demo](https://qduoj.com)

[中文文档](README-CN.md)

## Overview

+ Based on Docker; One-click deployment
+ Separated backend and frontend; Modular programming; Micro service
+ ACM/OI rule support; realtime/non-realtime rank support
+ Amazing charting and visualization
+ Template-problem support
+ More reasonable permission control
+ Multi-language support: `C`, `C++`, `Java`, `Python2`, `Python3`
+ Markdown & MathJax support
+ Contest participants IP limit(CIDR)

Main modules are available below:

+ Backend(Django): [https://github.com/QingdaoU/OnlineJudge](https://github.com/QingdaoU/OnlineJudge)
+ Frontend(Vue): [https://github.com/QingdaoU/OnlineJudgeFE](https://github.com/QingdaoU/OnlineJudgeFE)
+ Judger Sandbox(Seccomp): [https://github.com/QingdaoU/Judger](https://github.com/QingdaoU/Judger)
+ JudgeServer(A wrapper for Judger): [https://github.com/QingdaoU/JudgeServer](https://github.com/QingdaoU/JudgeServer)

## Locked development environment

Phase 3 uses Python `>=3.10,<3.11` with Django `5.2.17`, Psycopg `3.3.4`, DRF `3.18.0`, redis-py `7.4.1`, django-redis `7.0.0`, Dramatiq `2.2.0` and django-dramatiq `0.15.0`. `pyproject.toml` + `uv.lock` are the dependency source of truth; the runtime image never resolves dependencies at startup.

为适配 huawei 构建网络，`uv.lock` 中的 registry 和 artifact URL 使用华为云 PyPI 公网镜像（`repo.huaweicloud.com`，与 PyPI 路径布局一致，本地和 CI 也能访问）；每个已锁定发行物的 SHA-256 保持不变。更换镜像必须重新生成并审查 lock，不能在生产构建中临时解除 `--locked`。

```bash
uv sync --locked --group dev
uv run --locked --no-sync python manage.py check
uv run --locked --no-sync python manage.py makemigrations --check --dry-run
```

Current models use Django `models.JSONField`; historical migration imports remain intact through the locked `jsonfield` loader. Five `SeparateDatabaseAndState` migrations update Django state only and emit no database DDL, preserving the existing PostgreSQL JSONB columns and N-1 schema readability.

## Backend commands

在 runtime 目录已经准备好后，可分别执行：

```bash
./deploy/entrypoint.sh bootstrap-runtime --dry-run
./deploy/entrypoint.sh migrate
./deploy/entrypoint.sh api
./deploy/entrypoint.sh worker
```

`configure-judge-token` 和 `create-initial-admin` 只接受外部 Secret/文件输入，已有配置或管理员时不会覆盖；不要把密码、Token 或 `secret.key` 写入命令行、镜像或日志。

`deploy/runtime_smoke.py` 可在 API 容器中检查 `/api/website/`、Redis DB 1/4 和一次短 TTL cache 往返；Worker 容器使用 `--worker` 只检查 Redis/队列依赖。

## Installation

Follow me:  [https://github.com/QingdaoU/OnlineJudgeDeploy/tree/2.0](https://github.com/QingdaoU/OnlineJudgeDeploy/tree/2.0)

## Documents

[http://opensource.qduoj.com/](http://opensource.qduoj.com/)

## Screenshots

### Frontend:

![problem-list](https://user-images.githubusercontent.com/20637881/33372506-402022e4-d539-11e7-8e64-6656f8ceb75a.png)

![problem-details](https://user-images.githubusercontent.com/20637881/33372507-4061a782-d539-11e7-8835-076ddae6b529.png)

![statistic-info](https://user-images.githubusercontent.com/20637881/33372508-40a0c6ce-d539-11e7-8d5e-024541b76750.png)

![contest-list](https://user-images.githubusercontent.com/20637881/33372509-40d880dc-d539-11e7-9eba-1f08dcb6b9a0.png)

You can control the menu and chart status in rankings.

![acm-rankings](https://user-images.githubusercontent.com/20637881/33372510-41117f68-d539-11e7-9947-70e60bad3cf2.png)

![oi-rankings](https://user-images.githubusercontent.com/20637881/33372511-41d406fa-d539-11e7-9947-7a2a088785b0.png)

![status](https://user-images.githubusercontent.com/20637881/33372512-420ba240-d539-11e7-8645-594cac4a0b78.png)

![status-details](https://user-images.githubusercontent.com/20637881/33365523-787bd0ea-d523-11e7-953f-dacbf7a506df.png)

![user-home](https://user-images.githubusercontent.com/20637881/33365521-7842d808-d523-11e7-84c1-2e2aa0079f32.png)

### Admin: 

![admin-users](https://user-images.githubusercontent.com/20637881/33372516-42c34fda-d539-11e7-9f4e-5109477f83be.png)

![judge-server](https://user-images.githubusercontent.com/20637881/33372517-42faef9e-d539-11e7-9f17-df9be3583900.png)

![create-problem](https://user-images.githubusercontent.com/20637881/33372513-42472162-d539-11e7-8659-5497bf52dbea.png)

![create-contest](https://user-images.githubusercontent.com/20637881/33372514-428ab922-d539-11e7-8f68-da55dedf3ad3.png)

## Browser Support

Modern browsers(chrome, firefox) and Internet Explorer 10+.

## Thanks

+ I'd appreciate a star if you find this helpful.
+ Thanks to everyone that contributes to this project.
+ Special thanks to [heb1c](https://github.com/hebicheng), who has given us a lot of suggestions.

## License

[MIT](http://opensource.org/licenses/MIT)
