# server

`server/` 是判题服务主模块，内部保留两个不可混淆的边界：

- `judge-server/`：Flask/Gunicorn HTTP 服务、客户端和协议测试；对外保持 `POST /judge`、`POST /compile_spj`、`POST /ping` 以及心跳调用。
- `judger/`：C/Seccomp 核心和 Python/Node/Lua bindings；负责资源限制、系统调用规则和结果码。

## 运行约束

- JudgeServer 只读挂载后端测试数据 `/test_case`；`Problem.test_case_id` 与该路径的目录名保持绑定。
- `/judger`、`/log` 和 `/test_case` 的权限边界由当前镜像/入口脚本定义；不要让用户代码以容器 root 运行。
- `X-Judge-Server-Token` 继续使用配置 Token 的 SHA-256 摘要；协议字段、`err/data` 响应包装和测试点结果码见 `docs/contracts/judge-server-protocol.md`。
- `judge-server/` 与 `judger/` 必须独立测试和构建；不得再次引入空的 `judge-server/Judger/` 或复制第二份 Judger 源码。
- 统一构建上下文是仓库根目录，由 `server/Dockerfile` 构建 `server/judger/` 与 `server/judge-server/`；正式构建输入使用版本锁定的基础镜像 digest。
- JudgeServer 优先从 `TOKEN_FILE` 读取原始 Token，回退到 `TOKEN`；两者都只在内存中计算 SHA-256，日志不输出 Token 或摘要。
- Docker healthcheck 只执行本机 `/ping` liveness；heartbeat 由独立后台循环发送，后端不可达只标记 degraded，不使主进程 unhealthy。

## 构建与检查

```bash
docker buildx build --file server/Dockerfile --target judge-server --platform linux/amd64 --load .
python3 -m unittest server/judge-server/tests/test_protocol_contract.py
```

## 许可证

`judge-server/LICENSE` 与 `judger/LICENSE` 保留各自的 SATA 文本和上游归属。边界说明见 [LICENSES.md](LICENSES.md)。

生产只使用 Python 绑定。NodeJS 和 Lua 绑定保留为上游历史源码，未适配现行 ABI，不属于受支持的运行入口；不要安装或以特权运行其旧测试。
