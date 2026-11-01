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
    { id: 1, user: { id: 50, username: 'team-abcd', real_name: '刘龙羽,陈胤良,杨昱泽' }, team, accepted_number: 1, total_time: 3000, submission_number: 3,
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
    if (req.method() !== 'GET') state.writes.push({ path, method: req.method(), body })
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
    if (path === '/api/contest' && data && data.id === 22 && state.awards) data = { ...data, rank_awards: state.awards }
    if (path === '/api/admin/contest/rank_awards') data = state.awards = { mode: body.mode, tiers: body.tiers }
    if (path === '/api/contest/problem') {
      data = url.searchParams.get('problem_id') ? problem : [{ id: 5, _id: 'A', title: 'A+B', submission_number: 3, accepted_number: 1, my_status: null }]
    }
    if (path === '/api/languages') data = { languages: [{ name: 'C++', description: 'G++', content_type: 'text/x-c++src', config: { template: '' } }], spj_languages: [] }
    if (path === '/api/contest_rank') { data = state.admin ? { ...rank, frozen: false } : rank; (state.rankLimits ||= []).push(url.searchParams.get('limit')) }
    if (path === '/api/contest_rank' && state.adminRow) {
      data = { ...rank, frozen: false, total: 3, results: [{ id: 3, user: { id: 1, username: 'root' }, team: null, accepted_number: 1, total_time: 600, submission_number: 1,
        submission_info: { 5: { is_ac: true, ac_time: 600, error_number: 0, is_first_ac: false } } }, ...rank.results] }
    }
    if (path === '/api/contest_rank' && state.campus) {
      data = { ...rank, frozen: false, results: rank.results.map((row, index) => ({ ...row, team: { ...row.team, campus: index ? 'youhao' : 'boda' } })) }
    }
    if (path === '/api/contest_rank' && state.moved) {
      data = { ...rank, frozen: false, results: rank.results.map((row, index) => ({ ...row, frozen_place: index ? 1 : 2 })) }
    }
    if (path === '/api/contest_rank' && state.star) {
      data = { ...rank, frozen: false, results: rank.results.map((row, index) => index ? { ...row, team: { ...row.team, star: true }, place: null } : { ...row, place: 1 }) }
    }
    if (path.startsWith('/api/contest/prep/problem')) data = [{ id: 9, _id: 'A', title: 'A+B', visible: true }]
    if (path === '/api/contest/prep/plan') data = { items: [], progress: [] }
    if (path === '/api/contest/prep/publish') data = { id: 40, title: body.title, teams: body.teams.map((item, index) => ({ ...item, id: index + 1, username: `team-aaa${index}`, password: 'Pass2345' })) }
    if (path === '/api/contest/announcement') data = []
    if (path === '/api/contest_submissions') {
      data = { total: 2, results: [
        { id: 's1', problem: 'A', result: 0, statistic_info: { time_cost: 10, memory_cost: 1024 }, language: 'C++', username: 'team-abcd', create_time: iso(-1), show_link: true },
        { id: 's2', problem: 'A', result: -1, statistic_info: { time_cost: 10, memory_cost: 1024 }, language: 'C++', username: 'root', create_time: iso(-1), show_link: false }
      ] }
    }
    if (path === '/api/admin/contest' && req.method() === 'GET') data = { id: 40, title: '新生赛正式', description: '<p>说明</p>', visible: true, password: null, allowed_ip_ranges: [], rule_type: 'ACM' }
    if (path === '/api/admin/contest/teams' && req.method() === 'GET') {
      data = [{ id: 1, name: 'Team Alpha', members: ['A1', 'A2'], star: false, campus: '' }, { id: 2, name: 'Team Beta', members: [], star: true, campus: '' }]
    }
    if (path === '/api/admin/contest/teams' && req.method() === 'PATCH') data = body.teams.map(item => ({ members: [], star: false, campus: '', ...item }))
    if (path === '/api/admin/contest/teams' && req.method() === 'POST') data = body.teams.map((item, index) => ({ ...item, id: index + 3, username: `team-new${index}`, password: 'Pass6789' }))
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
  await expect(page.locator('.contest-team-add')).toHaveCount(0)
  await expect(page.locator('.contest-breadcrumb .contest-team')).toContainText('A1、A2')
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
  await expect(page.locator('td.first-ac')).toHaveCSS('background-color', 'rgb(21, 127, 102)')
  await expect(page.locator('.rank-freeze-banner')).toContainText('封榜')
  // No team on this board has a campus, so there is nothing to tell apart.
  await expect(page.locator('label.rank-setting').filter({ hasText: '校区区分' })).toHaveCount(0)
  // Penalty in minutes; a team opens only its own cells.
  await expect(page.locator('.el-table th').nth(3)).toHaveText('罚时')
  await expect(page.locator('.rank-penalty').first()).toHaveText('50')
  await expect(page.locator('tbody tr').nth(1).locator('.rank-problem-link')).toHaveCount(0)
  await page.locator('tbody tr').first().locator('.rank-problem-link').click()
  await expect(page).toHaveURL(/\/(contest|arena)\/22\/submissions\?.*myself=1/)
  await expect(page).toHaveURL(/problemID=A/)
})

test('board hover stays on the row under the pointer and never repaints problem cells', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  state.adminRow = true
  await page.goto('/contest/22/rank')
  const rows = page.locator('.el-table__body tr.el-table__row')
  await expect(rows).toHaveCount(3)
  await rows.nth(2).hover()
  await expect(rows.nth(2)).toHaveClass(/hover-row/)
  // Element's JS hover-row lags behind fast pointer moves; on rows the pointer has left it changes nothing.
  await page.evaluate(() => document.querySelectorAll('.el-table__body tr.el-table__row').forEach((tr, index) => index < 2 && tr.classList.add('hover-row')))
  // Past Element's 0.25 s fade, should one come back.
  await page.waitForTimeout(300)
  await expect(rows.nth(0).locator('td.ac')).toHaveCSS('background-color', 'rgba(15, 123, 108, 0.12)')
  await expect(rows.nth(1).locator('td.first-ac')).toHaveCSS('background-color', 'rgb(21, 127, 102)')
  await expect(rows.nth(1).locator('td.rank-hover-cell').first()).toHaveCSS('background-color', 'rgb(255, 255, 255)')
  await expect(rows.nth(2).locator('td.rank-hover-cell').first()).toHaveCSS('background-color', 'rgb(247, 246, 243)')
  await expect(rows.nth(2).locator('td.frozen')).toHaveCSS('background-color', 'rgb(227, 238, 250)')
  await expect(rows.nth(2).locator('td').first()).toHaveCSS('transition-duration', '0s')
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
    name: 'teams.csv', mimeType: 'text/csv', buffer: Buffer.from('队伍名,队员1,队员2,队员3,队伍类型\nTeam Alpha,A1,A2,\nTeam Beta,B1,,,打星队伍\n,赵一,孙二,\n')
  })
  await expect(dialog.locator('.team-roster-preview')).toContainText('共 3 支队伍，其中打星 1 支')
  await expect(dialog.locator('.team-roster-preview')).toContainText('赵孙队')
  // Advancing places or medals must be set; a percentage of the two official teams floors.
  await expect(dialog.getByRole('button', { name: '发布比赛' })).toBeDisabled()
  await expect(dialog.locator('.rank-awards')).toContainText('正式参赛 2 支（不含打星）')
  const percent = dialog.getByRole('spinbutton', { name: '晋级百分比' })
  await percent.fill('70')
  await percent.press('Enter')
  await expect(dialog.getByRole('spinbutton', { name: '晋级个数' })).toHaveValue('1')
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '发布比赛' }).click()
  expect((await download).suggestedFilename()).toBe('contest-40-teams.csv')
  const publish = state.writes.find(item => item.path === '/api/contest/prep/publish')
  expect(publish.body.teams).toEqual([{ name: 'Team Alpha', members: ['A1', 'A2'], star: false, campus: '' },
    { name: 'Team Beta', members: ['B1'], star: true, campus: '' }, { name: '赵孙队', members: ['赵一', '孙二'], star: false, campus: '' }])
  expect(publish.body.password).toBe('')
  expect(publish.body.rank_awards).toEqual({ mode: 'advance', tiers: { advance: { kind: 'percent', value: 70 } } })
  // Ranks are live and an ACM board freezes for the last hour.
  expect(publish.body.real_time_rank).toBe(true)
  expect(Date.parse(publish.body.end_time) - Date.parse(publish.body.start_time)).toBe(5 * 3600e3)
  expect(Date.parse(publish.body.end_time) - Date.parse(publish.body.rank_freeze_time)).toBe(3600e3)
  await expect(page.locator('.prep-published-link a')).toHaveText(/\/arena\/40$/)
  const sheet = page.waitForEvent('download')
  await page.locator('.el-dialog').filter({ hasText: '比赛链接' }).getByRole('button', { name: '导出 PDF' }).click()
  expect((await sheet).suggestedFilename()).toBe('contest-40-teams.pdf')
  const sheetRequest = state.writes.find(item => item.path === '/api/admin/contest/teams/sheet')
  expect(sheetRequest.body.teams[2]).toEqual({ name: '赵孙队', members: ['赵一', '孙二'], username: 'team-aaa2', password: 'Pass2345', star: false })
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

test('an admin on a team board takes no place and looks like a star team', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  state.adminRow = true
  await page.goto('/contest/22/rank')
  const adminRow = page.locator('tbody tr').first()
  await expect(adminRow).toHaveClass(/rank-star-row/)
  await expect(adminRow.locator('td').nth(1)).toHaveText('★root')
  await expect(adminRow.locator('td').first()).toHaveText('*')
  await expect(page.locator('tbody tr').nth(1).locator('td').first()).toHaveText('1')
  await expect(page.locator('tbody tr').nth(2).locator('td').first()).toHaveText('2')
})

test('a team that signs in before the start waits on the poster carousel until it begins', async ({ page }) => {
  state.upcoming = true
  await page.goto('/arena/22')
  await page.getByPlaceholder('team-xxxx').fill('team-abcd')
  await page.locator('input[type=password]').fill('Pass2345')
  await page.getByRole('button', { name: '登录并进入比赛' }).click()
  await expect(page).toHaveURL(/\/arena\/22\/waiting$/)
  const active = page.locator('.poster.is-active')
  await expect(page.locator('.poster')).toHaveCount(6)
  await expect(active.locator('.poster-team')).toContainText('Team Alpha')
  await expect(active.locator('.poster-kind')).toHaveText('正式队')
  await expect(active.locator('.poster-members')).toHaveText(/A1\s+·\s+A2/)
  await expect(active.locator('.poster-clock')).toHaveText(/^0[12]:\d{2}:\d{2}$/)
  await page.locator('.arena-waiting-dot').nth(2).click()
  await expect(page.locator('.poster').nth(2)).toHaveClass(/is-active/)
  // The contest pages send the team back to wait; once it starts they let it in.
  await page.goto('/arena/22/')
  await expect(page).toHaveURL(/\/arena\/22\/waiting$/)
  state.upcoming = false
  await page.goto('/arena/22/waiting')
  await expect(page).toHaveURL(/\/arena\/22\/$/)
})

test('contest admins preview the waiting carousel with placeholder team text', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  await page.goto('/arena/22/waiting')
  await expect(page.locator('.poster.is-active .poster-team')).toContainText('队伍名称')
  await expect(page.locator('.poster.is-active .poster-status')).toHaveText('比赛已开始')
  await page.getByRole('button', { name: '进入比赛页' }).click()
  await expect(page).toHaveURL(/\/arena\/22\/$/)
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
  state.profile.real_name = '管理员甲'
  await page.goto('/arena/22')
  await expect(page.locator('.contest-hero')).toBeVisible()
  await expect(page).toHaveURL(/\/arena\/22$/)
  await expect(page.locator('#header')).toHaveCount(0)
  await expect(page.locator('.contest-breadcrumb .contest-team')).toContainText('root')
  await expect(page.locator('.contest-breadcrumb .contest-team')).toContainText('管理员甲')
  await page.locator('.contest-tabs').getByText(/排名|Rankings/).first().click()
  await expect(page).toHaveURL(/\/arena\/22\/rank$/)
})

test('contest admins set medals as a count or a floored percentage and the places show them', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  await page.goto('/contest/22/rank')
  await expect(page.locator('.rank-award-legend')).toHaveCount(0)
  await page.getByRole('button', { name: '晋级 / 奖牌' }).click()
  const dialog = page.locator('.el-dialog').filter({ hasText: '晋级 / 奖牌' })
  await dialog.getByText('奖牌', { exact: true }).click()
  await expect(dialog).toContainText('正式参赛 2 支')
  const gold = dialog.getByRole('spinbutton', { name: '金牌个数' })
  await gold.fill('1')
  await gold.press('Enter')
  await expect(dialog.getByRole('spinbutton', { name: '金牌百分比' })).toHaveValue('50.00')
  const silver = dialog.getByRole('spinbutton', { name: '银牌百分比' })
  await silver.fill('70')
  await silver.press('Enter')
  await expect(dialog.getByRole('spinbutton', { name: '银牌个数' })).toHaveValue('1')
  await dialog.getByRole('button', { name: '保存' }).click()
  const saved = state.writes.find(item => item.path === '/api/admin/contest/rank_awards')
  expect(saved.body).toEqual({ contest_id: '22', mode: 'medal', tiers: { gold: { kind: 'count', value: 1 }, silver: { kind: 'percent', value: 70 } } })
  await expect(page.locator('.rank-award-legend')).toHaveText('金牌 1银牌 1')
  const places = page.locator('.el-table__body tr.el-table__row .rank-place')
  await expect(places.nth(0)).toHaveClass(/is-gold/)
  await expect(places.nth(1)).toHaveClass(/is-silver/)
  await expect(places.nth(0)).toHaveCSS('border-top-color', 'rgb(232, 197, 90)')
})

test('the live board shows how far each team moved since the freeze', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  state.moved = true
  await page.goto('/contest/22/rank')
  const rows = page.locator('.el-table__body tr.el-table__row')
  await expect(rows.nth(0).locator('.rank-move')).toHaveText('↑1')
  await expect(rows.nth(0).locator('.rank-move')).toHaveCSS('color', 'rgb(24, 134, 75)')
  await expect(rows.nth(1).locator('.rank-move')).toHaveText('↓1')
  await expect(rows.nth(1).locator('.rank-move')).toHaveCSS('color', 'rgb(196, 65, 59)')
  await expect(rows.nth(0).locator('.rank-move')).toHaveAttribute('title', '封榜时第 2 名')
  // The arrow sits beside the badge: every place stays centred in its column and the arrow stays inside it.
  const layout = await page.evaluate(() => [...document.querySelectorAll('.el-table__body tr.el-table__row')].map(tr => {
    const cell = tr.querySelector('td').getBoundingClientRect()
    const badge = tr.querySelector('.rank-place').getBoundingClientRect()
    const arrow = tr.querySelector('.rank-move').getBoundingClientRect()
    return [Math.abs((cell.left + cell.width / 2) - (badge.left + badge.width / 2)), cell.right - arrow.right]
  }))
  for (const [offset, room] of layout) {
    expect(offset).toBeLessThan(1)
    expect(room).toBeGreaterThan(0)
  }
})

test('opening the frozen board asks for confirmation first', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  state.ended = true
  await page.goto('/contest/22/rank')
  const opened = () => state.writes.filter(item => item.path === '/api/admin/contest/rank_freeze')
  await page.getByRole('button', { name: '开榜', exact: true }).click()
  const confirm = page.locator('.el-message-box')
  await expect(confirm).toContainText('确认开榜')
  await expect(confirm).toContainText('包括未登录的访客')
  await confirm.getByRole('button', { name: '取消' }).click()
  await expect(confirm).toBeHidden()
  expect(opened()).toHaveLength(0)
  await page.getByRole('button', { name: '开榜', exact: true }).click()
  await confirm.getByRole('button', { name: '确认开榜' }).click()
  await expect.poll(() => opened().length).toBe(1)
  expect(opened()[0].body).toMatchObject({ unfrozen: true })
})

test('the board tells campuses apart up to the penalty column when asked', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  state.campus = true
  await page.goto('/contest/22/rank')
  const toggle = page.locator('label.rank-setting').filter({ hasText: '校区区分' })
  await expect(toggle).toHaveCount(1)
  await expect(page.locator('.rank-campus-legend')).toHaveCount(0)
  await toggle.locator('.el-switch').first().click()
  // The legend sits right after the switch.
  const legend = page.locator('.rank-campus-legend')
  await expect(legend).toHaveText('博达校区友好校区')
  const switchBox = await toggle.locator('.el-switch').first().boundingBox()
  const legendBox = await legend.boundingBox()
  expect(legendBox.x - (switchBox.x + switchBox.width)).toBeLessThan(16)
  const rows = page.locator('.el-table__body tr.el-table__row')
  await expect(rows.nth(0)).toHaveClass(/rank-campus-boda/)
  await expect(rows.nth(0).locator('td').first()).toHaveCSS('background-color', 'rgb(241, 236, 251)')
  await expect(rows.nth(0).locator('td').nth(3)).toHaveCSS('background-color', 'rgb(241, 236, 251)')
  await expect(rows.nth(0).locator('td.first-ac')).toHaveCSS('background-color', 'rgb(21, 127, 102)')
  await expect(rows.nth(1).locator('td').nth(1)).toHaveCSS('background-color', 'rgb(253, 240, 226)')
  await expect(rows.nth(1).locator('td.frozen')).toHaveCSS('background-color', 'rgb(227, 238, 250)')
  // The choice is remembered.
  await page.reload()
  await expect(page.locator('.rank-campus-legend')).toHaveCount(1)
  await toggle.locator('.el-switch').first().click()
  await expect(rows.nth(0)).not.toHaveClass(/rank-campus/)
  await expect(page.locator('.rank-campus-legend')).toHaveCount(0)
})

test('star teams take no place on the board and contest admins add teams from the header', async ({ page }) => {
  state.profile = { language: 'zh-CN', user: { id: 1, username: 'root', admin_type: 'Super Admin' } }
  state.star = true
  await page.goto('/contest/22/rank')
  const starRow = page.locator('tr.rank-star-row')
  await expect(starRow).toHaveCount(1)
  await expect(starRow.locator('.rank-team')).toHaveText('★Team Beta')
  await expect(starRow.locator('.rank-star-mark')).toHaveCount(1)
  await expect(starRow.locator('td').first()).toHaveText('*')
  await expect(page.locator('tbody tr').first().locator('td').first()).toHaveText('1')
  // Contest admins open any team's submissions from its cells.
  await expect(page.locator('.rank-problem-link')).toHaveCount(2)
  // The real name column takes the star row's tint like the other info columns,
  // keeps three names on one line, and every header sits over its column.
  await page.locator('.rank-setting').filter({ hasText: /真名|Real/ }).locator('.el-switch').click()
  await expect(starRow.locator('td').nth(2)).toHaveCSS('background-color', 'rgb(252, 249, 242)')
  await expect(page.locator('.rank-real-name').first()).toHaveText('刘龙羽,陈胤良,杨昱泽')
  expect((await page.locator('.rank-real-name').first().boundingBox()).height).toBeLessThan(26)
  const offsets = await page.evaluate(() => {
    const heads = [...document.querySelectorAll('.el-table__header-wrapper th')]
    const cells = [...document.querySelectorAll('.el-table__body-wrapper tbody tr:first-child td')]
    return heads.map((th, i) => {
      const a = th.getBoundingClientRect(); const b = cells[i].getBoundingClientRect()
      return Math.abs((a.left + a.width / 2) - (b.left + b.width / 2))
    })
  })
  expect(Math.max(...offsets)).toBeLessThan(1)
  await page.locator('.rank-setting').filter({ hasText: /真名|Real/ }).locator('.el-switch').click()
  // A team contest ranks teams, thirty to a page, numbering the whole board itself.
  await expect(page.locator('.el-table th').nth(1)).toHaveText('队伍')
  await expect(page.locator('.el-pagination')).toContainText('30')
  expect(state.rankLimits).toContain('250')

  // One team by hand: names already in the contest are refused.
  await page.locator('.contest-team-add').click()
  const dialog = page.locator('.el-dialog').filter({ hasText: '添加队伍' })
  await dialog.getByPlaceholder('留空则按队员姓氏取名').fill('Team Alpha')
  await expect(dialog).toContainText('本场比赛已有同名队伍')
  await expect(dialog.getByRole('button', { name: /生成/ })).toBeDisabled()
  await dialog.getByPlaceholder('留空则按队员姓氏取名').fill('Team Gamma')
  await dialog.getByPlaceholder('队员 1').fill('G1')
  await dialog.getByText('打星队伍').click()
  await dialog.getByText('友好校区').click()
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '生成 1 个账号' }).click()
  expect((await download).suggestedFilename()).toBe('contest-22-teams-added.csv')
  const created = state.writes.find(item => item.path === '/api/admin/contest/teams')
  expect(created.body).toEqual({ contest_id: '22', teams: [{ name: 'Team Gamma', members: ['G1'], star: true, campus: 'youhao' }] })
  await expect(dialog).toContainText('Pass6789')
  await dialog.getByRole('button', { name: '完成' }).click()

  // A roster file is checked for its type and campus columns.
  await page.locator('.contest-team-add').click()
  await dialog.getByText('批量导入').click()
  await dialog.locator('input[type=file]').setInputFiles({
    name: 'more.csv', mimeType: 'text/csv', buffer: Buffer.from('Team Delta,D1,,,正式队伍\nTeam Echo,E1,,,外卡\nTeam Fox,F1,,,,主校区\nTeam Delta,D2\n')
  })
  await expect(dialog.locator('.team-roster-errors')).toContainText('第 2 行队伍类型「外卡」应为正式队伍或打星队伍')
  await expect(dialog.locator('.team-roster-errors')).toContainText('第 3 行校区「主校区」应为博达校区或友好校区')
  await expect(dialog.locator('.team-roster-errors')).toContainText('第 4 行队伍「Team Delta」重复')
  await expect(dialog.getByRole('button', { name: /生成/ })).toBeDisabled()
  // Teams already in the contest, by name or, unnamed, by all their members, get
  // only what they lack: no second account, and contradictions are left alone.
  await dialog.locator('input[type=file]').setInputFiles({
    name: 'more.csv', mimeType: 'text/csv', buffer: Buffer.from('Team Beta,B1,,,,博达\n,A1,A2,A3,打星队伍,友好\nTeam Delta,D1,,,正式队伍,友好校区\n')
  })
  const preview = dialog.locator('.team-roster-preview')
  await expect(preview).toContainText('新建 1 支，补充 2 支已有队伍')
  await expect(preview.locator('tbody tr').nth(0)).toContainText('补充队员、校区')
  await expect(preview.locator('tbody tr').nth(1)).toContainText('Team Alpha')
  await expect(preview.locator('tbody tr').nth(1)).toContainText('补充队员、校区；队伍类型不一致，未改')
  await expect(preview.locator('tbody tr').nth(2)).toContainText('新建')
  const added = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '生成 1 个账号，补充 2 支队伍' }).click()
  await added
  const teamWrites = state.writes.filter(item => item.path === '/api/admin/contest/teams').slice(1)
  expect(teamWrites.map(item => [item.method, item.body])).toEqual([
    ['PATCH', { contest_id: '22', teams: [{ id: 2, members: ['B1'], campus: 'boda' }, { id: 1, members: ['A1', 'A2', 'A3'], campus: 'youhao' }] }],
    ['POST', { contest_id: '22', teams: [{ name: 'Team Delta', members: ['D1'], star: false, campus: 'youhao' }] }]
  ])
  await dialog.getByRole('button', { name: '完成' }).click()
  await page.locator('tr.rank-star-row .rank-problem-link').click()
  await expect(page).toHaveURL(/\/contest\/22\/submissions\?.*username=team-wxyz/)
  // Submissions name the team; other accounts keep their username.
  await expect(page.locator('.submission-team')).toHaveText('Team Alpha')
  await expect(page.locator('.el-table th').filter({ hasText: /^队伍$/ })).toHaveCount(1)
  await expect(page.locator('.el-table__body').filter({ hasText: 'Team Alpha' })).toContainText('root')
  // The author box searches by team: the cell's account shows as its team, and a
  // team name picked from the suggestions asks for that team's account.
  const search = page.getByPlaceholder('搜索队伍')
  await expect(search).toHaveValue('Team Beta')
  await search.fill('alp')
  const request = page.waitForRequest(req => req.url().includes('/api/contest_submissions') && req.url().includes('username=team-abcd'))
  await page.locator('.el-autocomplete-suggestion li').filter({ hasText: 'Team Alpha' }).click()
  await request
})
