// Storage can be denied by browser policy or contain an interrupted write.
// Keep legacy OJ keys readable; leave unrelated application preferences alone.
export default {
  name: 'storage',
  set (key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); return true } catch { return false }
  },
  get (key) {
    try { return JSON.parse(window.localStorage.getItem(key)) } catch { return null }
  },
  remove (key) {
    try { window.localStorage.removeItem(key) } catch {}
  },
  clear () {
    try {
      const storage = window.localStorage
      for (const key of Object.keys(storage)) {
        if (key === 'authed' || key === 'languages' || key === 'problemCode' || key.startsWith('problemCode_')) {
          storage.removeItem(key)
        }
      }
    } catch {}
  }
}
