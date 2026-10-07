import { apiErrorMessage } from './apiError'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import storage from '@/utils/storage'
import { STORAGE_KEY } from '@/utils/constants'
import ojAPI from '@oj/api'

function submissionMemoryFormat (memory) {
  if (memory === undefined) return '--'
  // 1048576 = 1024 * 1024
  let t = parseInt(memory) / 1048576
  return String(t.toFixed(0)) + 'MB'
}

function submissionTimeFormat (time) {
  if (time === undefined) return '--'
  return time + 'ms'
}

function getACRate (acCount, totalCount) {
  let rate = totalCount === 0 ? 0.00 : (acCount / totalCount * 100).toFixed(2)
  return String(rate) + '%'
}

// 去掉值为空的项，返回object
function filterEmptyValue (object) {
  let query = {}
  Object.keys(object).forEach(key => {
    if (object[key] || object[key] === 0 || object[key] === false) {
      query[key] = object[key]
    }
  })
  return query
}

// 按指定字符数截断添加换行，非英文字符按指定字符的半数截断
function breakLongWords (value, length = 16) {
  let re
  if (escape(value).indexOf('%u') === -1) {
    // 没有中文
    re = new RegExp('(.{' + length + '})', 'g')
  } else {
    // 中文字符
    re = new RegExp('(.{' + (length / 2 + 1) + '})', 'g')
  }
  return value.replace(re, '$1\n')
}

async function downloadFile (url) {
  try {
    const response = await axios.get(url, {responseType: 'blob'})
    const type = response.headers['content-type'] || ''
    if (type.includes('json')) {
      let message = 'Invalid file format'
      try {
        const payload = JSON.parse(await response.data.text())
        if (typeof payload.data === 'string') message = payload.data
      } catch {}
      throw new Error(message)
    }
    const link = document.createElement('a')
    const objectURL = window.URL.createObjectURL(response.data)
    try {
      link.href = objectURL
      link.download = ((response.headers['content-disposition'] || '').split('filename=')[1] || 'download').replace(/^"|"$/g, '')
      document.body.appendChild(link)
      link.click()
    } finally {
      link.remove()
      window.setTimeout(() => window.URL.revokeObjectURL(objectURL), 1000)
    }
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
    throw error
  }
}

function getLanguages () {
  return new Promise((resolve, reject) => {
    let languages = storage.get(STORAGE_KEY.languages)
    if (languages) {
      resolve(languages)
      return
    }
    ojAPI.getLanguages().then(res => {
      let languages = res.data.data.languages
      storage.set(STORAGE_KEY.languages, languages)
      resolve(languages)
    }, err => {
      reject(err)
    })
  })
}

export default {
  submissionMemoryFormat: submissionMemoryFormat,
  submissionTimeFormat: submissionTimeFormat,
  getACRate: getACRate,
  filterEmptyValue: filterEmptyValue,
  breakLongWords: breakLongWords,
  downloadFile: downloadFile,
  getLanguages: getLanguages
}
