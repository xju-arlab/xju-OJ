import { test, expect } from '@playwright/test'

// Browser contract for quiz answer cards; grading itself is covered by backend tests.
const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
const problem = {
  id: 'AI010', title: '宿舍用电量场景分析', type: 'quiz', metric: 'Score', points: 100, version: 1, cells: [], files: [],
  objective: '阅读材料并作答', requirements: ['未作答的小题记 0 分'], signature: '', inputSpec: '', outputSpec: '',
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
      { id: 'steps', kind: 'order', prompt: '排列处理步骤', options: ['划分数据集', '标准化', '训练'], points: 40, materials: [] }
    ]
  },
  media: { 'curve.png': PNG }
}
let state

test.beforeEach(async ({ page }) => {
  state = { errors: [], writes: [], draft: { answers: {}, revision: 0 }, jobs: [], attemptsUsed: 0 }
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
          official, status: 'PARTIAL', publicScore: 60, payload: { answers: body.answers }, createdAt: new Date().toISOString() }
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
  await expect(page.locator('.studio-quiz-question')).toHaveCount(4)
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
  expect(state.draft.answers).toEqual({ task: 0, leak: [1, 2], rmse: 0.42, steps: [1, 0, 2] })
  await expect(page.locator('.studio-notebook-status')).toContainText('已作答 4 / 4')

  await page.reload()
  await expect(number).toHaveValue('0.42')
  await expect(page.locator('.studio-quiz-options label.selected')).toHaveCount(3)

  await page.getByRole('button', { name: '提交作答' }).click()
  await expect(page.getByRole('dialog')).toContainText('已作答 4 / 4 题')
  await page.getByRole('button', { name: '确认提交' }).click()
  await expect(page.getByRole('dialog')).toContainText('本次得分 60 / 100')
  const submitted = state.writes.filter(write => write.path === '/api/ai/jobs').at(-1).body
  expect(submitted).toMatchObject({ problem_id: 'AI010', kind: 'evaluation', answers: { task: 0, leak: [1, 2], rmse: 0.42, steps: [1, 0, 2] } })
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
