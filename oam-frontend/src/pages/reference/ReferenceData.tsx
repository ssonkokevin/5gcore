import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { useMCCMNC, usePLMNProfiles } from '@/api/queries'
import { MCCMNC, PLMNProfile } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Globe, Flag, Network } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'
import { toast } from 'react-hot-toast'
import { useState } from 'react'

const MccMncTab = () => {
  const { data } = useMCCMNC()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">MCC/MNC Registry</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Entry</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">MCC</th><th className="table-head">MNC</th><th className="table-head">Country</th>
            <th className="table-head">Network</th><th className="table-head">Type</th><th className="table-head">Parent</th>
            <th className="table-head">Active</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: MCCMNC) => (
              <tr key={item.mcc + item.mnc} className="table-row">
                <td className="table-cell font-mono font-medium">{item.mcc}</td>
                <td className="table-cell font-mono font-medium">{item.mnc}</td>
                <td className="table-cell">{item.country_name || '—'}</td>
                <td className="table-cell">{item.network_name || '—'}</td>
                <td className="table-cell"><span className="badge badge-info">{item.network_type}</span></td>
                <td className="table-cell font-mono">{item.parent_mcc && item.parent_mnc ? `${item.parent_mcc}-${item.parent_mnc}` : '—'}</td>
                <td className="table-cell">{item.is_active ? 'Yes' : 'No'}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const PlmnProfileTab = () => {
  const { data } = usePLMNProfiles()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">PLMN Profiles</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Profile</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">PLMN ID</th><th className="table-head">Name</th><th className="table-head">EPS</th>
            <th className="table-head">5G</th><th className="table-head">RedCap</th><th className="table-head">NTN</th>
            <th className="table-head">5G-Adv</th><th className="table-head">HPLMN/VPLMN</th><th className="table-head">TAC Range</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: PLMNProfile) => (
              <tr key={item.plmn_id} className="table-row">
                <td className="table-cell font-mono font-medium">{item.plmn_id}</td>
                <td className="table-cell">{item.plmn_name || '—'}</td>
                <td className="table-cell">{item.eps_supported ? 'Yes' : 'No'}</td>
                <td className="table-cell">{item.fiveg_supported ? 'Yes' : 'No'}</td>
                <td className="table-cell">{item.redcap_supported ? 'Yes' : 'No'}</td>
                <td className="table-cell">{item.ntn_supported ? 'Yes' : 'No'}</td>
                <td className="table-cell">{item.fiveg_advanced_supported ? 'Yes' : 'No'}</td>
                <td className="table-cell">
                  <span className={`badge ${item.hplmn_allowed ? 'badge-success' : 'badge-error'}`}>H</span>
                  <span className={`badge ${item.vplmn_allowed ? 'badge-success' : 'badge-error'}`}>V</span>
                </td>
                <td className="table-cell font-mono text-sm">{item.tac_range_start} - {item.tac_range_end}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ReferenceData() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <Globe className="h-6 w-6" />
          Reference Data
        </h1>
        <p className="text-surface-500 dark:text-surface-400">MCC/MNC registry and PLMN profiles for multi-operator support</p>
      </div>

      <Tabs defaultValue="mcc-mnc" className="space-y-4">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="mcc-mnc"><Flag className="h-4 w-4 mr-2" />MCC/MNC Registry</TabsTrigger>
          <TabsTrigger value="plmn-profiles"><Network className="h-4 w-4 mr-2" />PLMN Profiles</TabsTrigger>
        </TabsList>
        <TabsContent value="mcc-mnc"><MccMncTab /></TabsContent>
        <TabsContent value="plmn-profiles"><PlmnProfileTab /></TabsContent>
      </Tabs>
    </div>
  )
}