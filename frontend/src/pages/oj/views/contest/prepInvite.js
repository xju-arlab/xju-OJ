// A preparation invite token arrives in the URL fragment, which browsers never
// send to the server or in a Referer. While the visitor signs in it waits in
// sessionStorage (this tab only) and is dropped as soon as it is redeemed.
const PENDING_KEY = 'xju_pending_prep_invite'

export function inviteLink (token) {
  return `${window.location.origin}/invite#${token}`
}

export function readInviteToken () {
  const fromHash = window.location.hash.replace(/^#/, '')
  if (/^[A-Za-z0-9_-]{16,128}$/.test(fromHash)) return fromHash
  try {
    return window.sessionStorage.getItem(PENDING_KEY) || ''
  } catch (_) {
    return ''
  }
}

export function keepPendingInvite (token) {
  try {
    window.sessionStorage.setItem(PENDING_KEY, token)
  } catch (_) {
    // Without storage the visitor simply opens the link again after signing in.
  }
}

export function hasPendingInvite () {
  try {
    return Boolean(window.sessionStorage.getItem(PENDING_KEY))
  } catch (_) {
    return false
  }
}

export function forgetInvite () {
  try {
    window.sessionStorage.removeItem(PENDING_KEY)
  } catch (_) {
    // Nothing stored.
  }
  if (window.location.hash) {
    window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
  }
}
