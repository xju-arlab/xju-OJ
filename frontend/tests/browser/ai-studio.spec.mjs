import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

// Browser contract fixtures. Real execution is verified by ai/tests/live_acceptance.py.
const titles = ['线性回归从零实现', '稳定 Softmax', '补全 PyTorch 训练循环', '宿舍用电量预测', '外卖送达时间与超时风险预测']
const problems = titles.map((title, i) => ({ id: 'AI00' + (i + 1), title, type: i < 2 ? 'logic' : i === 2 ? 'model' : 'challenge',
  metric: i === 2 ? 'Accuracy' : 'MSE', points: 20, version: 1, cells: ['import torch', '# implement'],
  objective: '练习任务', requirements: ['按接口实现'], signature: 'train(X, y)', files: [],
  inputSpec: i < 3 ? 'X：张量 [N, 2]' : 'train.csv：600 行；test.csv：160 行',
  outputSpec: i < 3 ? '输出：张量 [N, 1]' : 'predictions.csv：160 行；id 与 test.csv 完全同序',
  previous: i ? 'AI00' + i : null, next: i < 4 ? 'AI00' + (i + 2) : null }))
const contest = { id: '23', title: 'AI 功能验证赛', rule_type: 'AI', contest_type: 'Public', status: '0',
  start_time: '2026-10-17T06:00:00Z', end_time: '2026-10-17T08:00:00Z', registered: true,
  scorePolicy: 'latest', description: '<p>接口展示</p>', problems, totalPoints: 100, created_by: { id: 1, username: 'teacher' } }
let state

test.beforeEach(async ({ page }) => {
  state = { errors: [], writes: [], drafts: {}, jobs: [], authenticated: true, conflict: false }
  state.jobs = [
    { id: 'new', problemId: 'AI005', title: titles[4], type: 'challenge', status: 'SCORING', createdAt: '2026-10-07T18:04:00Z' },
    { id: 'bad', problemId: 'AI002', title: titles[1], type: 'logic', status: 'WRONG_ANSWER', createdAt: '2026-10-07T18:03:00Z' },
    { id: 'zero', problemId: 'AI004', title: titles[3], type: 'challenge', status: 'SCORED', publicScore: 0, privateScore: null, privatePublished: false, createdAt: '2026-10-07T18:02:00Z' },
    { id: 'model', problemId: 'AI003', title: titles[2], type: 'model', status: 'ACCEPTED', accuracy: 1, createdAt: '2026-10-07T18:01:00Z' }
  ]
  page.on('pageerror', error => state.errors.push(error.message))
  await page.route('**/api/**', async route => {
    const req = route.request(); const url = new URL(req.url()); const path = url.pathname.replace(/\/$/, '')
    const body = req.method() === 'GET' ? {} : req.postDataJSON()
    let data = {}; let error = null
    if (req.method() !== 'GET') state.writes.push({ path, body })
    if (path === '/api/profile') data = state.authenticated ? { language: 'zh-CN', user: { id: 7, username: 'student', admin_type: 'Regular User' } } : { language: 'zh-CN' }
    if (path.includes('providers')) data = { authentik: { enabled: false }, local: { login_enabled: true, register_enabled: false } }
    if (path.includes('website')) data = { website_name: 'XJU-OJ', allow_register: false }
    if (path === '/api/ai/problems') {
      const id = url.searchParams.get('problem_id')
      if (id) data = problems.find(p => p.id === id)
      else {
        const kind = url.searchParams.get('type'); const search = url.searchParams.get('keyword') || ''
        const rows = problems.filter(p => (!kind || p.type === kind) && (p.title + p.id).includes(search))
        data = { total: rows.length, results: rows.map(p => ({ ...p, latest: state.jobs.find(j => j.problemId === p.id) })) }
      }
    }
    if (path === '/api/contests') {
      const rows = url.searchParams.get('rule_type') === 'AI' ? [contest] : [contest, ...Array.from({ length: 24 }, (_, i) => ({ ...contest, id: i + 101, title: 'ACM 回归比赛 ' + (i + 1), rule_type: 'ACM' }))]
      const offset = Number(url.searchParams.get('offset')); const limit = Number(url.searchParams.get('limit'))
      data = { total: rows.length, results: rows.slice(offset, offset + limit) }
    }
    if (path === '/api/ai/contest') data = contest
    if (path === '/api/contest/announcement') data = { results: [], total: 0 }
    if (path === '/api/ai/leaderboard') data = { results: [], selection: 'latest', privatePublished: false }
    if (path === '/api/ai/problem-leaderboard') {
      state.rankScope = Object.fromEntries(url.searchParams)
      data = { results: [{ rank: 1, userId: 8, username: 'classmate', score: 0, record: { type: 'challenge', status: 'SCORED', publicScore: 0, privatePublished: false } }], total: 1, selection: url.searchParams.get('contest_id') ? 'latest' : 'best', privatePublished: false }
      if (state.rankHidden) { error = 'error'; data = 'Leaderboard is hidden during this contest' }
    }
    if (path === '/api/ai/completed') data = state.jobs.filter(j => ['SCORED', 'ACCEPTED'].includes(j.status))
    if (path === '/api/ai/draft') {
      const scope = req.method() === 'GET' ? Object.fromEntries(url.searchParams) : body
      const key = JSON.stringify([scope.problem_id, scope.contest_id || ''])
      const saved = state.drafts[key] || { cells: problems.find(p => p.id === scope.problem_id).cells, revision: 0 }
      if (req.method() === 'PUT') {
        if (state.conflict || body.revision !== saved.revision) { error = 'draft-conflict'; data = 'Draft changed in another window.' }
        else data = state.drafts[key] = { cells: body.cells, revision: saved.revision + 1 }
      } else data = saved
    }
    if (path === '/api/ai/jobs') {
      if (req.method() === 'POST') {
        const p = problems.find(p => p.id === body.problem_id)
        data = { id: body.id, problemId: p.id, title: p.title, type: p.type, kind: body.kind,
          contestId: body.contest_id, official: !!body.contest_id, status: body.kind === 'notebook' ? 'SUCCEEDED' : 'PENDING',
          payload: { cells: body.cells }, output: { cells: [{ text: 'tensor(3.)', png: [], execution_count: 1 }] }, createdAt: new Date().toISOString() }
        if (body.kind === 'notebook' && state.notebookPending) { data.status = 'PENDING'; data.output = {} }
        state.jobs.unshift(data)
        if (body.kind === 'notebook' && state.holdNotebook) await state.holdNotebook
      } else if (url.searchParams.has('id')) data = state.jobs.find(j => j.id === url.searchParams.get('id'))
      else {
        const code = url.searchParams.get('problem_id')
        const jobs = state.jobs.filter(j => j.kind !== 'notebook' && (!code || j.problemId === code))
        data = { results: jobs, total: jobs.length }
      }
    }
    await route.fulfill({ json: { error, data } })
  })
})
test.afterEach(() => expect(state.errors).toEqual([]))

test('home shows per-problem states, valid zero scores and latest-first activity', async ({ page }) => {
  await page.goto('/ai-studio')
  await expect(page.locator('.studio-table tbody tr')).toHaveCount(5)
  await expect(page.locator('.ai-studio > .studio-heading, .ai-studio > .studio-tabs')).toHaveCount(0)
  expect(await page.locator('[data-submission-id]').evaluateAll(rows => rows.map(r => r.dataset.submissionId))).toEqual(['new', 'bad', 'zero', 'model'])
  await expect(page.locator('[data-submission-id="zero"] .evaluation-score-pill')).toHaveText('公榜0.0分')
  await expect(page.locator('[data-submission-id="model"]')).toContainText('Accuracy 100.0%模型达标')
  await page.getByRole('button', { name: '数据挑战', exact: true }).click()
  await expect(page.locator('.studio-table tbody tr')).toHaveCount(2)
  await page.getByRole('textbox', { name: '搜索 AI 题目' }).fill('宿舍')
  await expect(page.locator('.studio-table tbody tr')).toHaveCount(1)
  await expect(page.locator('.studio-table')).toContainText('私榜未公布')
})

test('ordinary contest tab fetches AI and preserves ACM pagination', async ({ page }) => {
  await page.goto('/contest')
  await expect(page.locator('#contest-list > li')).toHaveCount(10)
  await expect(page.locator('#contest-list')).toContainText(contest.title)
  await page.goto('/contest?page=2')
  await expect(page.locator('#contest-list > li').first()).toContainText('ACM 回归比赛 10')
  await page.goto('/contest?rule_type=AI')
  await expect(page.locator('#contest-list > li')).toHaveCount(1)
  await page.getByText(contest.title, { exact: true }).click()
  await expect(page).toHaveURL(/\/ai-studio\/contest\/23$/)
  await expect(page.getByRole('heading', { name: contest.title })).toBeVisible()
})

test('Notebook saves scoped drafts, runs through API and submits a snapshot', async ({ page }) => {
  await page.goto('/ai-studio/problem/AI001')
  const code = page.locator('.cm-content').nth(1)
  await expect(code).toContainText('implement')
  await expect.poll(() => page.evaluate(() => Math.abs(document.querySelector('.studio-notebook').getBoundingClientRect().top - document.querySelector('#header').getBoundingClientRect().bottom))).toBeLessThanOrEqual(1)
  await code.fill('# practice answer\nw = 42')
  await page.getByRole('link', { name: '下一题' }).click()
  await expect(code).not.toContainText('practice answer')
  await page.getByRole('link', { name: '上一题' }).click()
  await expect(code).toContainText('practice answer')
  await page.goto('/ai-studio/problem/AI001?contest=23')
  await expect(code).not.toContainText('practice answer')
  await code.fill('# contest answer\nw = 100')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已保存至云端')
  await page.getByRole('button', { name: '运行全部' }).click()
  await expect(page.locator('.studio-cell-output')).toContainText('tensor(3.)')
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出', exact: true }).click()
  const notebook = JSON.parse(await readFile(await (await pending).path(), 'utf8'))
  expect(notebook.nbformat).toBe(4)
  expect(notebook.cells.filter(c => c.cell_type === 'code')[1].source.join('')).toContain('contest answer')
  await page.getByRole('button', { name: '提交评测', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('答卷已保存')
  expect(state.writes.filter(r => r.path === '/api/ai/jobs').at(-1).body).toMatchObject({ kind: 'evaluation', contest_id: '23', cells: ['import torch', '# contest answer\nw = 100'] })
})

test('draft conflicts preserve the answer and keep export available', async ({ page }) => {
  await page.goto('/ai-studio/problem/AI001')
  await expect(page.locator('.cm-content').nth(1)).toBeVisible()
  state.conflict = true
  await page.locator('.cm-content').nth(1).fill('# do not lose this')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Draft changed')
  await expect(page.locator('.cm-content').nth(1)).toContainText('do not lose this')
  await expect(page.getByRole('button', { name: '导出', exact: true })).toBeEnabled()
})

test('Notebook immediately acknowledges runs and shows actual sequential progress and errors', async ({ page }) => {
  state.notebookPending = true
  let release
  state.holdNotebook = new Promise(resolve => { release = resolve })
  await page.goto('/ai-studio/problem/AI001')
  const runAll = page.getByRole('button', { name: '运行全部', exact: true })
  const cells = page.locator('.studio-cell')
  await runAll.click()
  await expect(runAll).toBeDisabled()
  await expect(runAll).toContainText('正在提交')
  await expect(runAll.locator('.studio-spin')).toBeVisible()
  await expect(page.getByRole('button', { name: '运行第 1 个单元格' })).toBeDisabled()
  release()
  await expect(page.locator('.studio-run-state')).toContainText('排队中')
  const job = state.jobs[0]
  const kernel = '1'.repeat(32)
  job.status = 'RUNNING'
  job.output = { kernel_id: kernel, cells: [{ status: 'RUNNING', execution_count: null }, { status: 'PENDING', execution_count: null }] }
  await expect(cells.nth(0).locator('.studio-cell-prompt')).toHaveText('[*]')
  await expect(cells.nth(1)).toHaveAttribute('data-cell-state', 'PENDING')
  job.output.cells = [{ status: 'SUCCEEDED', execution_count: 1, text: 'first result' }, { status: 'RUNNING', execution_count: null }]
  await expect(cells.nth(0).locator('.studio-cell-prompt')).toHaveText('[1]')
  await expect(cells.nth(1).locator('.studio-cell-prompt')).toHaveText('[*]')
  await expect(page.locator('.studio-run-state')).toContainText('正在运行第 2 格')
  job.status = 'RUNTIME_ERROR'
  job.output.cells[1] = { status: 'ERROR', execution_count: 2, text: 'ValueError: example' }
  await expect(runAll).toBeEnabled()
  await expect(cells.nth(1)).toHaveAttribute('data-cell-state', 'ERROR')
  await expect(cells.nth(0)).toContainText('first result')
  await page.reload()
  await expect(cells.nth(1)).toContainText('ValueError: example')
  state.holdNotebook = null
  await page.getByRole('button', { name: '运行第 2 个单元格' }).click()
  await expect.poll(() => state.writes.filter(r => r.path === '/api/ai/jobs').length).toBe(2)
  const requests = state.writes.filter(r => r.path === '/api/ai/jobs').map(r => r.body)
  expect(requests[0].cell_index).toBeNull()
  expect(requests[1]).toMatchObject({ cell_index: 1, kernel: requests[0].kernel, kernel_generation: kernel })
  await expect(cells.nth(0)).toContainText('first result')
  await expect(cells.nth(1)).toHaveAttribute('data-cell-state', 'PENDING')
})

test('Shift+Enter executes the focused cell and advances, adding a final blank cell', async ({ page }) => {
  await page.goto('/ai-studio/problem/AI001')
  const editors = page.locator('.cm-content')
  await editors.nth(0).fill('counter = 40')
  await editors.nth(0).press('Shift+Enter')
  await expect(editors.nth(1)).toBeFocused()
  await expect.poll(() => state.writes.filter(r => r.path === '/api/ai/jobs').length).toBe(1)
  expect(state.writes.filter(r => r.path === '/api/ai/jobs')[0].body).toMatchObject({ cell_index: 0, cells: ['counter = 40', '# implement'] })
  await expect(page.getByRole('button', { name: '运行全部', exact: true })).toBeEnabled()
  await editors.nth(1).fill('counter += 1\nprint(counter)')
  await editors.nth(1).press('Shift+Enter')
  await expect(editors).toHaveCount(3)
  await expect(editors.nth(2)).toBeFocused()
  await expect.poll(() => state.writes.filter(r => r.path === '/api/ai/jobs').length).toBe(2)
  expect(state.writes.filter(r => r.path === '/api/ai/jobs')[1].body).toMatchObject({ cell_index: 1, cells: ['counter = 40', 'counter += 1\nprint(counter)'] })
})

test('anonymous visitors cannot run or submit', async ({ page }) => {
  state.authenticated = false
  await page.goto('/ai-studio/problem/AI001')
  await expect(page.getByRole('heading', { name: titles[0], exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '运行全部' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '提交评测', exact: true })).toBeDisabled()
  expect(state.writes).toEqual([])
})

test('problem input/output follows the interface and ranking uses the current problem and contest', async ({ page }) => {
  await page.goto('/ai-studio/problem/AI004?contest=23')
  await expect(page.locator('.studio-prose h2')).toHaveText(['任务目标', '实现要求', '接口约定', '输入', '输出'])
  await expect(page.locator('.studio-io-description').first()).toContainText('600 行')
  await expect(page.locator('.studio-io-description').last()).toContainText('完全同序')
  await expect(page.getByRole('navigation', { name: '题目资料' }).locator('button')).toHaveText(['题目', '数据与框架', '评测', '排行'])
  await page.getByRole('button', { name: '排行', exact: true }).click()
  await expect(page.getByRole('region', { name: '本题排行' })).toContainText('本场比赛 · 最后一次提交 · 公榜')
  await expect(page.locator('.studio-problem-ranking')).toContainText('classmate')
  await expect(page.locator('.studio-problem-ranking .evaluation-score-pill')).toHaveText('公榜0.0分')
  expect(state.rankScope).toMatchObject({ problem_id: 'AI004', contest_id: '23' })
  await expect(page.locator('.cm-content')).toHaveCount(2)
  await page.goto('/ai-studio/problem/AI001')
  await expect(page.locator('.studio-io-description').first()).toContainText('张量 [N, 2]')
  await page.getByRole('button', { name: '排行', exact: true }).click()
  await expect(page.locator('.studio-problem-ranking')).toContainText('自主练习 · 最高分 · 公榜')
  expect(state.rankScope).toMatchObject({ problem_id: 'AI001', contest_id: '' })
})

test('a hidden contest problem leaderboard stays hidden', async ({ page }) => {
  state.rankHidden = true
  await page.goto('/ai-studio/problem/AI001?contest=23')
  await page.getByRole('button', { name: '排行', exact: true }).click()
  await expect(page.locator('.studio-problem-ranking [role="alert"]')).toContainText('Leaderboard is hidden')
  await expect(page.locator('.studio-problem-ranking table')).toHaveCount(0)
})

test('statement notation stays text and styled CSV upload preserves the submitted file', async ({ page }) => {
  const previous = problems[3].inputSpec
  const unsafe = '<img src=x onerror="window.statementInjected=true">'
  problems[3].inputSpec = 'train.csv：float32 张量 [N, 2]\n' + unsafe
  try {
    await page.goto('/ai-studio/problem/AI004')
    const input = page.locator('.studio-io-description').first()
    await expect(input.locator('p')).toHaveCount(2)
    await expect(input.locator('code')).toContainText(['train.csv', 'float32', '[N, 2]'])
    await expect(input).toContainText(unsafe)
    await expect(input.locator('img')).toHaveCount(0)
    expect(await page.evaluate(() => window.statementInjected)).toBeUndefined()
    const csv = 'id,next_power_kwh\n' + Array.from({ length: 160 }, (_, i) => `${i + 761},2.5\n`).join('')
    await page.getByLabel('上传预测结果 CSV').setInputFiles({ name: 'predictions.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
    await expect(page.locator('.studio-prediction-file')).toContainText('predictions.csv')
    await page.getByRole('button', { name: '提交评测', exact: true }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    expect(state.writes.filter(r => r.path === '/api/ai/jobs').at(-1).body.predictions).toBe(csv)
  } finally { problems[3].inputSpec = previous }
})

test('mobile page fits and retains AI navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/ai-studio')
  await expect(page.locator('.studio-table')).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
  const overflow = page.locator('#header .el-sub-menu__hide-arrow > .el-sub-menu__title')
  if (await overflow.isVisible()) await overflow.hover()
  await expect(page.getByRole('menuitem', { name: 'AI 工作台', exact: true })).toBeVisible()
})
