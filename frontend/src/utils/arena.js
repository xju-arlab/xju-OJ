// The contest a visitor entered through its team link (/arena/:id). Its pages
// stay navbar-free for the browser session and read only once it is over;
// leaving the contest ends the arena view.
const ARENA_KEY = 'xju-oj-arena-contest'

export function arenaContest () {
  try { return sessionStorage.getItem(ARENA_KEY) || '' } catch (_) { return '' }
}

export function enterArena (id) {
  try { sessionStorage.setItem(ARENA_KEY, String(id)) } catch (_) {}
}

export function leaveArena () {
  try { sessionStorage.removeItem(ARENA_KEY) } catch (_) {}
}
