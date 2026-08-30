import axios from 'axios'

export const api = axios.create({ baseURL: '/api', timeout: 30000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.dispatchEvent(new Event('auth-expired'))
    }
    return Promise.reject(error)
  },
)

export function errorText(error) {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join('；')
  return detail || error.message || '操作失败'
}

export function formatTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

export function formatBytes(value) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let number = Number(value)
  let index = 0
  while (number >= 1024 && index < units.length - 1) {
    number /= 1024
    index += 1
  }
  return `${number.toFixed(index ? 2 : 0)} ${units[index]}`
}
