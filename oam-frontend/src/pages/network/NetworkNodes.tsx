import { useState } from 'react'
import { useNetworkNodes, useCreateNetworkNode } from '@/api/queries'
import { NetworkNode, NetworkNodeCreate } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Server, Wifi, Globe, Database, Shield, AlertTriangle } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'
import { toast } from 'react-hot-toast'
import { clsx } from 'clsx'

const nodeTypeIcons: Record<string, any> = {
  MME: Server, MSC: Server, SGSN: Server, PGW: Database, SGW: Database,
  HSS: Database, PCRF: Shield, PCF: Shield, SMF: Shield, UPF: Wifi,
  AMF: Server, GMLC: Globe, SCP: Shield, USSD_GW: Globe, SMSC: Globe,
  NRF: Server, AUSF: Shield, UDM: Server, NEF: Globe, BSF: Shield,
  UDSF: Database, NSSF: Shield,
}

export function NetworkNodes() {
  const [showModal, setShowModal] = useState(false)
  const [editingNode, setEditingNode] = useState<NetworkNode | null>(null)
  const [filterType, setFilterType] = useState<string>('')

  const { data: nodes, refetch } = useNetworkNodes({ node_type: filterType || undefined })
  const createMutation = useCreateNetworkNode()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget as HTMLFormElement)
    const data: NetworkNodeCreate = {
      node_name: formData.get('node_name') as string,
      node_type: formData.get('node_type') as string,
      fqdn: formData.get('fqdn') as string || undefined,
      ipv4: formData.get('ipv4') as string || undefined,
      ipv6: formData.get('ipv6') as string || undefined,
      diameter_host: formData.get('diameter_host') as string || undefined,
      diameter_realm: formData.get('diameter_realm') as string || undefined,
      diameter_port: Number(formData.get('diameter_port')) || 3868,
      sctp_port: Number(formData.get('sctp_port')) || 2905,
      point_code: formData.get('point_code') as string || undefined,
      global_title: formData.get('global_title') as string || undefined,
      gt_translation_type: Number(formData.get('gt_translation_type')) || 0,
      gt_numbering_plan: Number(formData.get('gt_numbering_plan')) || 1,
      gt_nature_of_address: Number(formData.get('gt_nature_of_address')) || 4,
      plmn_id: formData.get('plmn_id') as string || undefined,
      supported_interfaces: formData.get('supported_interfaces') ? JSON.parse(formData.get('supported_interfaces') as string) : undefined,
      is_active: true,
      health_check_url: formData.get('health_check_url') as string || undefined,
    }
    createMutation.mutate(data, {
      onSuccess: () => { toast.success('Network node created'); refetch(); setShowModal(false); setEditingNode(null); },
      onError: () => toast.error('Failed to create network node'),
    })
  }

  const nodeTypes = [
    'MME', 'MSC', 'SGSN', 'PGW', 'SGW', 'HSS', 'PCRF', 'PCF', 'SMF', 'UPF',
    'AMF', 'GMLC', 'SCP', 'USSD_GW', 'SMSC', 'NRF', 'AUSF', 'UDM', 'NEF', 'BSF', 'UDSF', 'NSSF'
  ]

  if (nodes === undefined) {
    return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">Network Nodes</h1>
          <p className="text-surface-500 dark:text-surface-400">Manage network element registry for interworking</p>
        </div>
        <Button onClick={() => { setEditingNode(null); setShowModal(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add Network Node
        </Button>
      </div>

      <div className="card p-4">
        <Label htmlFor="node_type_filter">Filter by Type</Label>
        <Select
          id="node_type_filter"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          options={[{ value: '', label: 'All Types' }, ...nodeTypes.map(t => ({ value: t, label: t }))]}
          placeholder="All Types"
        />
      </div>

      <div className="card">
        {nodes.length === 0 ? (
          <div className="p-12 text-center">
            <Server className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
            <p className="text-surface-500 dark:text-surface-400">No network nodes configured</p>
            <Button variant="outline" className="mt-4" onClick={() => { setEditingNode(null); setShowModal(true); }}>
              Add First Network Node
            </Button>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr className="table-header">
                  <th className="table-head">Node Name</th>
                  <th className="table-head">Type</th>
                  <th className="table-head">FQDN / IP</th>
                  <th className="table-head">Diameter</th>
                  <th className="table-head">SCCP/SS7</th>
                  <th className="table-head">PLMN</th>
                  <th className="table-head">Interfaces</th>
                  <th className="table-head">Health</th>
                  <th className="table-head">Status</th>
                  <th className="table-head">Actions</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => {
                  const Icon = nodeTypeIcons[node.node_type] || Server
                  return (
                    <tr key={node.id} className="table-row">
                      <td className="table-cell font-medium">{node.node_name}</td>
                      <td className="table-cell">
                        <span className="flex items-center gap-1 badge badge-info">
                          <Icon className="h-3 w-3" />
                          {node.node_type}
                        </span>
                      </td>
                      <td className="table-cell">
                        <div className="text-sm">
                          {node.fqdn && <div className="font-mono">{node.fqdn}</div>}
                          {node.ipv4 && <div className="font-mono text-surface-500">{node.ipv4}</div>}
                          {node.ipv6 && <div className="font-mono text-surface-500">{node.ipv6}</div>}
                        </div>
                      </td>
                      <td className="table-cell text-sm">
                        {node.diameter_host && <div className="font-mono">{node.diameter_host}</div>}
                        {node.diameter_realm && <div className="text-surface-500">{node.diameter_realm}</div>}
                        <div className="font-mono">{node.diameter_port}</div>
                      </td>
                      <td className="table-cell text-sm">
                        {node.point_code && <div className="font-mono">PC: {node.point_code}</div>}
                        {node.global_title && <div className="font-mono">GT: {node.global_title}</div>}
                        <div className="font-mono">SCCP: {node.sctp_port}</div>
                      </td>
                      <td className="table-cell font-mono">{node.plmn_id || '—'}</td>
                      <td className="table-cell">
                        {node.supported_interfaces && (
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(node.supported_interfaces).map(([k, v]) => (
                              <span key={k} className="badge badge-gray text-xs">{k}: {String(v)}</span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="table-cell">
                        {node.health_check_url ? (
                          <span className="badge badge-success">Configured</span>
                        ) : (
                          <span className="badge badge-gray">No Check</span>
                        )}
                      </td>
                      <td className="table-cell">
                        <span className={`badge ${node.is_active ? 'badge-success' : 'badge-error'}`}>
                          {node.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="sm" onClick={() => { setEditingNode(node); setShowModal(true); }}><Edit className="h-4 w-4" /></Button>
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
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-auto">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{editingNode ? 'Edit' : 'Add'} Network Node</h3>
              <button onClick={() => { setShowModal(false); setEditingNode(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="node_name">Node Name *</Label>
                  <Input id="node_name" name="node_name" value={editingNode?.node_name || ''} required disabled={!!editingNode} />
                </div>
                <div>
                  <Label htmlFor="node_type">Node Type *</Label>
                  <Select
                    id="node_type"
                    name="node_type"
                    value={editingNode?.node_type || ''}
                    required
                    disabled={!!editingNode}
                    options={nodeTypes.map(t => ({ value: t, label: t }))}
                    placeholder="Select node type"
                  />
                </div>
                <div>
                  <Label htmlFor="fqdn">FQDN</Label>
                  <Input id="fqdn" name="fqdn" value={editingNode?.fqdn || ''} placeholder="node.example.com" />
                </div>
                <div>
                  <Label htmlFor="plmn_id">PLMN ID (MCC+MNC)</Label>
                  <Input id="plmn_id" name="plmn_id" value={editingNode?.plmn_id || ''} placeholder="64108" maxLength={6} />
                </div>
                <div>
                  <Label htmlFor="ipv4">IPv4 Address</Label>
                  <Input id="ipv4" name="ipv4" value={editingNode?.ipv4 || ''} placeholder="192.168.1.10" />
                </div>
                <div>
                  <Label htmlFor="ipv6">IPv6 Address</Label>
                  <Input id="ipv6" name="ipv6" value={editingNode?.ipv6 || ''} placeholder="2001:db8::1" />
                </div>
              </div>
              <div className="border-t border-surface-200 dark:border-surface-700 pt-4">
                <h4 className="text-sm font-medium mb-3">Diameter Configuration</h4>
                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <Label htmlFor="diameter_host">Diameter Host</Label>
                    <Input id="diameter_host" name="diameter_host" value={editingNode?.diameter_host || ''} />
                  </div>
                  <div>
                    <Label htmlFor="diameter_realm">Diameter Realm</Label>
                    <Input id="diameter_realm" name="diameter_realm" value={editingNode?.diameter_realm || ''} />
                  </div>
                  <div>
                    <Label htmlFor="diameter_port">Diameter Port</Label>
                    <Input id="diameter_port" name="diameter_port" type="number" value={String(editingNode?.diameter_port || 3868)} />
                  </div>
                </div>
              </div>
              <div className="border-t border-surface-200 dark:border-surface-700 pt-4">
                <h4 className="text-sm font-medium mb-3">SCCP/SS7 Configuration</h4>
                <div className="grid gap-4 md:grid-cols-4">
                  <div>
                    <Label htmlFor="sctp_port">SCCP Port</Label>
                    <Input id="sctp_port" name="sctp_port" type="number" value={String(editingNode?.sctp_port || 2905)} />
                  </div>
                  <div>
                    <Label htmlFor="point_code">Point Code</Label>
                    <Input id="point_code" name="point_code" value={editingNode?.point_code || ''} placeholder="1.2.3" />
                  </div>
                  <div>
                    <Label htmlFor="global_title">Global Title</Label>
                    <Input id="global_title" name="global_title" value={editingNode?.global_title || ''} />
                  </div>
                  <div>
                    <Label htmlFor="gt_translation_type">GT Translation Type</Label>
                    <Input id="gt_translation_type" name="gt_translation_type" type="number" value={String(editingNode?.gt_translation_type || 0)} />
                  </div>
                  <div>
                    <Label htmlFor="gt_numbering_plan">GT Numbering Plan</Label>
                    <Input id="gt_numbering_plan" name="gt_numbering_plan" type="number" value={String(editingNode?.gt_numbering_plan || 1)} />
                  </div>
                  <div>
                    <Label htmlFor="gt_nature_of_address">GT Nature of Address</Label>
                    <Input id="gt_nature_of_address" name="gt_nature_of_address" type="number" value={String(editingNode?.gt_nature_of_address || 4)} />
                  </div>
                </div>
              </div>
              <div className="border-t border-surface-200 dark:border-surface-700 pt-4">
                <h4 className="text-sm font-medium mb-3">Health Check</h4>
                <div>
                  <Label htmlFor="health_check_url">Health Check URL</Label>
                  <Input id="health_check_url" name="health_check_url" value={editingNode?.health_check_url || ''} placeholder="http://node:8080/health" />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditingNode(null); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Saving...' : editingNode ? 'Update' : 'Create'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}