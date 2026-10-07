import axios from 'axios'

const client = axios.create({ baseURL: '/api/', timeout: 20000, xsrfCookieName: 'csrftoken', xsrfHeaderName: 'X-CSRFToken' })
export async function request (path, method = 'get', data = {}) {
  const response = await client.request({ url: path, method, ...(method === 'get' ? { params: data } : { data }) })
  if (response.data.error) {
    const error = new Error(typeof response.data.data === 'string' ? response.data.data : '请求失败')
    error.code = response.data.error
    throw error
  }
  return response.data.data
}
export const studioApi = (path, method = 'get', data = {}) => request('ai/' + path, method, data)
export const activeStatuses = new Set(['PENDING', 'RUNNING', 'JUDGING', 'TRAINING', 'SCORING'])
