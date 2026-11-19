import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { login as loginApi, logout as logoutApi, isAuthenticated } from '../api/auth'

interface AuthContextType {
  user: { username: string } | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<{ username: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const initAuth = () => {
      if (isAuthenticated()) {
        const token = localStorage.getItem('oam_auth_token')
        if (token) {
          try {
            const payload = JSON.parse(atob(token.split('.')[1]))
            setUser({ username: payload.username || 'admin' })
          } catch {
            setUser({ username: 'admin' })
          }
        }
      }
      setLoading(false)
    }
    initAuth()
  }, [])

  const login = async (username: string, password: string) => {
    await loginApi(username, password)
    setUser({ username })
  }

  const logout = () => {
    logoutApi()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}