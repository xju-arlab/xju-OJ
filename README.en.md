<div align="center">
  <h1>XJU-OJ</h1>
  <p><strong>A modern online judge for programming assessments, ACM, and OI</strong></p>
  <p>A 400+ problem library, local sandbox judging, and browser-assisted remote judging for Nowcoder, Luogu, and Codeforces.</p>
  <p>
    <a href="https://oj.icthub.top"><img alt="OJ status" src="https://img.shields.io/website?url=https%3A%2F%2Foj.icthub.top&up_message=online&down_message=offline&label=OJ"></a>
    <a href="https://github.com/xju-arlab/xju-OJ/actions/workflows/publish-release-images.yml"><img alt="Release images" src="https://github.com/xju-arlab/xju-OJ/actions/workflows/publish-release-images.yml/badge.svg"></a>
    <a href="https://github.com/xju-arlab/xju-OJ/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/xju-arlab/xju-OJ?logo=github"></a>
    <img alt="Vue 3.5.41" src="https://img.shields.io/badge/Vue-3.5.41-42b883?logo=vuedotjs&logoColor=white">
    <img alt="Django 5.2.17" src="https://img.shields.io/badge/Django-5.2.17-092E20?logo=django&logoColor=white">
    <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  </p>
  <p>
    <a href="https://oj.icthub.top">Live site</a> ·
    <a href="https://oj.icthub.top/remote-bridge">Remote judge helper</a> ·
    <a href="#quick-install">Quick install</a> ·
    <a href="README.md">简体中文</a>
  </p>
</div>

## Highlights

- **400+ problems** for programming assessments, ACM, and OI practice.
- **Local and remote judging** through JudgeServer/Judger plus a ScriptCat bridge for Nowcoder, Luogu, and Codeforces.
- **Complete contest workflows** with ACM/OI rules, registration, problem composition, live submission states, and rankings.
- **Modern full stack** built with Vue 3, Vite 8, Django 5.2, PostgreSQL 18, and Redis 8.
- **Secure identity integration** with Authentik OIDC, session management, user profiles, and a separate admin console.

## Quick install

Requirements:

- Ubuntu 22.04 or newer on `linux/amd64`
- Docker Engine, Docker Compose v2, and Docker Buildx
- Git, Python 3, and curl
- At least 20 GB of available disk space is recommended

Use the [official Docker Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/).

```bash
git clone https://github.com/xju-arlab/xju-OJ.git
cd xju-OJ
cp .env.example .env
./deploy.sh
```

On the first run, `deploy.sh` securely prompts for the PostgreSQL password, Django secret key, JudgeServer token, and initial administrator password. Input is not echoed or written to ordinary logs. Secret files and mutable data are stored outside the checkout under `~/.local/share/xju-oj/` by default, and existing secrets are never overwritten.

The secure default listens only on:

```text
http://127.0.0.1:18080
```

Use an SSH tunnel for remote rehearsal access:

```bash
ssh -N -L 18080:127.0.0.1:18080 user@server
```

Then open:

```text
http://127.0.0.1:18080/
http://127.0.0.1:18080/admin/
```

The first build creates the PostgreSQL 18.6 Alpine derivative with the patched `gosu`, then builds the frontend, backend, Judge toolchain, and JudgeServer. Redis uses the digest-pinned 8.2.8 Alpine image. Duration depends on network and host performance.

`deploy.sh` clears inherited `http_proxy`, `https_proxy`, `ALL_PROXY`, and equivalent host variables. Runtime containers do not inherit them. Only explicit `BUILD_*_PROXY` values in `.env` may affect PostgreSQL `gosu` and frontend build downloads, and they never enter runtime.

## Configuration

Edit `.env` before deployment when needed:

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

Important rules:

- Keep `COMPOSE_PROJECT_NAME` stable after the first installation.
- Keep `DEPLOY_ROOT` outside the Git checkout.
- Prefer `HTTP_BIND_ADDRESS=127.0.0.1` and proxy the public domain to `127.0.0.1:18080` with Nginx, Caddy, or a load balancer.
- `DEPLOY_MODE=pull` accepts only immutable `image@sha256:...` references.
- Set `SECRET_PROVISION_MODE=external` and configure the four `*_FILE` paths when an external Secret manager owns provisioning.

See [`.env.example`](.env.example) for every setting.

## DNS and HTTPS

DNS points a domain to the server IP; it cannot include port `18080`:

```text
A     oj     <server public IPv4>
CNAME www    oj.example.edu.cn
```

A reverse proxy should terminate TLS and forward requests to:

```text
http://127.0.0.1:18080
```

Do not store TLS private keys in `.env` or Git.

## Operations

```bash
# Run full preflight without creating directories, building, or starting services
./deploy.sh --dry-run

# Validate .env, Compose rendering, and published-port boundaries only
./deploy.sh --config-only

# Upgrade or redeploy
git pull --ff-only
./deploy.sh

# Inspect service status
docker compose --env-file .env -f compose.yaml ps

# Create an isolated fixture backup
./deploy/ops/backup-fixture.sh

# Stop while preserving data and secrets
docker compose --env-file .env -f compose.yaml down
```

Never use `down -v`, `docker volume prune`, or `docker system prune --volumes` for normal operations.
