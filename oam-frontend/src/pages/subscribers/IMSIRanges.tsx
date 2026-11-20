import { useState } from 'react'
import { useIMSIRanges, useCreateIMSIRange, useAllocateIMSI } from '@/api/queries'
import { IMSIRange, IMSIRangeCreate } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Plus, Edit, Trash2, Search, Hash, Copy, AlertCircle } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'
import { toast } from 'react-hot-toast'
import { clsx } from 'clsx'

export function IMSIRanges() {
  const [showModal, setShowModal] = useState(false)
  const [editingRange, setEditingRange] = useState<IMSIRange | null>(null)
  const [showAllocate, setShowAllocate] = useState(false)
  const [allocateRange, setAllocateRange] = useState<string>('')
  const [allocateCount, setAllocateCount] = useState(1)

  const { data: ranges, isLoading, refetch } = useIMSIRanges()
  const createMutation = useCreateIMSIRange()
  const allocateMutation = useAllocateIMSI()

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget as HTMLFormElement)
    const data: IMSIRangeCreate = {
      range_name: formData.get('range_name') as string,
      mcc: formData.get('mcc') as string,
      mnc: formData.get('mnc') as string,
      msisdn_prefix: formData.get('msisdn_prefix') as string || undefined,
      imsi_start: formData.get('imsi_start') as string,
      imsi_end: formData.get('imsi_end') as string,
      default_k: formData.get('default_k') as string || undefined,
      default_ki: formData.get('default_ki') as string || undefined,
      default_op: formData.get('default_op') as string || undefined,
      default_opc: formData.get('default_opc') as string || undefined,
      default_algorithm: formData.get('default_algorithm') as string || 'milenage',
      mvno_id: formData.get('mvno_id') as string || undefined,
    }
    createMutation.mutate(data, {
      onSuccess: () => {
        toast.success('IMSI range created')
        refetch()
        setShowModal(false)
        setEditingRange(null)
      },
      onError: () => toast.error('Failed to create IMSI range'),
    })
  }

  const handleAllocateSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    allocateMutation.mutate({ range_name: allocateRange, count: allocateCount }, {
      onSuccess: (result) => {
        toast.success(`Allocated ${result.count} IMSIs: ${result.allocated_imsis.join(', ')}`)
        refetch()
        setShowAllocate(false)
        setAllocateRange('')
        setAllocateCount(1)
      },
      onError: () => toast.error('Failed to allocate IMSIs'),
    })
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'available': return 'badge-success'
      case 'exhausted': return 'badge-error'
      case 'reserved': return 'badge-warning'
      default: return 'badge-gray'
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">IMSI Range Management</h1>
          <p className="text-surface-500 dark:text-surface-400">Manage IMSI ranges for subscriber allocation</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => { setAllocateRange(''); setShowAllocate(true); }}>
            <Hash className="h-4 w-4 mr-2" />
            Allocate IMSI
          </Button>
          <Button onClick={() => { setEditingRange(null); setShowModal(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Add Range
          </Button>
        </div>
      </div>

      <div className="card">
        {ranges && ranges.length === 0 ? (
          <div className="p-12 text-center">
            <Hash className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
            <p className="text-surface-500 dark:text-surface-400">No IMSI ranges configured</p>
            <Button variant="outline" className="mt-4" onClick={() => { setEditingRange(null); setShowModal(true); }}>
              Create First IMSI Range
            </Button>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr className="table-header">
                  <th className="table-head">Range Name</th>
                  <th className="table-head">MCC/MNC</th>
                  <th className="table-head">IMSI Range</th>
                  <th className="table-head">MSISDN Prefix</th>
                  <th className="table-head">Allocated / Total</th>
                  <th className="table-head">Utilization</th>
                  <th className="table-head">Status</th>
                  <th className="table-head">MVNO</th>
                  <th className="table-head">Default Keys</th>
                  <th className="table-head">Actions</th>
                </tr>
              </thead>
              <tbody>
                {ranges?.map((range) => {
                  const total = range.total_count || (Number(range.imsi_end) - Number(range.imsi_start) + 1)
                  const allocated = range.allocated_count
                  const utilization = total > 0 ? ((allocated / total) * 100).toFixed(1) : '0'
                  return (
                    <tr key={range.id} className="table-row">
                      <td className="table-cell font-medium">{range.range_name}</td>
                      <td className="table-cell font-mono">{range.mcc}-{range.mnc}</td>
                      <td className="table-cell font-mono text-sm">{range.imsi_start} - {range.imsi_end}</td>
                      <td className="table-cell font-mono">{range.msisdn_prefix || '—'}</td>
                      <td className="table-cell font-mono">{allocated} / {total}</td>
                      <td className="table-cell">
                        <div className="w-32 h-2 bg-surface-200 dark:bg-surface-700 rounded-full overflow-hidden">
                          <div
                            className={clsx(
                              'h-full rounded-full transition-all',
                              Number(utilization) > 90 ? 'bg-red-500' : Number(utilization) > 70 ? 'bg-yellow-500' : 'bg-green-500'
                            )}
                            style={{ width: `${utilization}%` }}
                          />
                        </div>
                      </td>
                      <td className="table-cell">
                        <span className={clsx('badge', getStatusBadge(range.status))}>{range.status}</span>
                      </td>
                      <td className="table-cell">{range.mvno_id || '—'}</td>
                      <td className="table-cell text-sm">
                        <div className="flex flex-wrap gap-1">
                          {range.default_k && <span className="badge badge-gray">K</span>}
                          {range.default_ki && <span className="badge badge-gray">Ki</span>}
                          {range.default_op && <span className="badge badge-gray">OP</span>}
                          {range.default_opc && <span className="badge badge-gray">OPc</span>}
                          {range.default_algorithm && <span className="badge badge-info">{range.default_algorithm}</span>}
                        </div>
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => { setEditingRange(range); setShowModal(true); }}
                            className="p-1.5 rounded hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                            title="Edit"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => { setAllocateRange(range.range_name); setShowAllocate(true); }}
                            className="p-1.5 rounded hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors text-primary-600"
                            title="Allocate from this range"
                          >
                            <Hash className="h-4 w-4" />
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
              <h3 className="text-lg font-semibold">{editingRange ? 'Edit' : 'Create'} IMSI Range</h3>
              <button onClick={() => { setShowModal(false); setEditingRange(null); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="range_name">Range Name *</Label>
                  <Input id="range_name" name="range_name" value={editingRange?.range_name || ''} required />
                </div>
                <div>
                  <Label htmlFor="mvno_id">MVNO ID (Optional)</Label>
                  <Input id="mvno_id" name="mvno_id" value={editingRange?.mvno_id || ''} />
                </div>
                <div>
                  <Label htmlFor="mcc">MCC *</Label>
                  <Input id="mcc" name="mcc" type="number" min={100} max={999} value={editingRange?.mcc || ''} required maxLength={3} />
                </div>
                <div>
                  <Label htmlFor="mnc">MNC *</Label>
                  <Input id="mnc" name="mnc" type="number" min={0} max={999} value={editingRange?.mnc || ''} required maxLength={3} />
                </div>
                <div>
                  <Label htmlFor="imsi_start">IMSI Start *</Label>
                  <Input id="imsi_start" name="imsi_start" value={editingRange?.imsi_start || ''} required className="font-mono" />
                </div>
                <div>
                  <Label htmlFor="imsi_end">IMSI End *</Label>
                  <Input id="imsi_end" name="imsi_end" value={editingRange?.imsi_end || ''} required className="font-mono" />
                </div>
                <div>
                  <Label htmlFor="msisdn_prefix">MSISDN Prefix</Label>
                  <Input id="msisdn_prefix" name="msisdn_prefix" value={editingRange?.msisdn_prefix || ''} placeholder="+2567" />
                </div>
                <div>
                  <Label htmlFor="default_algorithm">Default Algorithm</Label>
                  <Select
                    id="default_algorithm"
                    name="default_algorithm"
                    value={editingRange?.default_algorithm || 'milenage'}
                    options={[
                      { value: 'milenage', label: 'MILENAGE' },
                      { value: 'xor', label: 'XOR (Test)' },
                    ]}
                  />
                </div>
              </div>
              <div className="border-t border-surface-200 dark:border-surface-700 pt-4">
                <h4 className="text-sm font-medium text-surface-900 dark:text-surface-100 mb-3">Default Keys (Optional)</h4>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="md:col-span-2">
                    <Label htmlFor="default_k">Default K (256-bit hex)</Label>
                    <Input id="default_k" name="default_k" value={editingRange?.default_k || ''} className="font-mono text-sm" placeholder="For 5G subscribers without K" />
                  </div>
                  <div>
                    <Label htmlFor="default_ki">Default Ki (128-bit hex)</Label>
                    <Input id="default_ki" name="default_ki" value={editingRange?.default_ki || ''} className="font-mono text-sm" placeholder="For 4G/3G/2G subscribers without Ki" />
                  </div>
                  <div>
                    <Label htmlFor="default_op">Default OP (128-bit hex)</Label>
                    <Input id="default_op" name="default_op" value={editingRange?.default_op || ''} className="font-mono text-sm" />
                  </div>
                  <div>
                    <Label htmlFor="default_opc">Default OPc (128-bit hex)</Label>
                    <Input id="default_opc" name="default_opc" value={editingRange?.default_opc || ''} className="font-mono text-sm" />
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditingRange(null); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Saving...' : editingRange ? 'Update' : 'Create'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showAllocate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-md w-full">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Allocate IMSI</h3>
              <button onClick={() => { setShowAllocate(false); setAllocateRange(''); setAllocateCount(1); }} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleAllocateSubmit} className="p-6 space-y-4">
              <div>
                <Label htmlFor="allocate_range">Select Range *</Label>
                <Select
                  id="allocate_range"
                  name="range_name"
                  value={allocateRange}
                  onChange={(e) => setAllocateRange(e.target.value)}
                  required
                  options={ranges?.filter(r => r.status === 'available').map(r => ({ value: r.range_name, label: `${r.range_name} (${r.mcc}-${r.mnc})` })) || []}
                  placeholder="Choose an available range"
                />
              </div>
              <div>
                <Label htmlFor="allocate_count">Count *</Label>
                <Input
                  id="allocate_count"
                  type="number"
                  min={1}
                  max={1000}
                  value={String(allocateCount)}
                  onChange={(e) => setAllocateCount(Number(e.target.value))}
                  required
                />
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => { setShowAllocate(false); setAllocateRange(''); setAllocateCount(1); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={allocateMutation.isPending || !allocateRange}>
                  {allocateMutation.isPending ? 'Allocating...' : 'Allocate'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}