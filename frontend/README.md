# frontend

这是单仓库中的浏览器静态入口，Phase 3 最终运行栈为 Vue 3、Vue Router 5、Pinia、vue-i18n 11、Element Plus 和 Vite 8。

- 用户端和 `/admin/` 管理端保持两个 history 入口。
- Axios 同源基址继续是 `/api`，CSRF Cookie/Header 继续使用 `csrftoken`/`X-CSRFToken`。
- `/public` 由部署层发布后端运行时公开资源；前端不直接读取测试数据。
- Node 固定为 `24.19.0`，pnpm 固定为 `11.22.0`；`pnpm-lock.yaml` 是唯一依赖真源。
- CodeMirror 6 与 Tiptap 通过本地 adapter 保留旧 `value/input/change/update:value`、上传端点和历史 HTML/附件合同。
- `pnpm run build` 生成用户端和管理端双入口；Vue 2/Vite 7 的 Phase 2 immutable image 作为 N-1 回滚资产保留，不再从当前源码重建。
- 运行时域名和非秘密版本信息由 Nginx entrypoint 写入 `/runtime-config.js`，不把 Secret 编译进 bundle。

## 原始模块说明

以下保留原 OnlineJudgeFE 的开发说明。

### OnlineJudge Front End
[![vue](https://img.shields.io/badge/vue-2.5.13-blue.svg?style=flat-square)](https://github.com/vuejs/vue)
[![vuex](https://img.shields.io/badge/vuex-3.0.1-blue.svg?style=flat-square)](https://vuex.vuejs.org/)
[![echarts](https://img.shields.io/badge/echarts-3.8.3-blue.svg?style=flat-square)](https://github.com/ecomfe/echarts)
[![iview](https://img.shields.io/badge/iview-2.8.0-blue.svg?style=flat-square)](https://github.com/iview/iview)
[![element-ui](https://img.shields.io/badge/element-2.0.9-blue.svg?style=flat-square)](https://github.com/ElemeFE/element)
[![Build Status](https://travis-ci.org/QingdaoU/OnlineJudgeFE.svg?branch=master)](https://travis-ci.org/QingdaoU/OnlineJudgeFE)

>### A multiple pages app built for OnlineJudge. [Demo](https://qduoj.com)

## Features

+ Webpack3 multiple pages with bundle size optimization
+ Easy use simditor & Nice codemirror editor
+ Amazing charting and visualization(echarts)
+ User-friendly operation
+ Quite beautiful：)

## Get Started

Use Node **24.19.0** and pnpm **11.22.0**. Do not replace the frozen-lockfile install with `npm install`.

```bash
corepack pnpm@11.22.0 install --frozen-lockfile
pnpm run lint:modern
pnpm run test:routes
pnpm run build

# the Vite dev-server requires a backend target and keeps /api + /public same-origin
export TARGET=http://127.0.0.1:8000
pnpm run dev
```

## 推荐的全栈前端开发模式

从仓库根目录执行：

```bash
./deploy.sh --dev frontend
```

该命令会启动 PostgreSQL、Redis、backend-api、backend-worker 和 judge-server
容器，但不会启动 Docker frontend；随后在本机前台运行 `frontend/pnpm dev`。
Vite 默认监听 `127.0.0.1:5173`，把 `/api` 和 `/public` 代理到
`127.0.0.1:8000`。首次运行若没有 `frontend/node_modules`，会自动执行
`pnpm install --frozen-lockfile`。按 Ctrl-C 只停止 Vite，Docker 后端服务继续运行。

可通过以下环境变量调整本机端口，但仍只允许绑定 loopback：

```bash
DEV_FRONTEND_HOST=127.0.0.1 DEV_FRONTEND_PORT=5173 \
DEV_BACKEND_BIND_ADDRESS=127.0.0.1 DEV_BACKEND_PORT=8000 \
./deploy.sh --dev frontend
```

生产部署仍使用普通 `./deploy.sh`；`compose.dev.yaml` 只在上述开发模式显式加载，
不会让生产 Compose 直接发布 backend-api。

Vue 2、Vuex、Element UI/iView、CodeMirror 5、Simditor、Webpack/Babel 6 和 Yarn Classic 已从最终源码与锁文件移除。

## Screenshots

[Check here.](https://github.com/QingdaoU/OnlineJudge)

## Browser Support

Current Chrome, Firefox, Safari and Edge. Internet Explorer is not supported.

## LICENSE

[MIT](http://opensource.org/licenses/MIT)
