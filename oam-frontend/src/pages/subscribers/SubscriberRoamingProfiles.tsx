import { useState } from 'react'
import { FullProfile, RoamingProfile } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Globe } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'

interface SubscriberRoamingProfilesProps {
  fullProfile: FullProfile | undefined
  imsi: string
}

export function SubscriberRoamingProfiles({ fullProfile, imsi }: SubscriberRoamingProfilesProps) {
  const [showModal, setShowModal] = useState(false)
  const [editingProfile, setEditingProfile] = useState<RoamingProfile | null>(null)
  const profiles = fullProfile?.roaming_profiles || []

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setShowModal(false)
    setEditingProfile(null)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <Globe className="h-5 w-5" />
          Roaming Profiles (Per VPLMN)
        </h3>
        <Button onClick={() => { setEditingProfile(null); setShowModal(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add VPLMN Profile
        </Button>
      </div>

      {profiles.length === 0 ? (
        <div className="card p-12 text-center">
          <Globe className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
          <p className="text-surface-500 dark:text-surface-400">No roaming profiles configured</p>
          <p className="text-sm text-surface-400 dark:text-surface-500 mt-1">Add per-VPLMN policies for visited networks</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowModal(true)}>
            Create First Roaming Profile
          </Button>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr className="table-header">
                <th className="table-head">Visited PLMN</th>
                <th className="table-head">Roaming Allowed</th>
                <th className="table-head">RAT Allowed</th>
                <th className="table-head">ODB Roaming</th>
                <th className="table-head">Charging Profile</th>
                <th className="table-head">V2X Roaming</th>
                <th className="table-head">RedCap Roaming</th>
                <th className="table-head">NTN Roaming</th>
                <th className="table-head">Actions</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => (
                <tr key={profile.visited_plmn} className="table-row">
                  <td className="table-cell font-mono font-medium">{profile.visited_plmn}</td>
                  <td className="table-cell">
                    <span className={`badge ${profile.roaming_allowed ? 'badge-success' : 'badge-error'}`}>
                      {profile.roaming_allowed ? 'Allowed' : 'Denied'}
                    </span>
                  </td>
                  <td className="table-cell text-sm">
                    {profile.rat_allowed ? JSON.stringify(profile.rat_allowed) : 'All'}
                  </td>
                  <td className="table-cell">{profile.odb_roaming ? 'Yes' : 'No'}</td>
                  <td className="table-cell font-mono text-sm">{profile.charging_profile_id || '—'}</td>
                  <td className="table-cell">{profile.v2x_roaming ? 'Yes' : 'No'}</td>
                  <td className="table-cell">{profile.redcap_roaming ? 'Yes' : 'No'}</td>
                  <td className="table-cell">{profile.ntn_roaming ? 'Yes' : 'No'}</td>
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
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-auto">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{editingProfile ? 'Edit' : 'Add'} Roaming Profile</h3>
              <button onClick={() => { setShowModal(false); setEditingProfile(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="visited_plmn">Visited PLMN (MCC+MNC) *</Label>
                  <Input
                    id="visited_plmn"
                    value={editingProfile?.visited_plmn || ''}
                    onChange={(e) => console.log(e.target.value)}
                    disabled={!!editingProfile}
                    required
                    placeholder="e.g., 64108"
                    maxLength={6}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="roaming_allowed" checked={editingProfile?.roaming_allowed ?? true} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="roaming_allowed" className="mb-0">Roaming Allowed</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="odb_roaming" checked={editingProfile?.odb_roaming} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="odb_roaming" className="mb-0">ODB Roaming</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="v2x_roaming" checked={editingProfile?.v2x_roaming} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="v2x_roaming" className="mb-0">V2X Roaming</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="redcap_roaming" checked={editingProfile?.redcap_roaming} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="redcap_roaming" className="mb-0">RedCap Roaming</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Input type="checkbox" id="ntn_roaming" checked={editingProfile?.ntn_roaming} onChange={(e) => console.log(e.target.checked)} />
                  <Label htmlFor="ntn_roaming" className="mb-0">NTN Roaming</Label>
                </div>
                <div>
                  <Label htmlFor="charging_profile_id">Charging Profile ID</Label>
                  <Input id="charging_profile_id" value={editingProfile?.charging_profile_id || ''} onChange={(e) => console.log(e.target.value)} />
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