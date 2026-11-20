import {
  Users,
  Database,
  Server,
  Activity,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { useKPICurrent, useKPITimeSeries } from '@/api/queries'
import { useSubscribers } from '@/api/queries'
import { formatNumber, formatBytes } from '@/utils/format'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'

const StatCard = ({
  title,
  value,
  icon: Icon,
  trend,
  trendUp = true,
  color = 'primary',
}: {
  title: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  trend?: string
  trendUp?: boolean
  color?: 'primary' | 'success' | 'warning' | 'danger'
}) => {
  const colors = {
    primary: 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300',
    success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    warning: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
    danger: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  }

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-surface-500 dark:text-surface-400">{title}</p>
          <p className="mt-2 text-3xl font-bold text-surface-900 dark:text-surface-100">{value}</p>
          {trend && (
            <p className="mt-1 flex items-center gap-1 text-sm">
              <TrendingUp className={clsx('h-4 w-4', trendUp ? 'text-green-600' : 'text-red-600')} />
              <span className={clsx(trendUp ? 'text-green-600' : 'text-red-600')}>{trend}</span>
            </p>
          )}
        </div>
        <div className={clsx('p-3 rounded-xl', colors[color])}>
          <Icon className="h-6 w-6" />
        </div>
      </div>
    </div>
  )
}

import { clsx } from 'clsx'

export function Dashboard() {
  const { data: kpi } = useKPICurrent()
  const { data: timeseries } = useKPITimeSeries(24)
  const { data: subscribers } = useSubscribers(1, 5)

  const stats = [
    {
      title: 'Active UEs',
      value: kpi?.active_ues ? formatNumber(kpi.active_ues) : '—',
      icon: Users,
      trend: '+2.3%',
      color: 'primary' as const,
    },
    {
      title: 'PDU Sessions',
      value: kpi?.pdu_sessions ? formatNumber(kpi.pdu_sessions) : '—',
      icon: Database,
      trend: '+1.1%',
      color: 'success' as const,
    },
    {
      title: 'Throughput DL',
      value: kpi?.throughput_dl_mbps ? `${kpi.throughput_dl_mbps.toFixed(1)} Mbps` : '—',
      icon: TrendingUp,
      trend: '+5.2%',
      color: 'warning' as const,
    },
    {
      title: 'Auth Success Rate',
      value: kpi?.auth_success_rate ? `${(kpi.auth_success_rate * 100).toFixed(2)}%` : '—',
      icon: CheckCircle,
      trend: kpi && kpi.auth_success_rate > 0.99 ? 'Healthy' : 'Degraded',
      trendUp: kpi ? kpi.auth_success_rate > 0.99 : true,
      color: 'danger' as const,
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">Dashboard</h1>
          <p className="text-surface-500 dark:text-surface-400">5G Core Network Overview</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat, i) => (
          <StatCard key={i} {...stat} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-100 mb-4">Throughput (24h)</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeseries || []}>
                <defs>
                  <linearGradient id="colorDownlink" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorUplink" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-surface-200 dark:stroke-surface-700" />
                <XAxis dataKey="timestamp" tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />
                <YAxis />
                <Tooltip
                  formatter={(value, name) => [
                    name === 'throughput_dl_mbps' ? `${(Number(value) ?? 0).toFixed(1)} Mbps` : `${(Number(value) ?? 0).toFixed(1)} Mbps`,
                    name === 'throughput_dl_mbps' ? 'Downlink' : 'Uplink',
                  ]}
                />
                <Area type="monotone" dataKey="throughput_dl_mbps" stroke="#0ea5e9" fillOpacity={1} fill="url(#colorDownlink)" name="Downlink" />
                <Area type="monotone" dataKey="throughput_ul_mbps" stroke="#22c55e" fillOpacity={1} fill="url(#colorUplink)" name="Uplink" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-100 mb-4">Active UEs & Sessions (24h)</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeseries || []}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-surface-200 dark:stroke-surface-700" />
                <XAxis dataKey="timestamp" tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="active_ues" stroke="#0ea5e9" dot={false} name="Active UEs" yAxisId="left" />
                <Line type="monotone" dataKey="pdu_sessions" stroke="#f59e0b" dot={false} name="PDU Sessions" yAxisId="right" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 card p-6">
          <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-100 mb-4">Recent Subscribers</h2>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr className="table-header">
                  <th className="table-head">IMSI</th>
                  <th className="table-head">MSISDN</th>
                  <th className="table-head">Status</th>
                  <th className="table-head">Network Access</th>
                  <th className="table-head">Created</th>
                </tr>
              </thead>
              <tbody>
                {subscribers?.results.slice(0, 10).map((sub) => (
                  <tr key={sub.imsi} className="table-row">
                    <td className="table-cell font-mono text-sm">{sub.imsi}</td>
                    <td className="table-cell">{sub.msisdn || '—'}</td>
                    <td className="table-cell">
                      <span className={clsx(
                        'badge',
                        sub.subscriber_status === 0 ? 'badge-success' :
                        sub.subscriber_status === 1 ? 'badge-error' :
                        sub.subscriber_status === 2 ? 'badge-warning' : 'badge-gray'
                      )}>
                        {sub.subscriber_status === 0 ? 'Active' :
                        sub.subscriber_status === 1 ? 'Barred' :
                        sub.subscriber_status === 2 ? 'Suspended' : 'Detached'}
                      </span>
                    </td>
                    <td className="table-cell">
                      <span className={clsx(
                        'badge',
                        sub.network_access_mode === 3 ? 'badge-info' :
                        sub.network_access_mode === 2 ? 'badge-success' : 'badge-gray'
                      )}>
                        {sub.network_access_mode === 3 ? '5G Only' :
                        sub.network_access_mode === 2 ? 'GPRS+CS' :
                        sub.network_access_mode === 1 ? 'CS Only' : 'GPRS Only'}
                      </span>
                    </td>
                    <td className="table-cell text-sm text-surface-500 dark:text-surface-400">
                      {new Date(sub.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-100 mb-4">System Health</h2>
          <div className="space-y-4">
            {[
              { name: 'UDM', status: 'healthy', latency: '12ms' },
              { name: 'AMF', status: 'healthy', latency: '8ms' },
              { name: 'SMF', status: 'healthy', latency: '15ms' },
              { name: 'UPF', status: 'healthy', latency: '5ms' },
              { name: 'PCF', status: 'healthy', latency: '10ms' },
              { name: 'AUSF', status: 'healthy', latency: '9ms' },
              { name: 'NRF', status: 'healthy', latency: '6ms' },
              { name: 'DRA', status: 'healthy', latency: '4ms' },
              { name: 'STP', status: 'healthy', latency: '3ms' },
              { name: 'HSS', status: 'healthy', latency: '11ms' },
            ].map((svc) => (
              <div key={svc.name} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className={clsx('h-2 w-2 rounded-full', svc.status === 'healthy' ? 'bg-green-500' : 'bg-red-500')} />
                  <span className="text-sm font-medium text-surface-700 dark:text-surface-300">{svc.name}</span>
                </div>
                <span className="text-sm text-surface-500 dark:text-surface-400 font-mono">{svc.latency}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}