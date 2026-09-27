import assert from 'node:assert/strict'
import { activeContestAnnouncements, ANNOUNCEMENT_VISIBLE_MS } from '../src/pages/oj/contestAnnouncements.mjs'

const now = Date.parse('2026-09-27T12:00:00Z')
const posted = (id, ageMs, visible = true) => ({
  id,
  title: `Announcement ${id}`,
  visible,
  create_time: new Date(now - ageMs).toISOString()
})

const announcements = [
  posted(1, ANNOUNCEMENT_VISIBLE_MS),
  posted(2, ANNOUNCEMENT_VISIBLE_MS - 1),
  posted(3, 0),
  posted(4, -1000),
  posted(7, -999),
  posted(5, 3000, false),
  { id: 6, title: 'Invalid date', create_time: 'not-a-date' }
]

assert.deepEqual(activeContestAnnouncements(announcements, now).map(item => item.id), [7, 3, 2])
assert.deepEqual(activeContestAnnouncements(announcements, now + ANNOUNCEMENT_VISIBLE_MS).map(item => item.id), [4, 7])
assert.deepEqual(activeContestAnnouncements(null, now), [])

console.log('contest announcement timing passed')
