import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const root = path.dirname(fileURLToPath(import.meta.url))
const resolve = (entry) => path.resolve(root, entry)

function copyStaticAssets () {
  return {
    name: 'copy-static-assets',
    closeBundle () {
      fs.cpSync(resolve('static'), resolve('dist/static'), { recursive: true })
    }
  }
}

// pdf.js fetches the Adobe CMaps for embedded CJK fonts from one directory by name, so they ship
// unhashed under a versioned path; PdfPages.vue builds the same URL from pdfjs.version.
const pdfjsCMaps = resolve('node_modules/pdfjs-dist/cmaps')
const pdfjsVersion = JSON.parse(fs.readFileSync(resolve('node_modules/pdfjs-dist/package.json'), 'utf8')).version
const pdfjsCMapPath = `/static/pdfjs-${pdfjsVersion}/cmaps/`

function pdfjsCMapAssets () {
  return {
    name: 'pdfjs-cmap-assets',
    configureServer (server) {
      server.middlewares.use(pdfjsCMapPath, (req, res, next) => {
        const name = decodeURIComponent((req.url || '').split('?')[0]).replace(/^\//, '')
        if (!/^[\w.-]+\.bcmap$/.test(name)) return next()
        fs.readFile(path.join(pdfjsCMaps, name), (error, data) => {
          if (error) return next()
          res.setHeader('Content-Type', 'application/octet-stream')
          res.end(data)
        })
      })
    },
    closeBundle () {
      fs.cpSync(pdfjsCMaps, resolve(`dist${pdfjsCMapPath}`), { recursive: true })
    }
  }
}

const DEFAULT_AUTHENTIK_REGISTER_URL = 'https://auth.icthub.top/if/flow/icthub-public-registration/'

function envBoolean (name, fallback) {
  const value = process.env[name]
  if (value === undefined || value === '') return fallback
  return /^(1|true|yes|on)$/i.test(value)
}

function contentTypeFor (filePath) {
  const extension = path.extname(filePath).toLowerCase()
  return {
    '.avif': 'image/avif',
    '.bmp': 'image/bmp',
    '.gif': 'image/gif',
    '.ico': 'image/x-icon',
    '.jpeg': 'image/jpeg',
    '.jpg': 'image/jpeg',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2'
  }[extension] || 'application/octet-stream'
}

function dependencyChunk (id) {
  const value = id.replaceAll('\\', '/')
  if (!value.includes('/node_modules/')) return undefined
  if (value.includes('@codemirror') || value.includes('@lezer')) return 'vendor-editor'
  if (value.includes('/element-plus/')) return 'vendor-element'
  if (value.includes('/katex/') || value.includes('/highlight.js/')) return 'vendor-markdown'
  if (value.includes('@tiptap') || value.includes('/prosemirror-')) return 'vendor-richtext'
  if (value.includes('/node_modules/vue/') || value.includes('/node_modules/@vue/') || value.includes('/vue-router/') || value.includes('/vue-i18n/') || value.includes('/pinia/')) return 'vendor-vue'
  return undefined
}

function devRuntimeConfig () {
  const frontendDevMode = envBoolean('OJ_FRONTEND_DEV_MODE', false)
  return {
    APP_DOMAIN: process.env.APP_DOMAIN || '',
    PUBLIC_BASE_URL: process.env.PUBLIC_BASE_URL || '/public',
    VERSION: process.env.GIT_COMMIT || 'dev',
    OJ_FRONTEND_DEV_MODE: frontendDevMode,
    DEV_LOGIN_USERNAME: frontendDevMode ? (process.env.OJ_DEV_ADMIN_USERNAME || 'admin') : '',
    DEV_LOGIN_PASSWORD: frontendDevMode ? (process.env.OJ_DEV_ADMIN_PASSWORD || '12345678') : '',
    AUTHENTIK_OIDC_ENABLED: frontendDevMode ? false : envBoolean('AUTHENTIK_OIDC_ENABLED', false),
    AUTHENTIK_OIDC_REGISTER_URL: process.env.AUTHENTIK_OIDC_REGISTER_URL || DEFAULT_AUTHENTIK_REGISTER_URL,
    AUTHENTIK_LOCAL_LOGIN_ENABLED: frontendDevMode ? true : envBoolean('AUTHENTIK_LOCAL_LOGIN_ENABLED', true),
    AUTHENTIK_LOCAL_REGISTER_ENABLED: frontendDevMode ? true : envBoolean('AUTHENTIK_LOCAL_REGISTER_ENABLED', true)
  }
}

function devRuntimeConfigPlugin () {
  return {
    name: 'dev-runtime-config',
    configureServer (server) {
      server.middlewares.use((req, res, next) => {
        const pathname = (req.url || '').split('?', 1)[0]
        const publicDirectory = process.env.OJ_DEV_PUBLIC_DIR
        if (publicDirectory && pathname.startsWith('/public/') && ['GET', 'HEAD'].includes(req.method)) {
          let relativePath
          try {
            relativePath = decodeURIComponent(pathname.slice('/public/'.length))
          } catch (_) {
            res.statusCode = 400
            res.end('Invalid public path')
            return
          }
          const publicRoot = path.resolve(publicDirectory)
          const filePath = path.resolve(publicRoot, relativePath)
          if (filePath !== publicRoot && !filePath.startsWith(`${publicRoot}${path.sep}`)) {
            res.statusCode = 403
            res.end('Forbidden')
            return
          }
          try {
            if (fs.statSync(filePath).isFile()) {
              res.statusCode = 200
              res.setHeader('Content-Type', contentTypeFor(filePath))
              res.setHeader('Cache-Control', 'no-store')
              if (req.method === 'HEAD') {
                res.end()
              } else {
                fs.createReadStream(filePath).on('error', next).pipe(res)
              }
              return
            }
          } catch (_) {
            // Let the regular proxy return its normal 404 for missing files.
          }
        }
        if (pathname === '/admin') {
          res.statusCode = 301
          res.setHeader('Location', '/admin/')
          res.end()
          return
        }
        // Vite's default SPA fallback serves the first HTML entry for direct
        // history requests. Keep the admin entry isolated in dev so
        // `/admin/login` behaves like the production double-entry build.
        if (pathname.startsWith('/admin/') && pathname !== '/admin/index.html' && !path.extname(pathname)) {
          req.url = '/admin/index.html'
          return next()
        }
        if (pathname !== '/runtime-config.js' || !['GET', 'HEAD'].includes(req.method)) return next()

        const body = `window.__XJU_RUNTIME_CONFIG__ = ${JSON.stringify(devRuntimeConfig(), null, 2)}\n`
        res.statusCode = 200
        res.setHeader('Content-Type', 'application/javascript; charset=utf-8')
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate')
        res.end(req.method === 'HEAD' ? undefined : body)
      })
    }
  }
}

export default defineConfig(({ mode }) => {
  const commit = process.env.GIT_COMMIT || 'unknown'
  const target = process.env.TARGET || 'http://127.0.0.1:8000'
  const devHost = process.env.VITE_DEV_HOST || '127.0.0.1'
  const useDevelopmentFixtures = mode === 'development' && envBoolean('OJ_FRONTEND_DEV_MODE', false)

  return {
    plugins: [devRuntimeConfigPlugin(), vue(), copyStaticAssets(), pdfjsCMapAssets()],
    base: '/',
    publicDir: false,
    resolve: {
      alias: {
        '@oj/mocks/fixtures': resolve(useDevelopmentFixtures ? 'src/pages/oj/mocks/fixtures.js' : 'src/pages/oj/mocks/empty-fixtures.js'),
        '@': resolve('src'),
        '@oj': resolve('src/pages/oj'),
        '@admin': resolve('src/pages/admin'),
        '~': resolve('src/components')
      },
      extensions: ['.mjs', '.js', '.jsx', '.json', '.vue']
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify(mode),
      'process.env.VERSION': JSON.stringify(commit),
      'process.env.USE_SENTRY': JSON.stringify(process.env.USE_SENTRY || '0')
    },
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true
        }
      }
    },
    server: {
      host: devHost,
      port: Number(process.env.PORT || 8080),
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          configure (proxy) {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('Referer', target)
            })
          }
        },
        '/public': {
          target,
          changeOrigin: true,
          configure (proxy) {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('Referer', target)
            })
          }
        }
      }
    },
    // Workers (the pdf.js renderer) land next to the other hashed chunks, which nginx serves as static files.
    worker: {
      rollupOptions: {
        output: {
          entryFileNames: 'static/js/[name]-[hash].js',
          chunkFileNames: 'static/js/[name]-[hash].js',
          assetFileNames: 'static/assets/[name]-[hash][extname]'
        }
      }
    },
    build: {
      outDir: resolve('dist'),
      emptyOutDir: true,
      sourcemap: process.env.USE_SENTRY === '1',
      rollupOptions: {
        input: {
          index: resolve('index.html'),
          admin: resolve('admin/index.html')
        },
        output: {
          manualChunks: dependencyChunk,
          entryFileNames: 'static/js/[name]-[hash].js',
          chunkFileNames: 'static/js/[name]-[hash].js',
          assetFileNames: 'static/assets/[name]-[hash][extname]'
        }
      }
    }
  }
})
