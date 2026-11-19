import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input, Label, Select, Switch } from '@/components/ui'
import { Save, RefreshCw, BarChart3, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import { useKPICurrent, useKPITimeSeries } from '@/api/queries'
import { toast } from 'react-hot-toast'
import { clsx } from 'clsx'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

export function KPISettings() {
  const [refreshInterval, setRefreshInterval] = useState(10)
  const [retentionDays, setRetentionDays] = useState(30)
  const [alertThresholds, setAlertThresholds] = useState({
    auth_success_rate: 0.99,
    registration_success_rate: 0.98,
    handover_success_rate: 0.95,
    latency_ms: 100,
    cpu_usage: 80,
    memory_usage: 85,
    disk_usage: 90,
  })
  const [enabledAlerts, setEnabledAlerts] = useState({
    auth_failure: true,
    registration_failure: true,
    handover_failure: true,
    high_latency: true,
    high_cpu: true,
    high_memory: true,
    high_disk: true,
    service_down: true,
  })
  const [saving, setSaving] = useState(false)

  const { data: kpi } = useKPICurrent()
  const { data: timeseries } = useKPITimeSeries(24)

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    await new Promise(r => setTimeout(r, 1000))
    toast.success('KPI settings saved')
    setSaving(false)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <BarChart3 className="h-6 w-6" />
          KPI Settings & Monitoring
        </h1>
        <p className="text-surface-500 dark:text-surface-400">Configure monitoring thresholds, alerting, and data retention</p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        <div className="card p-6">
          <h2 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4 flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Data Collection
          </h2>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <Label htmlFor="refresh_interval">Refresh Interval (seconds)</Label>
              <Input
                id="refresh_interval"
                type="number"
                min={5}
                max={300}
                value={String(refreshInterval)}
                onChange={(e) => setRefreshInterval(Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="retention_days">Data Retention (days)</Label>
              <Input
                id="retention_days"
                type="number"
                min={1}
                max={365}
                value={String(retentionDays)}
                onChange={(e) => setRetentionDays(Number(e.target.value))}
              />
            </div>
            <div className="flex items-end">
              <Label className="w-full">Real-time Updates</Label>
              <Switch
                id="realtime"
                checked={true}
                onChange={() => {}}
              />
            </div>
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Alert Thresholds
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Object.entries(alertThresholds).map(([key, defaultValue]) => {
              const isRate = key.includes('rate')
              const isMs = key.includes('ms')
              const isUsage = key.includes('usage')
              return (
                <div key={key} className="p-4 bg-surface-50 dark:bg-surface-800/50 rounded-lg">
                  <Label htmlFor={key} className="block mb-2 text-sm">
                    {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </Label>
                  <Input
                    id={key}
                    type="number"
                    step={isRate ? '0.01' : isMs ? '1' : '1'}
                    min={isRate ? '0' : isUsage ? '0' : '0'}
                    max={isRate ? '1' : isUsage ? '100' : '10000'}
                    value={String(alertThresholds[key as keyof typeof alertThresholds])}
                    onChange={(e) => setAlertThresholds(prev => ({ ...prev, [key]: isRate ? Number(e.target.value) : Number(e.target.value) }))}
                    className="font-mono"
                  />
                  <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
                    {isRate ? '%' : isMs ? 'ms' : isUsage ? '%' : ''}
                  </p>
                </div>
              )
            })}
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4 flex items-center gap-2">
            <CheckCircle className="h-5 w-5" />
            Enabled Alerts
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {Object.entries(enabledAlerts).map(([key, defaultValue]) => (
              <div key={key} className="flex items-center gap-2">
                <Switch
                  id={`alert_${key}`}
                  checked={enabledAlerts[key as keyof typeof enabledAlerts]}
                  onChange={(checked) => setEnabledAlerts(prev => ({ ...prev, [key]: checked }))}
                />
                <Label htmlFor={`alert_${key}`} className="mb-0 text-sm">
                  {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </Label>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Current KPI Snapshot
          </h2>
          {kpi ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {[
                { label: 'Active UEs', value: kpi.active_ues.toLocaleString(), icon: '👥' },
                { label: 'PDU Sessions', value: kpi.pdu_sessions.toLocaleString(), icon: '📡' },
                { label: 'Throughput UL', value: `${kpi.throughput_ul_mbps.toFixed(1)} Mbps`, icon: '⬆️' },
                { label: 'Throughput DL', value: `${kpi.throughput_dl_mbps.toFixed(1)} Mbps`, icon: '⬇️' },
                { label: 'Auth Success', value: `${(kpi.auth_success_rate * 100).toFixed(2)}%`, icon: '🔐', status: kpi.auth_success_rate > 0.99 ? 'good' : 'bad' },
                { label: 'Reg Success', value: `${(kpi.registration_success_rate * 100).toFixed(2)}%`, icon: '📝', status: kpi.registration_success_rate > 0.98 ? 'good' : 'bad' },
                { label: 'HO Success', value: `${(kpi.handover_success_rate * 100).toFixed(2)}%`, icon: '🔄', status: kpi.handover_success_rate > 0.95 ? 'good' : 'bad' },
                { label: 'Latency', value: `${kpi.latency_ms} ms`, icon: '⏱️', status: kpi.latency_ms < 100 ? 'good' : 'bad' },
              ].map((item) => (
                <div key={item.label} className={clsx('p-4 rounded-lg', item.status === 'bad' ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800' : 'bg-surface-50 dark:bg-surface-800/50')}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-2xl">{item.icon}</span>
                    <span className="text-sm text-surface-500 dark:text-surface-400">{item.label}</span>
                  </div>
                  <div className={clsx('text-2xl font-bold', item.status === 'bad' ? 'text-red-600 dark:text-red-400' : 'text-surface-900 dark:text-surface-100')}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
            </div>
          )}
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            24-Hour Trends
          </h2>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeseries || []}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-surface-200 dark:stroke-surface-700" />
                <XAxis dataKey="timestamp" tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="active_ues" stroke="#0ea5e9" name="Active UEs" dot={false} />
                <Line type="monotone" dataKey="pdu_sessions" stroke="#22c55e" name="PDU Sessions" dot={false} />
                <Line type="monotone" dataKey="throughput_dl_mbps" stroke="#f59e0b" name="Throughput DL (Mbps)" dot={false} yAxisId="right" />
                <Line type="monotone" dataKey="auth_success_rate" stroke="#ef4444" name="Auth Success Rate" dot={false} yAxisId="right" strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => toast('Reset to defaults not implemented', { icon: 'ℹ️' })}>
            Reset to Defaults
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? (
              <>
                <Save className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Settings
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  )
}