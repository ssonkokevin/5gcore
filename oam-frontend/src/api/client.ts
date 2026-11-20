import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { getAuthToken, removeAuthToken } from './auth'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Request interceptor for auth
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAuthToken()
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      removeAuthToken()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Generic API functions
export const apiGet = <T>(url: string, params?: Record<string, any>) =>
  api.get<T>(url, { params }).then((res) => res.data)

export const apiPost = <T>(url: string, data?: any, config?: any) =>
  api.post<T>(url, data, config).then((res) => res.data)

export const apiPut = <T>(url: string, data?: any) =>
  api.put<T>(url, data).then((res) => res.data)

export const apiPatch = <T>(url: string, data?: any) =>
  api.patch<T>(url, data).then((res) => res.data)

export const apiDelete = <T>(url: string) =>
  api.delete<T>(url).then((res) => res.data)

// File upload helper
export const apiUpload = <T>(url: string, formData: FormData) =>
  api.post<T>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000, // 5 min for large uploads
  }).then((res) => res.data)