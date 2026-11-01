<div align="center">
  <h1>XJU-OJ</h1>
  <p><strong>A modern online judge for programming assessments, ACM, and OI</strong></p>
  <p>A 400+ problem library, local sandbox judging, and browser-assisted remote judging for Nowcoder, Luogu, and Codeforces.</p>
  <p>
    <img alt="Vue 3.5" src="https://img.shields.io/badge/Vue-3.5-42b883?logo=vuedotjs&logoColor=white">
    <img alt="Vite 8" src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white">
    <img alt="Element Plus 2.14" src="https://img.shields.io/badge/Element_Plus-2.14-409EFF?logo=element&logoColor=white">
    <img alt="Pinia 4" src="https://img.shields.io/badge/Pinia-4-F7D336?logo=pinia&logoColor=black">
    <img alt="Django 5.2" src="https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white">
    <img alt="Python 3.10" src="https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white">
    <img alt="Dramatiq 2.2" src="https://img.shields.io/badge/Dramatiq-2.2-4B5563">
    <img alt="PostgreSQL 18" src="https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white">
    <img alt="Redis 8" src="https://img.shields.io/badge/Redis-8-FF4438?logo=redis&logoColor=white">
    <img alt="Seccomp + Landlock" src="https://img.shields.io/badge/Sandbox-Seccomp%20%2B%20Landlock-FCC624?logo=linux&logoColor=black">
    <img alt="Jupyter + PyTorch" src="https://img.shields.io/badge/AI-Jupyter%20%2B%20PyTorch-EE4C2C?logo=pytorch&logoColor=white">
    <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  </p>
  <p>
    <a href="https://oj.icthub.top"><img alt="OJ status" src="https://img.shields.io/website?url=https%3A%2F%2Foj.icthub.top&up_message=online&down_message=offline&label=OJ"></a>
    <a href="https://github.com/xju-arlab/xju-OJ/actions/workflows/regression.yml"><img alt="Regression checks" src="https://github.com/xju-arlab/xju-OJ/actions/workflows/regression.yml/badge.svg"></a>
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
- **Complete contest workflows** with ACM/OI rules, registration, problem composition, live submission states, and rankings; ACM boards freeze for the last hour and admins unfreeze them after the contest.
- **Team-account contests**: a team CSV generates `team-xxxx` accounts and A4 account slips, with official and star (unranked) teams. Teams sign in through a dedicated `/arena` link, wait on a poster carousel before the start, enter automatically, and only official teams take places on the board.
- **Contest preparation workspace**: invite organizers, assign problems, track authoring progress, review without a time limit, export olymp-style statement PDFs, and publish once as a regular contest.
- **AI Studio** with Jupyter notebooks, Codabench evaluation, AI contests, and public/private leaderboards. See the [AI Studio guide](ai/README.md).
- **Modern full stack** built with Vue 3, Vite 8, Django 5.2, PostgreSQL 18, and Redis 8.
- **Secure identity integration** with Authentik OIDC, session management, user profiles, and a separate admin console.

Operations records: [release and recovery](docs/operations/release-and-recovery.md), [October audit](docs/operations/audit-2026-10.md), and [live 20-minute contest acceptance](docs/operations/acceptance-2026-10-07.md) (Chinese).

## Quick install

Requirements:

- Ubuntu 22.04 or newer on `linux/amd64`
- The host kernel must provide Landlock ABI 3 or newer for Java and File IO judging. Ubuntu 22.04's default 5.15 kernel is insufficient; install the official HWE 6.8 kernel and reboot. `./deploy.sh --dry-run` checks this capability before builds or service changes.
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

## Repository layout

- `frontend/`: Vue 3, Vite 8, Pinia, and Element Plus user site and `/admin/` console
- `backend/`: Django 5.2 API and Dramatiq worker
- `server/`: JudgeServer and the Judger/Seccomp sandbox
- `ai/`: AI Studio notebooks, Codabench evaluation, and the package agent, deployed separately
- `deploy/`: data service images (`deploy/images/`) and operations scripts (`deploy/ops/`)
- `docs/`: compatibility contracts, upgrade plans, and acceptance records
- `tools/`: development tools such as the remote judge probe
- `compose.yaml`, `compose.dev.yaml`: service topology and the frontend development override
- `deploy.sh`, `docker-bake.hcl`: build, bootstrap, migration, start, and smoke entry points
- `aoci*.txt`, `.aoci/`: the repository cognition index; see [AGENTS.md](AGENTS.md)
