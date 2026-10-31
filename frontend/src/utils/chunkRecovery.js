import runtime from './runtime'

// A tab opened before a deploy keeps running the previous build: it asks for
// route chunks that no longer exist, and even when they load it shows outdated
// pages. Reload onto the target page so the browser picks up the current build.
const RELOAD_KEY = 'xju-oj-chunk-reload-at'
const CHUNK_ERROR = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i
const RELEASE_CHECK_MS = 60000

function lastReload () {
  try {
    return Number(window.sessionStorage.getItem(RELOAD_KEY)) || 0
  } catch (_) {
    return 0
  }
}

function reloadOnto (router, to) {
  // Never loop if the current build itself is broken.
  if (Date.now() - lastReload() < 10000) return false
  try {
    window.sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
  } catch (_) {
    // Storage may be unavailable; reloading once is still safe.
  }
  window.location.assign(to ? router.resolve(to.fullPath).href : window.location.href)
  return true
}

// The deployed commit is published in the no-store runtime-config.js. When it
// differs from the one this tab started with, the next navigation does a full
// page load; drafts are backed up locally on every edit and restored after it.
function watchReleases (router) {
  const loaded = runtime.VERSION
  if (!loaded || loaded === 'unknown' || loaded === 'dev') return
  let checkedAt = 0
  let stale = false
  async function check () {
    if (stale || Date.now() - checkedAt < RELEASE_CHECK_MS) return
    checkedAt = Date.now()
    try {
      const response = await fetch('/runtime-config.js', { cache: 'no-store' })
      const version = ((await response.text()).match(/"VERSION":\s*"([^"]*)"/) || [])[1]
      stale = Boolean(version) && version !== 'unknown' && version !== loaded
    } catch (_) {
      // Offline or mid-deploy; try again on a later navigation.
    }
  }
  router.beforeEach(to => (stale && reloadOnto(router, to) ? false : undefined))
  router.afterEach(() => { check() })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check()
  })
}

export function recoverFromStaleChunks (router) {
  router.onError((error, to) => {
    if (CHUNK_ERROR.test(String((error && error.message) || error))) reloadOnto(router, to)
  })
  watchReleases(router)
}
