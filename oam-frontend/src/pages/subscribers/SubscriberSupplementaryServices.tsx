import { useState } from 'react'
import { FullProfile, SupplementaryService } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'

interface SubscriberSupplementaryServicesProps {
  fullProfile: FullProfile | undefined
  imsi: string
}

export function SubscriberSupplementaryServices({ fullProfile, imsi }: SubscriberSupplementaryServicesProps) {
  const [showModal, setShowModal] = useState(false)
  const [editingService, setEditingService] = useState<SupplementaryService | null>(null)
  const services = fullProfile?.supplementary_services || []

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setShowModal(false)
    setEditingService(null)
  }

  const serviceTypes = [
    { value: 'CFU', label: 'Call Forwarding Unconditional' },
    { value: 'CFB', label: 'Call Forwarding Busy' },
    { value: 'CFNRy', label: 'Call Forwarding No Reply' },
    { value: 'CFNRc', label: 'Call Forwarding Not Reachable' },
    { value: 'CLIP', label: 'Calling Line Identification Presentation' },
    { value: 'CLIR', label: 'Calling Line Identification Restriction' },
    { value: 'COLP', label: 'Connected Line Identification Presentation' },
    { value: 'COLR', label: 'Connected Line Identification Restriction' },
    { value: 'CW', label: 'Call Waiting' },
    { value: 'BAOC', label: 'Barring of All Outgoing Calls' },
    { value: 'BOIC', label: 'Barring of Outgoing International Calls' },
    { value: 'BOICexHC', label: 'Barring of Outgoing International Calls except Home' },
    { value: 'BAIC', label: 'Barring of All Incoming Calls' },
    { value: 'BICRoam', label: 'Barring of Incoming Calls when Roaming' },
    { value: 'USSD', label: 'Unstructured Supplementary Service Data' },
    { value: 'MMTel', label: 'Multimedia Telephony' },
    { value: 'RCS', label: 'Rich Communication Services' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Supplementary Services</h3>
        <Button onClick={() => { setEditingService(null); setShowModal(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add Service
        </Button>
      </div>

      {services.length === 0 ? (
        <div className="card p-12 text-center">
          <Search className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
          <p className="text-surface-500 dark:text-surface-400">No supplementary services provisioned</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowModal(true)}>
            Add First Service
          </Button>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr className="table-header">
                <th className="table-head">Service Code</th>
                <th className="table-head">Service Name</th>
                <th className="table-head">Provision Status</th>
                <th className="table-head">Forwarding Number</th>
                <th className="table-head">Condition</th>
                <th className="table-head">CLIP/CLIR</th>
                <th className="table-head">CAMEL Phase</th>
                <th className="table-head">Actions</th>
              </tr>
            </thead>
            <tbody>
              {services.map((svc) => (
                <tr key={svc.service_code} className="table-row">
                  <td className="table-cell font-mono text-sm">{svc.service_code}</td>
                  <td className="table-cell">{svc.service_name || serviceTypes.find(s => s.value === svc.service_code)?.label || '—'}</td>
                  <td className="table-cell">
                    <span className={`badge ${svc.provision_status === 'active' ? 'badge-success' : svc.provision_status === 'provisioned' ? 'badge-info' : 'badge-gray'}`}>
                      {svc.provision_status}
                    </span>
                  </td>
                  <td className="table-cell font-mono">{svc.forwarding_number || '—'}</td>
                  <td className="table-cell">{svc.forwarding_condition}</td>
                  <td className="table-cell">
                    <span className="badge badge-gray">CLIP: {svc.clip_provisioned ? 'Y' : 'N'}</span>
                    <span className="badge badge-gray">CLIR: {svc.clir_option}</span>
                  </td>
                  <td className="table-cell">Phase {svc.camel_phase}</td>
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditingService(svc); setShowModal(true); }}
                        className="p-1.5 rounded hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                        title="Edit"
                      >
                        <Edit className="h-4 w-4" />
                      </button>
                      <button className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors text-red-600" title="Delete">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-auto">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{editingService ? 'Edit' : 'Add'} Supplementary Service</h3>
              <button onClick={() => { setShowModal(false); setEditingService(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="service_code">Service Code *</Label>
                  <Select
                    id="service_code"
                    value={editingService?.service_code || ''}
                    onChange={(e) => console.log(e.target.value)}
                    disabled={!!editingService}
                    required
                    options={serviceTypes}
                    placeholder="Select service"
                  />
                </div>
                <div>
                  <Label htmlFor="service_name">Service Name</Label>
                  <Input id="service_name" value={editingService?.service_name || ''} onChange={(e) => console.log(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="provision_status">Provision Status</Label>
                  <Select
                    id="provision_status"
                    value={editingService?.provision_status || 'not_provisioned'}
                    onChange={(e) => console.log(e.target.value)}
                    options={[
                      { value: 'not_provisioned', label: 'Not Provisioned' },
                      { value: 'provisioned', label: 'Provisioned' },
                      { value: 'active', label: 'Active' },
                      { value: 'deactivated', label: 'Deactivated' },
                    ]}
                  />
                </div>
                <div>
                  <Label htmlFor="forwarding_number">Forwarding Number</Label>
                  <Input id="forwarding_number" value={editingService?.forwarding_number || ''} onChange={(e) => console.log(e.target.value)} placeholder="+1234567890" />
                </div>
                <div>
                  <Label htmlFor="forwarding_condition">Forwarding Condition</Label>
                  <Select
                    id="forwarding_condition"
                    value={editingService?.forwarding_condition || 'unconditional'}
                    onChange={(e) => console.log(e.target.value)}
                    options={[
                      { value: 'unconditional', label: 'Unconditional' },
                      { value: 'busy', label: 'Busy' },
                      { value: 'no_reply', label: 'No Reply' },
                      { value: 'not_reachable', label: 'Not Reachable' },
                      { value: 'all', label: 'All' },
                    ]}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="clip_provisioned" checked={editingService?.clip_provisioned ?? true} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="clip_provisioned" className="mb-0">CLIP Provisioned</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="clir_provisioned" checked={editingService?.clir_provisioned ?? true} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="clir_provisioned" className="mb-0">CLIR Provisioned</Label>
                </div>
                <div>
                  <Label htmlFor="camel_phase">CAMEL Phase</Label>
                  <Select
                    id="camel_phase"
                    value={String(editingService?.camel_phase || 3)}
                    onChange={(e) => console.log(e.target.value)}
                    options={[
                      { value: '1', label: 'Phase 1' },
                      { value: '2', label: 'Phase 2' },
                      { value: '3', label: 'Phase 3' },
                      { value: '4', label: 'Phase 4' },
                    ]}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditingService(null); }}>
                  Cancel
                </Button>
                <Button type="submit">{editingService ? 'Update' : 'Create'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}