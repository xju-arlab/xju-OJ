export const ANNOUNCEMENT_VISIBLE_MS = 10 * 60 * 1000

export function activeContestAnnouncements (announcements, nowMs) {
  if (!Array.isArray(announcements)) return []
  return announcements.filter(announcement => {
    if (announcement.visible === false) return false
    const publishedAt = Date.parse(announcement.create_time)
    const age = nowMs - publishedAt
    // The HTTP Date header has one-second precision; a just-published row can
    // appear slightly ahead of that clock even though it already exists.
    return Number.isFinite(age) && age > -1000 && age < ANNOUNCEMENT_VISIBLE_MS
  }).sort((a, b) => Date.parse(b.create_time) - Date.parse(a.create_time) || b.id - a.id)
}
