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
const problem = {
  id: 5, _id: 'A', title: 'A+B', description: '<p>求和</p>', input_description: '<p>两个数</p>', output_description: '<p>和</p>',
  data_range: '', samples: [{ input: '1 2', output: '3' }], hint: '', languages: ['C++'], template: {}, time_limit: 1000,
  memory_limit: 256, io_mode: { io_mode: 'Standard IO', input: 'input.txt', output: 'output.txt' }, rule_type: 'ACM',
  difficulty: 'Low', tags: [], source: '', created_by: { username: 'root' }, submission_number: 3, accepted_number: 1,
  statistic_info: {}, my_status: null, total_score: 0, judge_mode: 'LOCAL', favorited: false
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
    if (path === '/api/contest' && url.searchParams.get('id') === '40') data = { ...contest, id: 40, title: '新生赛正式', status: '1', start_time: iso(24), end_time: iso(29), rank_freeze_time: iso(28) }
    else if (path === '/api/contest') {
      data = url.searchParams.get('id') === '31' ? { ...prep, published_contests: state.published ? [{ id: 40, title: '新生赛正式' }] : [] }
        : state.ended ? { ...contest, status: '-1', start_time: iso(-6), end_time: iso(-1), now: iso(0) }
          : state.upcoming ? { ...contest, status: '1', start_time: iso(2), end_time: iso(7), rank_freeze_time: iso(6) } : contest
    }
    if (path === '/api/contest/problem') {
      data = url.searchParams.get('problem_id') ? problem : [{ id: 5, _id: 'A', title: 'A+B', submission_number: 3, accepted_number: 1, my_status: null }]
    }
    if (path === '/api/languages') data = { languages: [{ name: 'C++', description: 'G++', content_type: 'text/x-c++src', config: { template: '' } }], spj_languages: [] }
    if (path === '/api/contest_rank') data = state.admin ? { ...rank, frozen: false } : rank
    if (path.startsWith('/api/contest/prep/problem')) data = [{ id: 9, _id: 'A', title: 'A+B', visible: true }]
    if (path === '/api/contest/prep/plan') data = { items: [], progress: [] }
    if (path === '/api/contest/prep/publish') data = { id: 40, title: body.title, teams: body.teams.map((item, index) => ({ ...item, id: index + 1, username: `team-aaa${index}`, password: 'Pass2345' })) }
    if (path === '/api/contest/announcement') data = []
    if (path === '/api/admin/contest' && req.method() === 'GET') data = { id: 40, title: '新生赛正式', description: '<p>说明</p>', visible: true, password: null, allowed_ip_ranges: [], rule_type: 'ACM' }
    if (path === '/api/admin/contest/teams' && req.method() === 'GET') data = [{ id: 1 }, { id: 2 }]
    if (path === '/api/admin/contest/teams/sheet') return route.fulfill({ body: '%PDF-1.7', contentType: 'application/pdf' })
    await route.fulfill({ json: { error, data } })
  })
})
test.afterEach(() => expect(state.errors).toEqual([]))

test('the team link signs in with a password and stays inside the contest without the navbar', async ({ page }) => {
  await page.goto('/arena/22')
  await expect(page.locator('#header')).toHaveCount(0)
  await page.getByPlaceholder('team-xxxx').fill('team-abcd')
  await page.locator('input[type=password]').fill('Pass2345')
  await expect(page).toHaveURL(/\/arena\/22\/login$/)
  await page.getByRole('button', { name: '登录并进入比赛' }).click()
  await expect(page).toHaveURL(/\/arena\/22\/$/)
  await expect(page.locator('#header')).toHaveCount(0)
  await expect(page.locator('.contest-breadcrumb .contest-team')).toContainText('Team Alpha')
  await expect(page.locator('.contest-breadcrumb .contest-team')).toHaveAttribute('title', '队员：A1、A2')
  // Moving inside the contest keeps the link's URLs; anywhere else leads back.
  await page.locator('.contest-tabs').getByText(/题目|Problems/).first().click()
  await expect(page).toHaveURL(/\/arena\/22\/problems$/)
  await page.goto('/problem')
  await expect(page).toHaveURL(/\/arena\/22\/$/)
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
  await expect(dialog.locator('.prep-publish-note')).toHaveText('实时排名，最后一小时封榜，赛后由管理员开榜')
  await expect(dialog.locator('.el-switch')).toHaveCount(1)
  // A new start time brings a five hour window.
  const [start, end] = await dialog.locator('.el-date-editor input').all()
  await start.fill('2026-11-08 09:00:00')
  await start.press('Enter')
  await expect(end).toHaveValue('2026-11-08 14:00:00')
  await dialog.locator('.el-switch').first().click()
  await expect(dialog.getByText('密码', { exact: true })).toHaveCount(0)
  await dialog.locator('input[type=file]').setInputFiles({
    name: 'teams.csv', mimeType: 'text/csv', buffer: Buffer.from('队伍名,队员1,队员2,队员3\nTeam Alpha,A1,A2,\nTeam Beta,B1,,,\n,赵一,孙二,\n')
  })
  await expect(dialog.locator('.team-roster-preview')).toContainText('共 3 支队伍')
  await expect(dialog.locator('.team-roster-preview')).toContainText('赵孙队')
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '发布比赛' }).click()
  expect((await download).suggestedFilename()).toBe('contest-40-teams.csv')
  const publish = state.writes.find(item => item.path === '/api/contest/prep/publish')
  expect(publish.body.teams).toEqual([{ name: 'Team Alpha', members: ['A1', 'A2'] }, { name: 'Team Beta', members: ['B1'] },
    { name: '赵孙队', members: ['赵一', '孙二'] }])
  expect(publish.body.password).toBe('')
  // Ranks are live and an ACM board freezes for the last hour.
  expect(publish.body.real_time_rank).toBe(true)
  expect(Date.parse(publish.body.end_time) - Date.parse(publish.body.start_time)).toBe(5 * 3600e3)
  expect(Date.parse(publish.body.end_time) - Date.parse(publish.body.rank_freeze_time)).toBe(3600e3)
  await expect(page.locator('.prep-published-link a')).toHaveText(/\/arena\/40$/)
  const sheet = page.waitForEvent('download')
  await page.locator('.el-dialog').filter({ hasText: '比赛链接' }).getByRole('button', { name: '导出 PDF' }).click()
  expect((await sheet).suggestedFilename()).toBe('contest-40-teams.pdf')
  const sheetRequest = state.writes.find(item => item.path === '/api/admin/contest/teams/sheet')
  expect(sheetRequest.body.teams[2]).toEqual({ name: '赵孙队', members: ['赵一', '孙二'], username: 'team-aaa2', password: 'Pass2345' })
})

test('after the contest the link is read only while the normal site keeps practice', async ({ page }) => {
  state.ended = true
  state.profile = { language: 'zh-CN', user: { id: 7, username: 'student', admin_type: 'Regular User' } }
  await page.goto('/arena/22')
  await expect(page).toHaveURL(/\/arena\/22$/)
  await expect(page.locator('.contest-hero')).toBeVisible()
  await expect(page.locator('#header')).toHaveCount(0)
  await page.goto('/contest/22/problem/A/')
  await expect(page).toHaveURL(/\/arena\/22\/problem\/A\/$/)
  await expect(page.getByText('比赛已结束，此链接只供查看')).toBeVisible()
  await expect(page.locator('.oj-submit-button')).toBeDisabled()
  // Leaving through the contest list ends the link view.
  await page.goto('/contest')
  await expect(page.locator('#header')).toBeVisible()
  await page.goto('/contest/22/problem/A/')
  await expect(page.locator('#header')).toBeVisible()
  await expect(page.locator('.oj-submit-button')).toBeEnabled()
})

test('before the start the link says so instead of loading forever', async ({ page }) => {
  state.upcoming = true
  await page.goto('/arena/22')
  await expect(page.locator('.contest-arena-notice')).toContainText('未到开赛时间')
  await expect(page.getByPlaceholder('team-xxxx')).toBeVisible()
  // A signed-in site account is told the contest is for team accounts.
  state.profile = { language: 'zh-CN', user: { id: 7, username: 'student', admin_type: 'Regular User' } }
  await page.reload()
  await expect(page.locator('.contest-arena-notice')).toContainText('未到开赛时间')
  await expect(page.getByText('本场比赛只对队伍账号开放，当前登录的是 student')).toBeVisible()
  await expect(page.getByText('Loading')).toHaveCount(0)
})

test('a published preparation contest shows its copy and edits it instead of publishing again', async ({ page }) => {
  state.published = true
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  await page.goto('/contest/31/')
  await page.getByRole('button', { name: '已发布' }).click()
  const dialog = page.locator('.el-dialog').filter({ hasText: '已发布的比赛' })
  await expect(dialog).toContainText('新生赛正式')
  await expect(dialog).toContainText('批量队伍账号（2 支）')
  await expect(dialog.locator('.prep-published-link a')).toHaveText(/\/arena\/40$/)
  await expect(page.locator('.el-dialog').filter({ hasText: '参赛账号' }).filter({ hasText: '发布比赛' })).toHaveCount(0)
  await dialog.getByRole('button', { name: '编辑' }).click()
  await dialog.locator('input[maxlength="128"]').fill('新生赛决赛')
  const [start, end] = await dialog.locator('.el-date-editor input').all()
  await start.fill('2026-11-08 09:00:00')
  await start.press('Enter')
  await expect(end).toHaveValue('2026-11-08 14:00:00')
  await dialog.getByRole('button', { name: '保存' }).click()
  await expect.poll(() => state.writes.find(item => item.path === '/api/admin/contest')).toBeTruthy()
  const saved = state.writes.find(item => item.path === '/api/admin/contest').body
  expect(saved).toMatchObject({ id: 40, title: '新生赛决赛', password: '', real_time_rank: true, visible: true, description: '<p>说明</p>' })
  expect(Date.parse(saved.end_time) - Date.parse(saved.rank_freeze_time)).toBe(3600e3)
  expect(state.writes.some(item => item.path === '/api/contest/prep/publish')).toBe(false)
})

test('contest admins open the link and stay on /arena/', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  await page.goto('/arena/22')
  await expect(page.locator('.contest-hero')).toBeVisible()
  await expect(page).toHaveURL(/\/arena\/22$/)
  await expect(page.locator('#header')).toHaveCount(0)
  await page.locator('.contest-tabs').getByText(/排名|Rankings/).first().click()
  await expect(page).toHaveURL(/\/arena\/22\/rank$/)
})
