import { useAuth } from '../../context/AuthContext'
import { LogOut, User, Bell, Moon, Sun, ChevronDown } from 'lucide-react'
import { useState, useEffect } from 'react'

export function Header() {
  const { user, logout } = useAuth()
  const [darkMode, setDarkMode] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('darkMode')
    if (saved) {
      setDarkMode(JSON.parse(saved))
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setDarkMode(true)
    }
  }, [])

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    localStorage.setItem('darkMode', JSON.stringify(darkMode))
  }, [darkMode])

  return (
    <header className="h-16 bg-white dark:bg-surface-900 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-semibold text-surface-900 dark:text-surface-100 truncate max-w-md">
          5G Core Operations & Maintenance
        </h1>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => setDarkMode(!darkMode)}
          className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>

        <button
          className="relative p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          onClick={() => setNotificationsOpen(!notificationsOpen)}
          aria-label="Notifications"
          aria-expanded={notificationsOpen}
        >
          <Bell className="h-5 w-5" />
          <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-500" />
        </button>

        <div className="relative">
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
            aria-label="User menu"
            aria-expanded={userMenuOpen}
          >
            <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
              <User className="h-4 w-4 text-primary-600 dark:text-primary-400" />
            </div>
            <span className="hidden sm:block text-sm font-medium text-surface-700 dark:text-surface-300">
              {user?.username || 'Admin'}
            </span>
            <ChevronDown className="h-4 w-4 text-surface-500" />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-surface-800 rounded-lg shadow-lg border border-surface-200 dark:border-surface-700 py-1 z-50">
              <div className="px-4 py-2 border-b border-surface-200 dark:border-surface-700">
                <p className="text-sm font-medium text-surface-900 dark:text-surface-100">{user?.username || 'Admin'}</p>
                <p className="text-xs text-surface-500 dark:text-surface-400">Administrator</p>
              </div>
              <button
                onClick={logout}
                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-surface-100 dark:hover:bg-surface-700"
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}