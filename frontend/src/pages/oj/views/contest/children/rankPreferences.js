const LOCAL_KEY = 'xju-oj:contest-rank-view:v1'
const SESSION_KEY = 'xju-oj:contest-rank-session:v1'

const defaults = Object.freeze({
  chart: false,
  realName: false,
  campus: false,
  autoRefresh: false,
  forceUpdate: false
})

const readObject = (storage, key) => {
  if (!storage) return {}
  try {
    const value = JSON.parse(storage.getItem(key))
    return value && typeof value === 'object' ? value : {}
  } catch (_) {
    return {}
  }
}

const writeObject = (storage, key, value) => {
  if (!storage) return
  try {
    storage.setItem(key, JSON.stringify(value))
  } catch (_) {
    // Rankings must remain usable when browser storage is unavailable.
  }
}

const browserStorage = name => {
  if (typeof window === 'undefined') return null
  try {
    return window[name]
  } catch (_) {
    return null
  }
}
const booleanValue = (value, fallback) => typeof value === 'boolean' ? value : fallback

export const readRankPreferences = () => {
  const local = readObject(browserStorage('localStorage'), LOCAL_KEY)
  const session = readObject(browserStorage('sessionStorage'), SESSION_KEY)
  return {
    chart: booleanValue(local.chart, defaults.chart),
    realName: booleanValue(local.realName, defaults.realName),
    campus: booleanValue(local.campus, defaults.campus),
    autoRefresh: booleanValue(session.autoRefresh, defaults.autoRefresh),
    forceUpdate: booleanValue(session.forceUpdate, defaults.forceUpdate)
  }
}

export const updateRankPreferences = patch => {
  const current = readRankPreferences()
  const next = { ...current, ...patch }
  writeObject(browserStorage('localStorage'), LOCAL_KEY, {
    chart: next.chart === true,
    realName: next.realName === true,
    campus: next.campus === true
  })
  writeObject(browserStorage('sessionStorage'), SESSION_KEY, {
    autoRefresh: next.autoRefresh === true,
    forceUpdate: next.forceUpdate === true
  })
  return next
}
