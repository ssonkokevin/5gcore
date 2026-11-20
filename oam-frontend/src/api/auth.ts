const TOKEN_KEY = 'oam_auth_token'
const REFRESH_TOKEN_KEY = 'oam_refresh_token'

export const getAuthToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY)
}

export const setAuthToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token)
}

export const removeAuthToken = (): void => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

export const getRefreshToken = (): string | null => {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export const setRefreshToken = (token: string): void => {
  localStorage.setItem(REFRESH_TOKEN_KEY, token)
}

export const isAuthenticated = (): boolean => {
  return !!getAuthToken()
}

export const login = async (username: string, password: string): Promise<{ access: string; refresh: string }> => {
  const response = await fetch('/api/auth/login/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  
  if (!response.ok) {
    throw new Error('Invalid credentials')
  }
  
  const data = await response.json()
  setAuthToken(data.access)
  setRefreshToken(data.refresh)
  return data
}

export const logout = (): void => {
  removeAuthToken()
  window.location.href = '/login'
}