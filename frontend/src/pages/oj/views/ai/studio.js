export const categories = [
  { id: 'logic', name: '逻辑实现', detail: '实现算法与数学函数', tone: 'orange' },
  { id: 'model', name: '模型定义', detail: '构建模型与训练流程', tone: 'purple' },
  { id: 'challenge', name: '数据挑战', detail: '隐藏测试集与指标评分', tone: 'teal' }
]
export const categoryFor = type => categories.find(category => category.id === type) || categories[0]
export const formatDate = value => {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '待定'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}
export const notebookFor = (problem, cells) => ({
  nbformat: 4, nbformat_minor: 5,
  metadata: { kernelspec: { display_name: 'Python 3', language: 'python', name: 'python3' }, language_info: { name: 'python' } },
  cells: [
    { id: 'instructions', cell_type: 'markdown', metadata: {}, source: ['# ' + problem.title + '\n', problem.objective,
      '\n\n## 接口约定\n', problem.signature || '', '\n\n## 输入\n', problem.inputSpec || '', '\n\n## 输出\n', problem.outputSpec || ''] },
    ...cells.map((source, index) => ({ id: 'answer-' + index, cell_type: 'code', metadata: {}, source: [source], execution_count: null, outputs: [] }))
  ]
})
export function download (filename, content, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url; link.download = filename
  document.body.appendChild(link); link.click(); link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
