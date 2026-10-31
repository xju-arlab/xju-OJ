import { test, expect } from '@playwright/test'

// Browser contract for team-account contests and the frozen ACM board; the
// rules themselves are covered by backend tests.
const now = Date.now()
const iso = offset => new Date(now + offset * 3600e3).toISOString()
const team = { contest_id: 22, name: 'Team Alpha', members: ['A1', 'A2'] }
const contest = {
  id: 22, title: '新生赛', rule_type: 'ACM', contest_type: 'Public', status: '0', real_time_rank: true, description: '',
  start_time: iso(-4.5), end_time: iso(0.5), create_time: iso(-48), now: iso(0), created_by: { id: 1, username: 'root' },
  registered: true, participant_count: 2, team_contest: true, rank_freeze_time: iso(-0.5), rank_unfrozen: false
}
const prep = {
  ...contest, id: 31, title: '筹备赛', prep_state: 'Preparation', prep_role: 'Creator', published_contests: [],
  team_contest: false, rank_freeze_time: null, start_time: iso(-1), end_time: iso(24 * 9)
}
const rank = {
  frozen: true, total: 2, results: [
    { id: 1, user: { id: 50, username: 'team-abcd' }, team, accepted_number: 1, total_time: 3000, submission_number: 3,
      submission_info: { 5: { is_ac: true, ac_time: 1800, error_number: 1, is_first_ac: true } } },
    { id: 2, user: { id: 51, username: 'team-wxyz' }, team: { name: 'Team Beta', members: [] }, accepted_number: 0, total_time: 0,
      submission_number: 2, submission_info: { 5: { is_ac: false, ac_time: 0, error_number: 0, is_first_ac: false, frozen_number: 2 } } }
  ]
}
let state

test.beforeEach(async ({ page }) => {
  state = { errors: [], writes: [], profile: {}, admin: false }
  page.on('pageerror', error => state.errors.push(error.message))
  await page.route('**/api/**', async route => {
    const req = route.request(); const url = new URL(req.url()); const path = url.pathname.replace(/\/$/, '')
    const body = req.method() === 'GET' ? {} : req.postDataJSON()
    let data = {}; let error = null
    if (req.method() !== 'GET') state.writes.push({ path, body })
    if (path === '/api/profile') data = state.profile
    if (path.includes('providers')) data = { authentik: { enabled: true }, local: { login_enabled: false, register_enabled: false } }
    if (path.includes('website')) data = { website_name: 'XJU-OJ', allow_register: false }
    if (path === '/api/login') {
      if (body.username === 'team-abcd' && body.password === 'Pass2345') {
        state.profile = { language: 'zh-CN', oj_onboarding_completed: true, team, user: { id: 50, username: 'team-abcd', admin_type: 'Regular User' } }
      } else { error = 'error'; data = 'Invalid username or password' }
    }
    if (path === '/api/logout') state.profile = {}
    if (path === '/api/contest') data = url.searchParams.get('id') === '31' ? prep : contest
    if (path === '/api/contest/problem') data = [{ id: 5, _id: 'A', title: 'A+B', submission_number: 3, accepted_number: 1, my_status: null }]
    if (path === '/api/contest_rank') data = state.admin ? { ...rank, frozen: false } : rank
    if (path.startsWith('/api/contest/prep/problem')) data = [{ id: 9, _id: 'A', title: 'A+B', visible: true }]
    if (path === '/api/contest/prep/plan') data = { items: [], progress: [] }
    if (path === '/api/contest/prep/publish') data = { id: 40, title: body.title, teams: body.teams.map((item, index) => ({ ...item, id: index + 1, username: `team-aaa${index}`, password: 'Pass2345' })) }
    if (path === '/api/contest/announcement') data = []
    await route.fulfill({ json: { error, data } })
  })
})
test.afterEach(() => expect(state.errors).toEqual([]))

test('the team link signs in with a password and stays inside the contest without the navbar', async ({ page }) => {
  await page.goto('/arena/22')
  await expect(page.locator('#header')).toHaveCount(0)
  await page.getByPlaceholder('team-xxxx').fill('team-abcd')
  await page.locator('input[type=password]').fill('Pass2345')
  await page.getByRole('button', { name: '登录并进入比赛' }).click()
  await expect(page).toHaveURL(/\/contest\/22\/$/)
  await expect(page.locator('#header')).toHaveCount(0)
  await expect(page.locator('.contest-breadcrumb .contest-team')).toContainText('Team Alpha')
  await expect(page.locator('.contest-breadcrumb .contest-team')).toHaveAttribute('title', '队员：A1、A2')
  // Anywhere outside the contest leads back into it.
  await page.goto('/problem')
  await expect(page).toHaveURL(/\/contest\/22\/$/)
})

test('the board shows team names, members on hover and pending cells while frozen', async ({ page }) => {
  state.profile = { language: 'zh-CN', team, user: { id: 50, username: 'team-abcd', admin_type: 'Regular User' } }
  await page.goto('/contest/22/rank')
  await expect(page.locator('.rank-team').first()).toHaveText('Team Alpha')
  await expect(page.locator('.rank-team').first()).toHaveAttribute('title', '队员：A1、A2')
  await expect(page.locator('body')).not.toContainText('team-abcd')
  await expect(page.locator('.rank-problem-pending')).toHaveText('?+2')
  await expect(page.locator('.rank-freeze-banner')).toContainText('封榜')
})

test('publishing for team accounts takes a roster instead of a password and hands back the link', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  await page.goto('/contest/31/')
  await page.getByRole('button', { name: /发布|Publish/ }).first().click()
  const dialog = page.locator('.el-dialog').filter({ hasText: '参赛账号' })
  await expect(dialog.getByText('密码', { exact: true })).toBeVisible()
  await dialog.locator('.el-switch').first().click()
  await expect(dialog.getByText('密码', { exact: true })).toHaveCount(0)
  await dialog.locator('input[type=file]').setInputFiles({
    name: 'teams.csv', mimeType: 'text/csv', buffer: Buffer.from('队伍名,队员1,队员2,队员3\nTeam Alpha,A1,A2,\nTeam Beta,B1,,\n')
  })
  await expect(dialog.locator('.team-roster-preview')).toContainText('共 2 支队伍')
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '发布比赛' }).click()
  expect((await download).suggestedFilename()).toBe('contest-40-teams.csv')
  const publish = state.writes.find(item => item.path === '/api/contest/prep/publish')
  expect(publish.body.teams).toEqual([{ name: 'Team Alpha', members: ['A1', 'A2'] }, { name: 'Team Beta', members: ['B1'] }])
  expect(publish.body.password).toBe('')
  await expect(page.locator('.prep-published-link a')).toHaveText(/\/arena\/40$/)
})
