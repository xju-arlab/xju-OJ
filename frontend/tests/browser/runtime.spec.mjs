import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/tests/browser/fixture.html')
  await page.waitForFunction(() => Boolean(window.fixture))
})

test('CodeMirror preserves typed source through undo and redo', async ({ page }) => {
  const code = page.locator('.cm-content')
  await code.click()
  await page.keyboard.press('Control+End')
  await page.keyboard.insertText('\n// draft preserved')
  await expect(code).toContainText('// draft preserved')
  await page.keyboard.press('Control+z')
  await expect(code).not.toContainText('// draft preserved')
  await page.keyboard.press('Control+Shift+z')
  await expect(code).toContainText('// draft preserved')
})

test('editor mount does not rewrite stored HTML and formula survives editing', async ({ page }) => {
  expect(await page.evaluate(() => window.fixture.state.richChanges)).toBe(0)
  const raw = page.locator('.markdown-raw-editor')
  await expect(raw).toHaveValue('Formula $a+b$')
  await raw.fill('Formula $a+b$\n\n**bold**')
  await page.getByRole('button', { name: '预览', exact: true }).click()
  await expect(page.locator('.markdown-preview strong')).toHaveText('bold')
  await expect(page.locator('.markdown-preview .katex')).toHaveCount(1)
  await page.getByRole('button', { name: '原文', exact: true }).click()
  await expect(raw).toHaveValue('Formula $a+b$\n\n**bold**')
})

test('raw HTML preview and emitted content remove executable payloads', async ({ page }) => {
  await page.locator('.markdown-raw-editor').fill('<img src="/missing" onerror="window.editorExploit=1"><a href="javascript:alert(1)">unsafe</a><script>window.editorExploit=2</script>')
  await page.getByRole('button', { name: '预览', exact: true }).click()
  await expect(page.locator('.markdown-preview [onerror], .markdown-preview script, .markdown-preview a[href^="javascript:"]')).toHaveCount(0)
  expect(await page.evaluate(() => window.editorExploit)).toBeUndefined()
  expect(await page.evaluate(() => window.fixture.state.rich)).not.toMatch(/onerror|javascript:|<script/i)
})

test('logout storage cleanup preserves unrelated application preferences', async ({ page }) => {
  const result = await page.evaluate(() => {
    localStorage.setItem('unrelated', 'keep')
    window.fixture.storage.set('problemCode_A', 'private source')
    window.fixture.storage.set('authed', true)
    localStorage.setItem('broken', '{')
    const broken = window.fixture.storage.get('broken')
    window.fixture.storage.clear()
    return { unrelated: localStorage.getItem('unrelated'), draft: localStorage.getItem('problemCode_A'), broken }
  })
  expect(result).toEqual({ unrelated: 'keep', draft: null, broken: null })
})

test('storage denial does not break page or draft operations', async ({ page }) => {
  expect(await page.evaluate(() => {
    Object.defineProperty(window, 'localStorage', { get: () => { throw new DOMException('blocked', 'SecurityError') } })
    const store = window.fixture.storage
    store.remove('test'); store.clear()
    return [store.get('test'), store.set('test', 'value')]
  })).toEqual([null, false])
})

test('legacy information modal and loading error settle normally', async ({ page }) => {
  await page.evaluate(() => {
    const { $Modal, $Loading } = window.fixture.globals
    $Loading.start(); $Loading.error()
    $Modal.info({ title: 'Saved', content: 'Draft ready' })
  })
  await expect(page.getByText('Draft ready', { exact: true })).toBeVisible()
})
