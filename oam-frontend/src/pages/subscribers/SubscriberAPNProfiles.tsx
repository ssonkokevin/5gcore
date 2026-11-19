import { useState } from 'react'
import { FullProfile, APNProfile } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'
import { formatNumber } from '@/utils/format'

interface SubscriberAPNProfilesProps {
  fullProfile: FullProfile | undefined
  imsi: string
}

export function SubscriberAPNProfiles({ fullProfile, imsi }: SubscriberAPNProfilesProps) {
  const [showModal, setShowModal] = useState(false)
  const [editingApn, setEditingApn] = useState<APNProfile | null>(null)
  const apnProfiles = fullProfile?.apn_profiles || []

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // TODO: Implement API call
    setShowModal(false)
    setEditingApn(null)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">APN/DNN Profiles</h3>
        <Button onClick={() => { setEditingApn(null); setShowModal(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add APN Profile
        </Button>
      </div>

      {apnProfiles.length === 0 ? (
        <div className="card p-12 text-center">
          <Search className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
          <p className="text-surface-500 dark:text-surface-400">No APN profiles configured</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowModal(true)}>
            Create First APN Profile
          </Button>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr className="table-header">
                <th className="table-head">APN/DNN</th>
                <th className="table-head">Type</th>
                <th className="table-head">QCI</th>
                <th className="table-head">ARP</th>
                <th className="table-head">PDN Type</th>
                <th className="table-head">AMBR (UL/DL)</th>
                <th className="table-head">Default</th>
                <th className="table-head">Active</th>
                <th className="table-head">Actions</th>
              </tr>
            </thead>
            <tbody>
              {apnProfiles.map((apn) => (
                <tr key={apn.apn} className="table-row">
                  <td className="table-cell font-mono text-sm">{apn.apn}</td>
                  <td className="table-cell">
                    <span className="badge badge-info">{apn.apn_type}</span>
                  </td>
                  <td className="table-cell">{apn.qci}</td>
                  <td className="table-cell">{apn.arp_priority} (P:{apn.arp_preempt_cap ? '1' : '0'} V:{apn.arp_preempt_vuln ? '1' : '0'})</td>
                  <td className="table-cell">{apn.pdn_type}</td>
                  <td className="table-cell font-mono text-sm">{formatNumber(apn.apn_ambr_ul)} / {formatNumber(apn.apn_ambr_dl)}</td>
                  <td className="table-cell">{apn.is_default ? 'Yes' : 'No'}</td>
                  <td className="table-cell">{apn.is_active ? 'Yes' : 'No'}</td>
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditingApn(apn); setShowModal(true); }}
                        className="p-1.5 rounded hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                        title="Edit"
                      >
                        <Edit className="h-4 w-4" />
                      </button>
                      <button
                        className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors text-red-600"
                        title="Delete"
                      >
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
              <h3 className="text-lg font-semibold">{editingApn ? 'Edit' : 'Add'} APN Profile</h3>
              <button onClick={() => { setShowModal(false); setEditingApn(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="apn">APN/DNN *</Label>
                  <Input
                    id="apn"
                    value={editingApn?.apn || ''}
                    onChange={(e) => console.log(e.target.value)}
                    disabled={!!editingApn}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="apn_type">APN Type</Label>
                  <Select
                    id="apn_type"
                    value={editingApn?.apn_type || 'internet'}
                    onChange={(e) => console.log(e.target.value)}
                    options={[
                      { value: 'internet', label: 'Internet' },
                      { value: 'ims', label: 'IMS' },
                      { value: 'emergency', label: 'Emergency' },
                      { value: 'mms', label: 'MMS' },
                      { value: 'enterprise', label: 'Enterprise' },
                      { value: 'm2m', label: 'M2M' },
                      { value: 'mbs', label: 'MBS' },
                      { value: 'fmc', label: 'FMC' },
                    ]}
                  />
                </div>
                <div>
                  <Label htmlFor="qci">QCI</Label>
                  <Input id="qci" type="number" value={String(editingApn?.qci || 9)} onChange={(e) => console.log(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="arp_priority">ARP Priority</Label>
                  <Input id="arp_priority" type="number" value={String(editingApn?.arp_priority || 8)} onChange={(e) => console.log(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="pdn_type">PDN Type</Label>
                  <Select
                    id="pdn_type"
                    value={editingApn?.pdn_type || 'ipv4v6'}
                    onChange={(e) => console.log(e.target.value)}
                    options={[
                      { value: 'ipv4', label: 'IPv4' },
                      { value: 'ipv6', label: 'IPv6' },
                      { value: 'ipv4v6', label: 'IPv4v6' },
                      { value: 'non-ip', label: 'Non-IP' },
                    ]}
                  />
                </div>
                <div>
                  <Label htmlFor="apn_ambr_ul">APN AMBR UL (bps)</Label>
                  <Input id="apn_ambr_ul" type="number" value={String(editingApn?.apn_ambr_ul || 100000000)} onChange={(e) => console.log(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="apn_ambr_dl">APN AMBR DL (bps)</Label>
                  <Input id="apn_ambr_dl" type="number" value={String(editingApn?.apn_ambr_dl || 100000000)} onChange={(e) => console.log(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="dns_primary">Primary DNS</Label>
                  <Input id="dns_primary" value={editingApn?.dns_primary || '8.8.8.8'} onChange={(e) => console.log(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="is_default">Default APN</Label>
                  <Input id="is_default" type="checkbox" checked={Boolean(editingApn?.is_default)} onChange={(e) => console.log(e.target.checked)} />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditingApn(null); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={false}>
                  {editingApn ? 'Update' : 'Create'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}