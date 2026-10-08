import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

const problem = { id: 'AI145', title: 'Imported contract fixture', type: 'logic', metric: 'Score', points: 100,
  visible: false, version: 3, revision: 8, packaged: true, public_files: {}, cells: ['print(7)'], requirements: [],
  objective: 'Synthetic fixture', signature: 'answer()', inputSpec: 'one number', outputSpec: 'one number', data: '', evaluation: '',
  judge: { phase_id: 45, task_id: 65, public_column: 'score', pass_score: 100, run_seconds: 120 } }
const preview = { id: '7ba34aec-69dc-4c1e-aea3-9b6eaed78ae8', filename: 'example.zip', status: 'PREVIEW', publish: false, message: '', result: [],
  createdAt: '2026-10-08T01:00:00Z', problems: [{ title: problem.title, type: 'logic', metric: 'Score', cells: 1, files: ['sample.csv'] }] }
let state

test.beforeEach(async ({ page }) => {
  state = { history: [], problems: [], writes: [], errors: [], rejectUpload: false, conflict: false }
  page.on('pageerror', error => state.errors.push(error.message))
  await page.route('**/api/**', async route => {
    const req = route.request(); const url = new URL(req.url()); const path = url.pathname; const method = req.method()
    let data = {}; let error = null
    const body = method !== 'GET' && !req.headers()['content-type']?.includes('multipart') ? req.postDataJSON() : null
    if (method !== 'GET') state.writes.push({ path, body, content: req.postData() })
    if (path === '/api/profile') data = { language: 'zh-CN', user: { id: 1, username: 'teacher', admin_type: 'Super Admin', problem_permission: 'All' } }
    if (path.includes('website')) data = { website_name: 'XJU-OJ' }
    if (path.includes('providers')) data = { authentik: { enabled: false }, local: { login_enabled: true } }
    if (path === '/api/admin/ai/packages') {
      if (method === 'POST') {
        if (state.rejectUpload) { error = 'error'; data = 'ZIP 包含不安全路径' } else { state.history = [structuredClone(preview)]; data = state.history[0] }
      } else if (method === 'DELETE') { state.history = [] }
      else data = url.searchParams.has('id') ? state.history[0] : state.history
    }
    if (path === '/api/admin/ai/packages/confirm') {
      state.history[0].status = 'PENDING'; state.history[0].publish = body.publish; state.history[0].message = ''; data = state.history[0]
    }
    if (path === '/api/admin/ai/problems') {
      if (method === 'POST') {
        if (state.conflict) { error = 'error'; data = '题目已被修改，请重新加载后保存' }
        else data = { id: problem.id, version: 3, revision: 9 }
      } else data = url.searchParams.has('id') ? structuredClone(problem) : { total: state.problems.length, results: state.problems }
    }
    if (path === '/api/admin/ai/packages/export') {
      await route.fulfill({ contentType: 'application/zip', headers: { 'Content-Disposition': 'attachment; filename="AI145.zip"' }, body: Buffer.from('synthetic-export') }); return
    }
    if (path === '/api/admin/problem') data = { total: 0, results: [] }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ error, data }) })
  })
})

test('AI import previews before confirmation, tracks completion and exports selected packages', async ({ page }) => {
  await page.goto('/admin/ai/problem/batch_ops')
  await expect(page.locator('.import-kind-tabs .active')).toHaveText('AI 题目')
  await page.locator('input[type="file"]').setInputFiles({ name: 'example.zip', mimeType: 'application/zip', buffer: Buffer.from('synthetic upload') })
  await page.getByRole('button', { name: '上传并校验' }).click()
  await expect(page.getByRole('region', { name: '题包预览' })).toContainText(problem.title)
  await expect(page.getByRole('checkbox', { name: '导入后公开' })).not.toBeChecked()
  expect(state.writes.some(row => row.path.endsWith('/confirm'))).toBe(false)
  await page.getByRole('button', { name: '确认导入', exact: true }).click()
  await expect(page.getByRole('region', { name: '题包预览' })).toContainText('等待导入')
  expect(state.writes.find(row => row.path.endsWith('/confirm')).body).toEqual({ id: preview.id, publish: false })
  state.history[0].status = 'SUCCEEDED'; state.history[0].result = [{ id: problem.id, title: problem.title, version: 1 }]
  state.problems = [problem]
  await expect(page.getByRole('region', { name: '题包预览' })).toContainText('导入成功', { timeout: 10000 })
  const row = page.getByRole('row').filter({ hasText: /AI145.*Imported/ })
  await row.locator('.el-checkbox__inner').click()
  await expect(row.getByRole('checkbox')).toBeChecked()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /导出所选/ }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe('AI145.zip')
  expect(await readFile(await file.path(), 'utf8')).toBe('synthetic-export')
  expect(state.errors).toEqual([])
})

test('malformed uploads display a validation error without a confirmation action', async ({ page }) => {
  state.rejectUpload = true
  await page.goto('/admin/ai/problem/batch_ops')
  await page.locator('input[type="file"]').setInputFiles({ name: 'bad.zip', mimeType: 'application/zip', buffer: Buffer.from('bad') })
  await page.getByRole('button', { name: '上传并校验' }).click()
  await expect(page.getByRole('alert')).toContainText('ZIP 包含不安全路径')
  await expect(page.getByRole('button', { name: '确认导入', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: '普通题目', exact: true }).click()
  await expect(page.locator('.import-kind-tabs .active')).toHaveText('普通题目')
  await expect(page.getByText('导入 FPS 题目（测试版）', { exact: true })).toBeVisible()
})

test('pending imports restore after navigation and failed records can be retried', async ({ page }) => {
  state.history = [{ ...structuredClone(preview), status: 'RUNNING' }]
  await page.goto('/admin/ai/problem/batch_ops')
  await expect(page.getByRole('region', { name: '题包预览' })).toContainText('正在导入')
  state.history[0].status = 'FAILED'; state.history[0].message = '可重试；本批尚未创建题目。'
  await expect(page.getByRole('button', { name: '重试导入' })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: '重试导入' }).click()
  await expect(page.getByRole('region', { name: '题包预览' })).toContainText('等待导入')
})

test('imported problem editor preserves judge configuration and uses an independent revision', async ({ page }) => {
  state.problems = [problem]
  await page.goto('/admin/ai/problems?id=AI145')
  await expect(page.getByText('题包评测配置', { exact: true })).toBeVisible()
  await expect(page.getByText('Codabench Phase ID', { exact: true })).toHaveCount(0)
  await page.getByLabel('输出（返回值/提交格式与约束）').fill('concise output')
  await page.getByRole('button', { name: '保存题目', exact: true }).click()
  await expect(page.getByText('题目已保存', { exact: true })).toBeVisible()
  expect(state.writes.at(-1).body).toMatchObject({ revision: 8, version: 3, outputSpec: 'concise output', judge: problem.judge })
  state.conflict = true
  await page.getByRole('button', { name: '保存题目', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '题目已被修改' })).toBeVisible()
  expect(state.writes.at(-1).body).toMatchObject({ revision: 9, version: 3 })
  await expect(page.getByLabel('输出（返回值/提交格式与约束）')).toHaveValue('concise output')
  expect(state.errors).toEqual([])
})
