import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { useM3UAGlobal, useM3UALocal, useM3UALinksets, useM3UALinks, useSTPRoutes, useSTPTranslates } from '@/api/queries'
import { M3UAGlobal, M3UALocal, M3UALinkset, M3UALink, STPRoute, STPTranslate } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Server, GitBranch, Link as LinkIcon, Wifi, Route } from 'lucide-react'

const StpGlobalTab = () => {
  const { data } = useM3UAGlobal()
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium">M3UA Global Configuration</h3>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Instance</th><th className="table-head">Name</th><th className="table-head">Audit Interval</th>
            <th className="table-head">HB Interval</th><th className="table-head">Max Streams</th><th className="table-head">Congestion</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: M3UAGlobal) => (
              <tr key={item.instance_id} className="table-row">
                <td className="table-cell font-mono">{item.instance_id}</td>
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.audit_interval}ms</td>
                <td className="table-cell">{item.hb_interval}ms</td>
                <td className="table-cell">{item.max_ingress_streams}/{item.num_egress_streams}</td>
                <td className="table-cell text-sm">L1:{item.cong_onset_level1}/{item.cong_abatement_level1} L2:{item.cong_onset_level2}/{item.cong_abatement_level2} L3:{item.cong_onset_level3}/{item.cong_abatement_level3}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const StpLocalTab = () => {
  const { data } = useM3UALocal()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">M3UA Local Instances</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Local</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Instance</th><th className="table-head">Name</th><th className="table-head">Point Code</th>
            <th className="table-head">PC Length</th><th className="table-head">Network Indicator</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: M3UALocal) => (
              <tr key={item.instance_id + item.name} className="table-row">
                <td className="table-cell font-mono">{item.instance_id}</td>
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell font-mono">{item.local_point_code}</td>
                <td className="table-cell">{item.point_code_length}</td>
                <td className="table-cell">{item.network_indicator}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const StpLinksetTab = () => {
  const { data } = useM3UALinksets()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">M3UA Linksets</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Linkset</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Instance</th><th className="table-head">Name</th><th className="table-head">Local</th>
            <th className="table-head">Adjacent PC</th><th className="table-head">Traffic Mode</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: M3UALinkset) => (
              <tr key={item.instance_id + item.name} className="table-row">
                <td className="table-cell font-mono">{item.instance_id}</td>
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.m3ua_local}</td>
                <td className="table-cell font-mono">{item.adjacent_point_code}</td>
                <td className="table-cell">{item.traffic_mode}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const StpLinkTab = () => {
  const { data } = useM3UALinks()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">M3UA Links</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Link</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Instance</th><th className="table-head">Name</th><th className="table-head">Linkset</th>
            <th className="table-head">Local IP:Port</th><th className="table-head">Remote IP:Port</th>
            <th className="table-head">Type</th><th className="table-head">Status</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: M3UALink) => (
              <tr key={item.instance_id + item.name} className="table-row">
                <td className="table-cell font-mono">{item.instance_id}</td>
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.linkset_name}</td>
                <td className="table-cell font-mono">{item.local_ip_addr}:{item.local_port}</td>
                <td className="table-cell font-mono">{item.remote_ip_addr}:{item.remote_port}</td>
                <td className="table-cell">{item.link_type}</td>
                <td className="table-cell">
                  <span className={`badge ${item.link_status === 'activated' ? 'badge-success' : item.link_status === 'activating' ? 'badge-warning' : 'badge-error'}`}>
                    {item.link_status}
                  </span>
                </td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const StpRouteTab = () => {
  const { data } = useSTPRoutes()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">STP Routes</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Route</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Instance</th><th className="table-head">Name</th><th className="table-head">Enabled</th>
            <th className="table-head">Priority</th><th className="table-head">Ingress Linkset</th><th className="table-head">Egress Linkset</th>
            <th className="table-head">Calling GT</th><th className="table-head">Called GT</th><th className="table-head">IMSI Filter</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: STPRoute) => (
              <tr key={item.instance_id + item.name} className="table-row">
                <td className="table-cell font-mono">{item.instance_id}</td>
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.enable ? 'Yes' : 'No'}</td>
                <td className="table-cell">{item.priority}</td>
                <td className="table-cell">{item.linkset_ingress || 'Any'}</td>
                <td className="table-cell">{item.linkset_egress || 'Any'}</td>
                <td className="table-cell font-mono">{item.calling_gt || 'Any'}</td>
                <td className="table-cell font-mono">{item.called_gt || 'Any'}</td>
                <td className="table-cell font-mono text-sm">{item.imsi ? item.imsi.substring(0, 30) + '...' : 'Any'}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const StpTranslateTab = () => {
  const { data } = useSTPTranslates()
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium">STP Translations</h3>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">TID</th><th className="table-head">Instance</th><th className="table-head">Name</th>
            <th className="table-head">SPC Rule</th><th className="table-head">DPC Rule</th><th className="table-head">Calling Rule</th>
            <th className="table-head">Called Rule</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: STPTranslate) => (
              <tr key={item.tid} className="table-row">
                <td className="table-cell">{item.tid}</td>
                <td className="table-cell font-mono">{item.instance_id}</td>
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.spc_rule}</td>
                <td className="table-cell">{item.dpc}</td>
                <td className="table-cell">{item.calling_rule}</td>
                <td className="table-cell">{item.called_rule}</td>
                <td className="table-cell"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function STPManagement() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <GitBranch className="h-6 w-6" />
          STP Management
        </h1>
        <p className="text-surface-500 dark:text-surface-400">Signaling Transfer Point (M3UA/SCCP) configuration and monitoring</p>
      </div>

      <Tabs defaultValue="global" className="space-y-4">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="global"><Server className="h-4 w-4 mr-2" />Global</TabsTrigger>
          <TabsTrigger value="local"><Server className="h-4 w-4 mr-2" />Local</TabsTrigger>
          <TabsTrigger value="linksets"><LinkIcon className="h-4 w-4 mr-2" />Linksets</TabsTrigger>
          <TabsTrigger value="links"><Wifi className="h-4 w-4 mr-2" />Links</TabsTrigger>
          <TabsTrigger value="routes"><Route className="h-4 w-4 mr-2" />Routes</TabsTrigger>
          <TabsTrigger value="translates"><GitBranch className="h-4 w-4 mr-2" />Translations</TabsTrigger>
        </TabsList>
        <TabsContent value="global"><StpGlobalTab /></TabsContent>
        <TabsContent value="local"><StpLocalTab /></TabsContent>
        <TabsContent value="linksets"><StpLinksetTab /></TabsContent>
        <TabsContent value="links"><StpLinkTab /></TabsContent>
        <TabsContent value="routes"><StpRouteTab /></TabsContent>
        <TabsContent value="translates"><StpTranslateTab /></TabsContent>
      </Tabs>
    </div>
  )
}