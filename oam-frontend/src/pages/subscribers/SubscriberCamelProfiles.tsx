import { useState } from 'react'
import { FullProfile, CamelServiceProfile } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Shield } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'

interface SubscriberCamelProfilesProps {
  fullProfile: FullProfile | undefined
  imsi: string
}

export function SubscriberCamelProfiles({ fullProfile, imsi }: SubscriberCamelProfilesProps) {
  const [showModal, setShowModal] = useState(false)
  const [editingProfile, setEditingProfile] = useState<CamelServiceProfile | null>(null)
  const profiles = fullProfile?.camel_profiles || []

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setShowModal(false)
    setEditingProfile(null)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <Shield className="h-5 w-5" />
          CAMEL Service Profiles
        </h3>
        <Button onClick={() => { setEditingProfile(null); setShowModal(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add CAMEL Profile
        </Button>
      </div>

      {profiles.length === 0 ? (
        <div className="card p-12 text-center">
          <Shield className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
          <p className="text-surface-500 dark:text-surface-400">No CAMEL service profiles configured</p>
          <p className="text-sm text-surface-400 dark:text-surface-500 mt-1">Define CAMEL Phase 1-4 triggers and gsmSCF routing</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowModal(true)}>
            Create First CAMEL Profile
          </Button>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr className="table-header">
                <th className="table-head">Service Key</th>
                <th className="table-head">gsmSCF Address</th>
                <th className="table-head">Default Call Handling</th>
                <th className="table-head">TDP List</th>
                <th className="table-head">CSI Types</th>
                <th className="table-head">Actions</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => (
                <tr key={profile.service_key} className="table-row">
                  <td className="table-cell font-mono font-medium">{profile.service_key}</td>
                  <td className="table-cell font-mono text-sm">{profile.gsm_scf_address}</td>
                  <td className="table-cell">
                    <span className={`badge ${profile.default_call_handling === 'route_to_scf' ? 'badge-info' : profile.default_call_handling === 'release' ? 'badge-error' : 'badge-success'}`}>
                      {profile.default_call_handling.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="table-cell text-sm">
                    {profile.tdp_list ? JSON.stringify(profile.tdp_list).substring(0, 50) + '...' : '—'}
                  </td>
                  <td className="table-cell">
                    <div className="flex flex-wrap gap-1">
                      {profile.csi_psi && <span className="badge badge-gray">PSI</span>}
                      {profile.csi_csi && <span className="badge badge-gray">CSI</span>}
                      {profile.csi_ssi && <span className="badge badge-gray">SSI</span>}
                      {profile.csi_msi && <span className="badge badge-gray">MSI</span>}
                      {profile.csi_lsi && <span className="badge badge-gray">LSI</span>}
                      {profile.csi_v2x && <span className="badge badge-gray">V2X</span>}
                      {profile.csi_redcap && <span className="badge badge-gray">RedCap</span>}
                    </div>
                  </td>
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditingProfile(profile); setShowModal(true); }}
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
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-auto">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{editingProfile ? 'Edit' : 'Add'} CAMEL Service Profile</h3>
              <button onClick={() => { setShowModal(false); setEditingProfile(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="service_key">Service Key *</Label>
                  <Input
                    id="service_key"
                    type="number"
                    value={String(editingProfile?.service_key || '')}
                    onChange={(e) => console.log(e.target.value)}
                    disabled={!!editingProfile}
                    required
                    min={1}
                  />
                </div>
                <div>
                  <Label htmlFor="gsm_scf_address">gsmSCF Address *</Label>
                  <Input
                    id="gsm_scf_address"
                    value={editingProfile?.gsm_scf_address || ''}
                    onChange={(e) => console.log(e.target.value)}
                    required
                    placeholder="e.g., scf.example.com"
                  />
                </div>
                <div>
                  <Label htmlFor="default_call_handling">Default Call Handling</Label>
                  <Select
                    id="default_call_handling"
                    value={editingProfile?.default_call_handling || 'continue'}
                    onChange={(e) => console.log(e.target.value)}
                    options={[
                      { value: 'continue', label: 'Continue' },
                      { value: 'release', label: 'Release' },
                      { value: 'route_to_scf', label: 'Route to SCF' },
                    ]}
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="tdp_list">TDP List (JSON)</Label>
                <Input
                  id="tdp_list"
                  value={editingProfile?.tdp_list ? JSON.stringify(editingProfile.tdp_list, null, 2) : ''}
                  onChange={(e) => console.log(e.target.value)}
                  placeholder='[{"tdp_id": 2, "enabled": true}, {"tdp_id": 4, "enabled": true}]'
                  className="font-mono text-sm"
                />
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_psi" checked={Boolean(editingProfile?.csi_psi)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_psi" className="mb-0">CSI - PSI</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_csi" checked={Boolean(editingProfile?.csi_csi)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_csi" className="mb-0">CSI - CSI</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_ssi" checked={Boolean(editingProfile?.csi_ssi)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_ssi" className="mb-0">CSI - SSI</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_msi" checked={Boolean(editingProfile?.csi_msi)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_msi" className="mb-0">CSI - MSI</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_lsi" checked={Boolean(editingProfile?.csi_lsi)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_lsi" className="mb-0">CSI - LSI</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_v2x" checked={Boolean(editingProfile?.csi_v2x)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_v2x" className="mb-0">CSI - V2X</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="csi_redcap" checked={Boolean(editingProfile?.csi_redcap)} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="csi_redcap" className="mb-0">CSI - RedCap</Label>
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditingProfile(null); }}>
                  Cancel
                </Button>
                <Button type="submit">{editingProfile ? 'Update' : 'Create'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}