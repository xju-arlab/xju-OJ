// A tab opened before a deploy still asks for the previous build's route
// chunks, which no longer exist, and the navigation silently fails. Reload
// once onto the target page so the browser picks up the current build.
const RELOAD_KEY = 'xju-oj-chunk-reload-at'
const CHUNK_ERROR = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i

function lastReload () {
  try {
    return Number(window.sessionStorage.getItem(RELOAD_KEY)) || 0
  } catch (_) {
    return 0
  }
}

export function recoverFromStaleChunks (router) {
  router.onError((error, to) => {
    if (!CHUNK_ERROR.test(String((error && error.message) || error))) return
    // Never loop if the current build itself is broken.
    if (Date.now() - lastReload() < 10000) return
    try {
      window.sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
    } catch (_) {
      // Storage may be unavailable; reloading once is still safe.
    }
    window.location.assign(to ? router.resolve(to.fullPath).href : window.location.href)
  })
}
