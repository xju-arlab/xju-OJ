export function apiErrorMessage (error, fallback = '请求失败，请稍后重试') {
  const payload = error?.response?.data ?? error?.data
  if (typeof payload?.data === 'string' && payload.data) return payload.data
  if (typeof payload?.error === 'string' && payload.error) return payload.error
  if (typeof error?.message === 'string' && error.message) return error.message
  return fallback
}
