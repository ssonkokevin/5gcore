import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { useDRALocal, useDRAPeerSets, useDRAPeers, useDRARoutes, useDRATranslates } from '@/api/queries'
import { DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Server, Network, Route, ArrowRightLeft } from 'lucide-react'
import { Card } from '@/components/ui/Card'

const DraLocalTab = () => {
  const { data } = useDRALocal()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">DRA Local Configuration</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Local</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Name</th><th className="table-head">Instance ID</th><th className="table-head">IP:Port</th>
            <th className="table-head">Realm</th><th className="table-head">Host</th><th className="table-head">Protocol</th>
            <th className="table-head">TLS</th><th className="table-head">Applications</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: DRALocal) => (
              <tr key={item.name} className="table-row">
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell font-mono text-sm">{item.instance_id}</td>
                <td className="table-cell font-mono">{item.ip}:{item.port}</td>
                <td className="table-cell">{item.realm}</td>
                <td className="table-cell">{item.host}</td>
                <td className="table-cell">{item.protocol}</td>
                <td className="table-cell">{item.tls_flag ? 'Yes' : 'No'}</td>
                <td className="table-cell font-mono text-sm">{item.application_ids}</td>
                <td className="table-cell"><div className="flex gap-2"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="h-4 w-4" /></Button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const DraPeerSetTab = () => {
  const { data } = useDRAPeerSets()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">DRA Peer Sets</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Peer Set</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Name</th><th className="table-head">Instance ID</th><th className="table-head">Mode</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: DRAPeerSet) => (
              <tr key={item.name} className="table-row">
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell font-mono text-sm">{item.instance_id}</td>
                <td className="table-cell">{item.mode}</td>
                <td className="table-cell"><div className="flex gap-2"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="h-4 w-4" /></Button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const DraPeerTab = () => {
  const { data } = useDRAPeers()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">DRA Peers</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Peer</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Name</th><th className="table-head">Local</th><th className="table-head">Peer Set</th>
            <th className="table-head">Remote IP:Port</th><th className="table-head">Remote Host/Realm</th><th className="table-head">Type</th>
            <th className="table-head">Priority</th><th className="table-head">Enabled</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: DRAPeer) => (
              <tr key={item.name} className="table-row">
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.local_name}</td>
                <td className="table-cell">{item.peer_set_name}</td>
                <td className="table-cell font-mono">{item.remote_ip}:{item.remote_port}</td>
                <td className="table-cell">{item.remote_host} / {item.remote_realm}</td>
                <td className="table-cell">{item.remote_type}</td>
                <td className="table-cell">{item.priority}</td>
                <td className="table-cell">{item.enable ? 'Yes' : 'No'}</td>
                <td className="table-cell"><div className="flex gap-2"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="h-4 w-4" /></Button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const DraRouteTab = () => {
  const { data } = useDRARoutes()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">DRA Routes</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Route</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Name</th><th className="table-head">Instance ID</th><th className="table-head">Origin Peer Set</th>
            <th className="table-head">Dest Peer Set</th><th className="table-head">IMSI Filter</th><th className="table-head">Priority</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: DRARoute) => (
              <tr key={item.name} className="table-row">
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell font-mono text-sm">{item.instance_id}</td>
                <td className="table-cell">{item.origin_peer_set_name}</td>
                <td className="table-cell">{item.dest_peer_set_name}</td>
                <td className="table-cell font-mono text-sm">{item.imsi || 'Any'}</td>
                <td className="table-cell">{item.priority}</td>
                <td className="table-cell"><div className="flex gap-2"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="h-4 w-4" /></Button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const DraTranslateTab = () => {
  const { data } = useDRATranslates()
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium">DRA Translations</h3>
        <Button variant="outline"><Plus className="h-4 w-4 mr-2" />Add Translation</Button>
      </div>
      <div className="table-container">
        <table className="table">
          <thead><tr className="table-header">
            <th className="table-head">Name</th><th className="table-head">Origin Peer Set</th><th className="table-head">Dest Peer Set</th>
            <th className="table-head">AVP Code</th><th className="table-head">AVP Type</th><th className="table-head">AVP Value</th>
            <th className="table-head">Command Code</th><th className="table-head">Actions</th>
          </tr></thead>
          <tbody>
            {data?.map((item: DRATranslate) => (
              <tr key={item.name} className="table-row">
                <td className="table-cell font-medium">{item.name}</td>
                <td className="table-cell">{item.origin_peer_set_name}</td>
                <td className="table-cell">{item.dest_peer_set_name}</td>
                <td className="table-cell">{item.avp_code}</td>
                <td className="table-cell">{item.avp_type}</td>
                <td className="table-cell font-mono text-sm">{item.avp_value}</td>
                <td className="table-cell">{item.command_code}</td>
                <td className="table-cell"><div className="flex gap-2"><Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="h-4 w-4" /></Button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function DRAManagement() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <Server className="h-6 w-6" />
          DRA Management
        </h1>
        <p className="text-surface-500 dark:text-surface-400">Diameter Routing Agent configuration and monitoring</p>
      </div>

      <Tabs defaultValue="local" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="local"><Server className="h-4 w-4 mr-2" />Local</TabsTrigger>
          <TabsTrigger value="peer-sets"><Network className="h-4 w-4 mr-2" />Peer Sets</TabsTrigger>
          <TabsTrigger value="peers"><Network className="h-4 w-4 mr-2" />Peers</TabsTrigger>
          <TabsTrigger value="routes"><Route className="h-4 w-4 mr-2" />Routes</TabsTrigger>
          <TabsTrigger value="translates"><ArrowRightLeft className="h-4 w-4 mr-2" />Translations</TabsTrigger>
        </TabsList>
        <TabsContent value="local"><DraLocalTab /></TabsContent>
        <TabsContent value="peer-sets"><DraPeerSetTab /></TabsContent>
        <TabsContent value="peers"><DraPeerTab /></TabsContent>
        <TabsContent value="routes"><DraRouteTab /></TabsContent>
        <TabsContent value="translates"><DraTranslateTab /></TabsContent>
      </Tabs>
    </div>
  )
}