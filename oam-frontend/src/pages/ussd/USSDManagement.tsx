import { useState } from 'react'
import { useUSSDRoutes, useCreateUSSDRoute } from '@/api/queries'
import { USSDRoute } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Hash, Shield, ArrowRight, ExternalLink, Globe } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'
import { toast } from 'react-hot-toast'

export function USSDManagement() {
  const [showModal, setShowModal] = useState(false)
  const [editingRoute, setEditingRoute] = useState<USSDRoute | null>(null)

  const { data: routes, refetch } = useUSSDRoutes()
  const createMutation = useCreateUSSDRoute()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget as HTMLFormElement)
    const data = {
      ussd_string: formData.get('ussd_string') as string,
      destination_type: formData.get('destination_type') as string,
      destination_address: formData.get('destination_address') as string || undefined,
      gsm_scf_address: formData.get('gsm_scf_address') as string || undefined,
      service_key: Number(formData.get('service_key')) || 0,
      default_response: formData.get('default_response') as string || undefined,
      timeout_sec: Number(formData.get('timeout_sec')) || 10,
      mvno_mcc: formData.get('mvno_mcc') as string || undefined,
      mvno_mnc: formData.get('mvno_mnc') as string || undefined,
      fiveg_ussd_allowed: formData.get('fiveg_ussd_allowed') === 'on',
      is_active: true,
      priority: Number(formData.get('priority')) || 100,
    }
    createMutation.mutate(data, {
      onSuccess: () => { toast.success('USSD route created'); refetch(); setShowModal(false); setEditingRoute(null); },
      onError: () => toast.error('Failed to create USSD route'),
    })
  }

  const destTypeIcons: Record<string, any> = {
    internal: Hash, external_ussd_gw: ExternalLink, scp: Shield, gmlc: Globe, imsi_based: ArrowRight,
  }

  if (routes === undefined) {
    return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">USSD Routing</h1>
          <p className="text-surface-500 dark:text-surface-400">Configure USSD string routing and CAMEL/SCP integration</p>
        </div>
        <Button onClick={() => { setEditingRoute(null); setShowModal(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add USSD Route
        </Button>
      </div>

      <div className="card">
        {routes.length === 0 ? (
          <div className="p-12 text-center">
            <Hash className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
            <p className="text-surface-500 dark:text-surface-400">No USSD routes configured</p>
            <Button variant="outline" className="mt-4" onClick={() => { setEditingRoute(null); setShowModal(true); }}>
              Create First USSD Route
            </Button>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr className="table-header">
                  <th className="table-head">USSD String</th>
                  <th className="table-head">Destination Type</th>
                  <th className="table-head">Destination Address</th>
                  <th className="table-head">gsmSCF Address</th>
                  <th className="table-head">Service Key</th>
                  <th className="table-head">Default Response</th>
                  <th className="table-head">Timeout</th>
                  <th className="table-head">5G USSD</th>
                  <th className="table-head">MVNO</th>
                  <th className="table-head">Active</th>
                  <th className="table-head">Priority</th>
                  <th className="table-head">Actions</th>
                </tr>
              </thead>
              <tbody>
                {routes.map((route: USSDRoute) => {
                  const Icon = destTypeIcons[route.destination_type] || Hash
                  return (
                    <tr key={route.id} className="table-row">
                      <td className="table-cell font-mono font-medium">{route.ussd_string}</td>
                      <td className="table-cell">
                        <span className="flex items-center gap-1 badge badge-info">
                          <Icon className="h-3 w-3" />
                          {route.destination_type.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="table-cell font-mono text-sm">{route.destination_address || '—'}</td>
                      <td className="table-cell font-mono text-sm">{route.gsm_scf_address || '—'}</td>
                      <td className="table-cell">{route.service_key}</td>
                      <td className="table-cell text-sm max-w-xs truncate">{route.default_response || '—'}</td>
                      <td className="table-cell">{route.timeout_sec}s</td>
                      <td className="table-cell">{route.fiveg_ussd_allowed ? 'Yes' : 'No'}</td>
                      <td className="table-cell font-mono">{route.mvno_mcc && route.mvno_mnc ? `${route.mvno_mcc}-${route.mvno_mnc}` : '—'}</td>
                      <td className="table-cell">
                        <span className={`badge ${route.is_active ? 'badge-success' : 'badge-error'}`}>
                          {route.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="table-cell">{route.priority}</td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="sm" onClick={() => { setEditingRoute(route); setShowModal(true); }}><Edit className="h-4 w-4" /></Button>
                          <Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="h-4 w-4" /></Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-auto">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{editingRoute ? 'Edit' : 'Add'} USSD Route</h3>
              <button onClick={() => { setShowModal(false); setEditingRoute(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="ussd_string">USSD String *</Label>
                  <Input id="ussd_string" name="ussd_string" value={editingRoute?.ussd_string || ''} required disabled={!!editingRoute} placeholder="*123#" />
                </div>
                <div>
                  <Label htmlFor="destination_type">Destination Type *</Label>
                  <Select
                    id="destination_type"
                    name="destination_type"
                    value={editingRoute?.destination_type || 'internal'}
                    required
                    options={[
                      { value: 'internal', label: 'Internal' },
                      { value: 'external_ussd_gw', label: 'External USSD Gateway' },
                      { value: 'scp', label: 'SCP' },
                      { value: 'gmlc', label: 'GMLC' },
                      { value: 'imsi_based', label: 'IMSI Based' },
                    ]}
                  />
                </div>
                <div>
                  <Label htmlFor="destination_address">Destination Address</Label>
                  <Input id="destination_address" name="destination_address" value={editingRoute?.destination_address || ''} placeholder="IP:Port or FQDN" />
                </div>
                <div>
                  <Label htmlFor="gsm_scf_address">gsmSCF Address</Label>
                  <Input id="gsm_scf_address" name="gsm_scf_address" value={editingRoute?.gsm_scf_address || ''} placeholder="scf.example.com" />
                </div>
                <div>
                  <Label htmlFor="service_key">Service Key</Label>
                  <Input id="service_key" name="service_key" type="number" value={String(editingRoute?.service_key || 0)} min={0} />
                </div>
                <div>
                  <Label htmlFor="timeout_sec">Timeout (seconds)</Label>
                  <Input id="timeout_sec" name="timeout_sec" type="number" value={String(editingRoute?.timeout_sec || 10)} min={1} max={60} />
                </div>
                <div>
                  <Label htmlFor="default_response">Default Response</Label>
                  <Input id="default_response" name="default_response" value={editingRoute?.default_response || ''} placeholder="Default USSD response text" />
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="fiveg_ussd_allowed" name="fiveg_ussd_allowed" checked={editingRoute?.fiveg_ussd_allowed} />
                  <Label htmlFor="fiveg_ussd_allowed" className="mb-0">5G USSD Allowed</Label>
                </div>
                <div>
                  <Label htmlFor="mvno_mcc">MVNO MCC</Label>
                  <Input id="mvno_mcc" name="mvno_mcc" value={editingRoute?.mvno_mcc || ''} maxLength={3} placeholder="641" />
                </div>
                <div>
                  <Label htmlFor="mvno_mnc">MVNO MNC</Label>
                  <Input id="mvno_mnc" name="mvno_mnc" value={editingRoute?.mvno_mnc || ''} maxLength={3} placeholder="08" />
                </div>
                <div>
                  <Label htmlFor="priority">Priority</Label>
                  <Input id="priority" name="priority" type="number" value={String(editingRoute?.priority || 100)} min={1} />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditingRoute(null); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Saving...' : editingRoute ? 'Update' : 'Create'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}