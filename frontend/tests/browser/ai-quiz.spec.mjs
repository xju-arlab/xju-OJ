import { test, expect } from '@playwright/test'

// Browser contract for quiz answer cards; grading itself is covered by backend tests.
const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
const problem = {
  id: 'AI010', title: '宿舍用电量场景分析', type: 'quiz', metric: 'Score', points: 100, version: 1, cells: [], files: [],
  objective: '预测下一小时用电量。\n- 阅读材料\n- 完成作答卡\n误差 $\\mathrm{RMSE}=\\sqrt{\\frac{1}{n}\\sum (\\hat y_i-y_i)^2}$', requirements: ['主观题由老师评阅'], signature: '', inputSpec: '', outputSpec: '',
  data: '', evaluation: '按小题计分', previous: null, next: null, maxAttempts: 2,
  quiz: {
    materials: [
      { id: 'fields', title: '字段说明', kind: 'table', columns: ['字段', '含义'], rows: [['temp', '室外温度'], ['ac_on', '下一时段空调开启数']] },
      { id: 'log', title: '训练日志', kind: 'text', text: 'epoch 1, train 0.91, valid 0.95' },
      { id: 'curve', title: '损失曲线', kind: 'image', file: 'curve.png', alt: '训练与验证损失' }
    ],
    questions: [
      { id: 'task', kind: 'single', prompt: '这是什么任务？', options: ['回归', '分类'], points: 10, materials: ['fields'] },
      { id: 'leak', kind: 'multiple', prompt: '哪些特征会泄露未来信息？', options: ['temp', 'ac_on', 'hour'], points: 20, materials: [] },
      { id: 'rmse', kind: 'number', prompt: '计算 RMSE', unit: 'kWh', points: 30, materials: ['log'] },
      { id: 'steps', kind: 'order', prompt: '排列处理步骤', options: ['划分数据集', '标准化', '训练'], points: 20, materials: [] },
      { id: 'plan', kind: 'text', prompt: '给出建模方案：\n- 特征\n- 模型', points: 20, materials: [] }
    ]
  },
  media: { 'curve.png': PNG }
}
let state

test.beforeEach(async ({ page }) => {
  state = { errors: [], writes: [], draft: { answers: {}, revision: 0 }, jobs: [], attemptsUsed: 0, ranking: 'acm' }
  page.on('pageerror', error => state.errors.push(error.message))
  await page.route('**/api/**', async route => {
    const req = route.request(); const url = new URL(req.url()); const path = url.pathname.replace(/\/$/, '')
    const body = req.method() === 'GET' ? {} : req.postDataJSON()
    let data = {}; let error = null
    if (req.method() !== 'GET') state.writes.push({ path, body })
    if (path === '/api/profile') data = { language: 'zh-CN', user: { id: 7, username: 'student', admin_type: 'Regular User' } }
    if (path.includes('providers')) data = { authentik: { enabled: false }, local: { login_enabled: true, register_enabled: false } }
    if (path.includes('website')) data = { website_name: 'XJU-OJ', allow_register: false }
    if (path === '/api/ai/problems') data = { ...problem, ...(url.searchParams.get('contest_id') ? { practice: false, attemptsUsed: state.attemptsUsed } : {}) }
    if (path === '/api/ai/contest') data = { id: '23', title: 'ACM 考核', rule_type: 'AI', contest_type: 'Public', status: '0', ranking: state.ranking, scorePolicy: 'best',
      start_time: '2026-10-31T06:00:00Z', end_time: '2026-10-31T08:00:00Z', registered: true, created_by: { username: 'teacher' }, description: '',
      problems: [{ id: 'AI010', title: '线性回归', type: 'logic', points: 10 }, { id: 'AI011', title: 'Softmax', type: 'logic', points: 10 }], totalPoints: 20, accessError: '' }
    if (path === '/api/contest/announcement') data = { results: [], total: 0 }
    if (path === '/api/ai/leaderboard' && state.ranking === 'oi') data = { ranking: 'oi', selection: 'best', privatePublished: false, results: [
      { rank: 1, userId: 1, username: 'ann', total: 16, penalty: 3000, scores: { AI010: { score: 10, time: 600, tries: 1, pending: 0 }, AI011: { score: 6, time: 1200, tries: 2, pending: 1 } } },
      { rank: 2, userId: 2, username: 'bob', total: 0, penalty: 0, scores: { AI010: { score: 0, time: null, tries: 3, pending: 0 }, AI011: { score: null, time: null, tries: 0, pending: 1 } } }] }
    else if (path === '/api/ai/leaderboard') data = { ranking: 'acm', selection: 'best', privatePublished: false, results: [
      { rank: 1, userId: 1, username: 'ann', solved: 2, penalty: 2700, scores: { AI010: { accepted: true, tries: 1, time: 600, pending: 0 }, AI011: { accepted: true, tries: 0, time: 900, pending: 0 } } },
      { rank: 2, userId: 2, username: 'bob', solved: 0, penalty: 0, scores: { AI010: { accepted: false, tries: 2, time: null, pending: 1 }, AI011: { accepted: false, tries: 3, time: null, pending: 0 } } }] }
    if (path === '/api/ai/draft') {
      if (req.method() === 'PUT') {
        if (body.revision !== state.draft.revision) { error = 'draft-conflict'; data = 'Draft changed in another window.' }
        else data = state.draft = { answers: body.answers, revision: state.draft.revision + 1 }
      } else data = state.draft
    }
    if (path === '/api/ai/jobs') {
      if (req.method() === 'POST') {
        const official = !!body.contest_id
        if (official) state.attemptsUsed += 1
        data = { id: body.id, problemId: problem.id, title: problem.title, type: 'quiz', kind: 'evaluation', contestId: body.contest_id || '',
          official, status: body.answers.plan ? 'REVIEWING' : 'PARTIAL', publicScore: body.answers.plan ? null : 60, payload: { answers: body.answers }, createdAt: new Date().toISOString() }
        state.jobs.unshift(data)
      } else data = { results: state.jobs, total: state.jobs.length }
    }
    await route.fulfill({ json: { error, data } })
  })
})
test.afterEach(() => expect(state.errors).toEqual([]))

test('quiz shows materials, saves structured answers and submits without a Notebook', async ({ page }) => {
  await page.goto('/ai-studio/problem/AI010')
  await expect(page.locator('.studio-material')).toHaveCount(3)
  await expect(page.locator('.studio-material table')).toContainText('下一时段空调开启数')
  await expect(page.locator('.studio-material img')).toHaveAttribute('alt', '训练与验证损失')
  await expect(page.locator('.studio-quiz-question')).toHaveCount(5)
  await expect(page.locator('.studio-prose .studio-statement-block li')).toHaveCount(2)
  await expect(page.locator('.studio-prose .katex').first()).toBeVisible()
  await expect(page.locator('.studio-prose h2').last()).toHaveText('作答说明')
  await expect(page.locator('.studio-quiz-prompt li')).toHaveCount(2)
  await expect(page.locator('.cm-editor')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '运行全部' })).toHaveCount(0)
  await expect(page.locator('.studio-quiz-refs').first()).toContainText('字段说明')

  await page.getByRole('radiogroup', { name: '第 1 题选项' }).getByText('回归').click()
  const leak = page.getByRole('group', { name: '第 2 题选项' })
  await leak.getByText('hour').click(); await leak.getByText('ac_on').click()
  const number = page.getByRole('textbox', { name: '第 3 题数值' })
  await number.fill('1.2.3')
  await expect(page.locator('.studio-quiz-number small')).toBeVisible()
  await number.fill('0.42')
  await expect(page.locator('.studio-quiz-number small')).toHaveCount(0)
  await page.getByRole('button', { name: '下移：划分数据集' }).click()
  await expect(page.locator('.studio-quiz-order li').first()).toContainText('标准化')
  await expect(page.getByRole('status')).toContainText('已保存至云端')
  expect(state.draft.answers).toEqual({ task: 0, leak: [1, 2], rmse: 0.42, steps: [1, 0, 2], plan: null })
  await expect(page.locator('.studio-notebook-status')).toContainText('已作答 4 / 5')
  await page.getByRole('textbox', { name: '第 5 题作答' }).fill('独热编码 building，平方损失')
  await expect(page.locator('.studio-quiz-text small')).toContainText('18 / 2000')
  await expect(page.getByRole('status')).toContainText('已保存至云端')
  expect(state.draft.answers.plan).toBe('独热编码 building，平方损失')

  await page.reload()
  await expect(number).toHaveValue('0.42')
  await expect(page.locator('.studio-quiz-options label.selected')).toHaveCount(3)

  await page.getByRole('button', { name: '提交作答' }).click()
  await expect(page.getByRole('dialog')).toContainText('已作答 5 / 5 题')
  await page.getByRole('button', { name: '确认提交' }).click()
  await expect(page.getByRole('dialog')).toContainText('主观题等待老师评阅')
  const submitted = state.writes.filter(write => write.path === '/api/ai/jobs').at(-1).body
  expect(submitted).toMatchObject({ problem_id: 'AI010', kind: 'evaluation', answers: { task: 0, leak: [1, 2], rmse: 0.42, steps: [1, 0, 2], plan: '独热编码 building，平方损失' } })
  expect(submitted.cells).toBeUndefined()
})

test('contest quiz shows and enforces the attempt limit in the card', async ({ page }) => {
  state.attemptsUsed = 1
  await page.goto('/ai-studio/problem/AI010?contest=23')
  await expect(page.locator('.studio-notebook-status')).toContainText('最多提交 2 次，已提交 1 次')
  await page.getByRole('button', { name: '确认当前顺序' }).click()
  await page.getByRole('button', { name: '提交作答' }).click()
  await expect(page.getByRole('dialog')).toContainText('未作答的小题记 0 分')
  await page.getByRole('button', { name: '确认提交' }).click()
  await page.getByRole('button', { name: '关闭' }).click()
  await expect(page.getByRole('button', { name: '提交次数已用完' })).toBeDisabled()
  expect(state.writes.filter(write => write.path === '/api/ai/jobs').at(-1).body).toMatchObject({ contest_id: '23', answers: { steps: [0, 1, 2], task: null } })
})

test('ACM contests rank by solved problems and penalty', async ({ page }) => {
  await page.goto('/ai-studio/contest/23')
  await expect(page.locator('.contest-meta')).toContainText('ACM')
  await page.getByRole('button', { name: '成绩' }).click()
  const rows = page.locator('.ai-acm-board tbody tr')
  await expect(rows).toHaveCount(2)
  await expect(rows.first()).toContainText('ann')
  await expect(rows.first().locator('td').nth(3)).toHaveText('45')
  await expect(rows.first().locator('td.acm-accepted').first()).toContainText('+1')
  await expect(rows.nth(1).locator('td.acm-pending')).toHaveText('?')
  await expect(rows.nth(1).locator('td.acm-failed')).toHaveText('−3')
})

test('OI contests sum best scores, color cells by score and open own submissions', async ({ page }) => {
  state.ranking = 'oi'
  await page.goto('/ai-studio/contest/23')
  await expect(page.locator('.contest-meta')).toContainText('OI · 总分 20')
  await expect(page.locator('.contest-countdown')).toContainText('距结束')
  await expect(page.locator('.contest-countdown strong')).toHaveText(/^\d{2}:\d{2}:\d{2}$/)
  await page.getByRole('button', { name: '成绩' }).click()
  const rows = page.locator('.ai-acm-board tbody tr')
  await expect(rows.first().locator('td').nth(2)).toHaveText('16')
  await expect(rows.first().locator('td').nth(3)).toHaveText('50')
  await expect(rows.first().locator('td.oi-full')).toHaveText('100:10')
  await expect(rows.first().locator('td.oi-pending').first()).toHaveText('6 ?0:20')
  await expect(rows.nth(1).locator('td.oi-zero')).toHaveText('0')
  await expect(rows.nth(1).locator('td.oi-pending')).toHaveText('?')
  await expect(page.locator('.ai-acm-board')).not.toContainText('−')
  await expect(rows.first().locator('button.ai-board-cell')).toHaveCount(0)
})
