import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Upload,
  Database,
  Key,
  Server,
  GitBranch,
  Network,
  Globe,
  Settings,
  Shield,
  Menu,
  X,
} from 'lucide-react'
import { clsx } from 'clsx'
import { useState } from 'react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Subscribers', href: '/subscribers', icon: Users },
  { name: 'Batch Upload', href: '/batch-upload', icon: Upload },
  { name: 'IMSI Ranges', href: '/imsi-ranges', icon: Database },
  { name: 'Auth Vectors', href: '/auth-vectors', icon: Key },
  { name: 'DRA Management', href: '/dra', icon: Server },
  { name: 'STP Management', href: '/stp', icon: GitBranch },
  { name: 'Network Nodes', href: '/network-nodes', icon: Network },
  { name: 'Reference Data', href: '/reference', icon: Globe },
  { name: 'USSD Routes', href: '/ussd', icon: Shield },
  { name: 'KPI Settings', href: '/settings/kpi', icon: Settings },
]

export function Sidebar() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <>
      <button
        className="lg:hidden fixed top-4 left-4 z-50 btn-primary"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      <aside
        className={clsx(
          'fixed lg:static inset-y-0 left-0 z-40 bg-white dark:bg-surface-900 border-r border-surface-200 dark:border-surface-700 transition-all duration-300 flex flex-col',
          collapsed ? 'w-16' : 'w-64',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
        aria-label="Sidebar"
      >
        <div className="flex h-16 items-center justify-between px-4 border-b border-surface-200 dark:border-surface-700">
          {!collapsed && (
            <NavLink to="/" className="flex items-center gap-2 font-semibold text-lg text-primary-600">
              <Server className="h-6 w-6" />
              <span>5G Core OAM</span>
            </NavLink>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="lg:hidden p-1 rounded hover:bg-surface-100 dark:hover:bg-surface-800"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <Menu className="h-5 w-5" /> : <X className="h-5 w-5" />}
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-1" role="navigation" aria-label="Main navigation">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href || location.pathname.startsWith(item.href + '/')
            return (
              <NavLink
                key={item.name}
                to={item.href}
                className={clsx(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300'
                    : 'text-surface-600 hover:bg-surface-100 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-surface-800 dark:hover:text-surface-100',
                  collapsed && 'justify-center px-2'
                )}
                title={collapsed ? item.name : undefined}
                onClick={() => setMobileOpen(false)}
                aria-current={isActive ? 'page' : undefined}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                {!collapsed && <span>{item.name}</span>}
              </NavLink>
            )
          })}
        </nav>

        <div className="p-4 border-t border-surface-200 dark:border-surface-700">
          {!collapsed && (
            <div className="text-xs text-surface-500 dark:text-surface-400">
              <p className="font-medium">5G Core OAM v1.0</p>
              <p>3GPP Rel-15 to Rel-20</p>
            </div>
          )}
        </div>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
    </>
  )
}