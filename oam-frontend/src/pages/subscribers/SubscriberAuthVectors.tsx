import { useState } from 'react'
import { AuthVector, AuthVectorGenerateRequest, AuthVectorResponse } from '@/types/api'
import { useAuthVector, useGenerateAuthVector } from '@/api/queries'
import { Button } from '@/components/ui/Button'
import { RefreshCw, Key, Copy, Download, Eye, EyeOff } from 'lucide-react'
import { Input, Label, Select } from '@/components/ui'
import { formatDate, downloadBlob } from '@/utils/format'
import { toast } from 'react-hot-toast'

interface SubscriberAuthVectorsProps {
  imsi: string
}

export function SubscriberAuthVectors({ imsi }: SubscriberAuthVectorsProps) {
  const [showGenerate, setShowGenerate] = useState(false)
  const [generateForm, setGenerateForm] = useState<AuthVectorGenerateRequest>({
    algorithm: 'milenage',
    count: 5,
  })
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})

  const { data: authVector, isLoading, refetch } = useAuthVector(imsi)
  const generateMutation = useGenerateAuthVector(imsi)

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault()
    generateMutation.mutate(generateForm, {
      onSuccess: (response: AuthVectorResponse) => {
        toast.success(`Generated ${response.vectors.length} auth vectors`)
        refetch()
        setShowGenerate(false)
      },
      onError: () => {
        toast.error('Failed to generate auth vectors')
      },
    })
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${label} copied to clipboard`)
  }

  const downloadVectors = () => {
    if (!authVector) return
    const csv = [
      'Field,Value',
      `IMSI,${authVector.imsi}`,
      `Algorithm,${authVector.algorithm}`,
      `Generated,${formatDate(authVector.generated_at)}`,
      `Expires,${authVector.expires_at ? formatDate(authVector.expires_at) : 'N/A'}`,
      `OPc Used,${authVector.opc_used || 'N/A'}`,
      `SQN Used,${authVector.sqn_used || 'N/A'}`,
      '',
      '5G Vectors',
      `RAND_5G,${authVector.rand_5g || 'N/A'}`,
      `AUTN_5G,${authVector.autn_5g || 'N/A'}`,
      `XRES*_5G,${authVector.xres_5g || 'N/A'}`,
      `K_AUSF,${authVector.k_ausf || 'N/A'}`,
      `K_SEAF,${authVector.k_seaf || 'N/A'}`,
      `K_AMF,${authVector.k_amf || 'N/A'}`,
      '',
      '4G Vectors',
      `RAND_4G,${authVector.rand_4g || 'N/A'}`,
      `AUTN_4G,${authVector.autn_4g || 'N/A'}`,
      `XRES_4G,${authVector.xres_4g || 'N/A'}`,
      `CK_4G,${authVector.ck_4g || 'N/A'}`,
      `IK_4G,${authVector.ik_4g || 'N/A'}`,
      `K_ASME_4G,${authVector.k_asme_4g || 'N/A'}`,
      '',
      '3G Vectors',
      `RAND_3G,${authVector.rand_3g || 'N/A'}`,
      `AUTN_3G,${authVector.autn_3g || 'N/A'}`,
      `XRES_3G,${authVector.xres_3g || 'N/A'}`,
      `CK_3G,${authVector.ck_3g || 'N/A'}`,
      `IK_3G,${authVector.ik_3g || 'N/A'}`,
      '',
      '2G Vectors',
      `RAND_2G,${authVector.rand_2g || 'N/A'}`,
      `SRES_2G,${authVector.sres_2g || 'N/A'}`,
      `Kc_2G,${authVector.kc_2g || 'N/A'}`,
    ].join('\n')
    downloadBlob(new Blob([csv], { type: 'text/csv' }), `auth-vectors-${imsi}-${Date.now()}.csv`)
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
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 flex items-center gap-2">
          <Key className="h-5 w-5" />
          Authentication Vectors
        </h3>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={() => setShowGenerate(true)}>
            <Key className="h-4 w-4 mr-2" />
            Generate Vectors
          </Button>
        </div>
      </div>

      {authVector ? (
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-800/50">
            <div className="grid gap-4 md:grid-cols-4 text-sm">
              <div>
                <dt className="text-surface-500 dark:text-surface-400">Algorithm</dt>
                <dd className="font-medium">{authVector.algorithm.toUpperCase()}</dd>
              </div>
              <div>
                <dt className="text-surface-500 dark:text-surface-400">Generated</dt>
                <dd className="font-medium">{formatDate(authVector.generated_at)}</dd>
              </div>
              <div>
                <dt className="text-surface-500 dark:text-surface-400">Expires</dt>
                <dd className="font-medium">{authVector.expires_at ? formatDate(authVector.expires_at) : 'N/A'}</dd>
              </div>
              <div>
                <dt className="text-surface-500 dark:text-surface-400">SQN Used</dt>
                <dd className="font-mono font-medium">{authVector.sqn_used?.toString() || 'N/A'}</dd>
              </div>
            </div>
          </div>

          <div className="p-6 space-y-6">
            <div>
              <h4 className="text-sm font-medium text-surface-900 dark:text-surface-100 mb-3 flex items-center gap-2">
                <span className="badge badge-info">5G (TS 33.501)</span>
              </h4>
              <div className="grid gap-3 md:grid-cols-2">
                {[
                  { label: 'RAND', value: authVector.rand_5g, key: 'rand_5g' },
                  { label: 'AUTN', value: authVector.autn_5g, key: 'autn_5g' },
                  { label: 'XRES*', value: authVector.xres_5g, key: 'xres_5g' },
                  { label: 'K_AUSF', value: authVector.k_ausf, key: 'k_ausf' },
                  { label: 'K_SEAF', value: authVector.k_seaf, key: 'k_seaf' },
                  { label: 'K_AMF', value: authVector.k_amf, key: 'k_amf' },
                ].map((item) => (
                  <div key={item.key} className="p-3 bg-surface-50 dark:bg-surface-800/50 rounded-lg">
                    <dt className="text-xs text-surface-500 dark:text-surface-400">{item.label}</dt>
                    <dd className="flex items-center gap-2 font-mono text-sm break-all">
                      <span>{showValues[item.key] ? item.value : '••••••••••••••••'}</span>
                      <button
                        onClick={() => setShowValues(prev => ({ ...prev, [item.key]: !prev[item.key] }))}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                        aria-label={showValues[item.key] ? 'Hide' : 'Show'}
                      >
                        {showValues[item.key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => copyToClipboard(item.value || '', item.label)}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                        aria-label={`Copy ${item.label}`}
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </dd>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-medium text-surface-900 dark:text-surface-100 mb-3 flex items-center gap-2">
                <span className="badge badge-success">4G (TS 33.401)</span>
              </h4>
              <div className="grid gap-3 md:grid-cols-2">
                {[
                  { label: 'RAND', value: authVector.rand_4g, key: 'rand_4g' },
                  { label: 'AUTN', value: authVector.autn_4g, key: 'autn_4g' },
                  { label: 'XRES', value: authVector.xres_4g, key: 'xres_4g' },
                  { label: 'CK', value: authVector.ck_4g, key: 'ck_4g' },
                  { label: 'IK', value: authVector.ik_4g, key: 'ik_4g' },
                  { label: 'K_ASME', value: authVector.k_asme_4g, key: 'k_asme_4g' },
                ].map((item) => (
                  <div key={item.key} className="p-3 bg-surface-50 dark:bg-surface-800/50 rounded-lg">
                    <dt className="text-xs text-surface-500 dark:text-surface-400">{item.label}</dt>
                    <dd className="flex items-center gap-2 font-mono text-sm break-all">
                      <span>{showValues[item.key] ? item.value : '••••••••••••••••'}</span>
                      <button
                        onClick={() => setShowValues(prev => ({ ...prev, [item.key]: !prev[item.key] }))}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                      >
                        {showValues[item.key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => copyToClipboard(item.value || '', item.label)}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </dd>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-medium text-surface-900 dark:text-surface-100 mb-3 flex items-center gap-2">
                <span className="badge badge-warning">3G (TS 33.102)</span>
              </h4>
              <div className="grid gap-3 md:grid-cols-2">
                {[
                  { label: 'RAND', value: authVector.rand_3g, key: 'rand_3g' },
                  { label: 'AUTN', value: authVector.autn_3g, key: 'autn_3g' },
                  { label: 'XRES', value: authVector.xres_3g, key: 'xres_3g' },
                  { label: 'CK', value: authVector.ck_3g, key: 'ck_3g' },
                  { label: 'IK', value: authVector.ik_3g, key: 'ik_3g' },
                ].map((item) => (
                  <div key={item.key} className="p-3 bg-surface-50 dark:bg-surface-800/50 rounded-lg">
                    <dt className="text-xs text-surface-500 dark:text-surface-400">{item.label}</dt>
                    <dd className="flex items-center gap-2 font-mono text-sm break-all">
                      <span>{showValues[item.key] ? item.value : '••••••••••••••••'}</span>
                      <button
                        onClick={() => setShowValues(prev => ({ ...prev, [item.key]: !prev[item.key] }))}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                      >
                        {showValues[item.key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => copyToClipboard(item.value || '', item.label)}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </dd>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-medium text-surface-900 dark:text-surface-100 mb-3 flex items-center gap-2">
                <span className="badge badge-gray">2G (TS 33.102)</span>
              </h4>
              <div className="grid gap-3 md:grid-cols-2">
                {[
                  { label: 'RAND', value: authVector.rand_2g, key: 'rand_2g' },
                  { label: 'SRES', value: authVector.sres_2g, key: 'sres_2g' },
                  { label: 'Kc', value: authVector.kc_2g, key: 'kc_2g' },
                ].map((item) => (
                  <div key={item.key} className="p-3 bg-surface-50 dark:bg-surface-800/50 rounded-lg">
                    <dt className="text-xs text-surface-500 dark:text-surface-400">{item.label}</dt>
                    <dd className="flex items-center gap-2 font-mono text-sm break-all">
                      <span>{showValues[item.key] ? item.value : '••••••••••••••••'}</span>
                      <button
                        onClick={() => setShowValues(prev => ({ ...prev, [item.key]: !prev[item.key] }))}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                      >
                        {showValues[item.key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => copyToClipboard(item.value || '', item.label)}
                        className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </dd>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="p-4 border-t border-surface-200 dark:border-surface-700 flex justify-end">
            <Button variant="outline" onClick={downloadVectors}>
              <Download className="h-4 w-4 mr-2" />
              Download CSV
            </Button>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Key className="h-12 w-12 mx-auto text-surface-300 dark:text-surface-600 mb-4" />
          <p className="text-surface-500 dark:text-surface-400">No authentication vectors generated yet</p>
          <Button className="mt-4" onClick={() => setShowGenerate(true)}>
            Generate First Vectors
          </Button>
        </div>
      )}

      {showGenerate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-surface-800 rounded-xl shadow-xl max-w-md w-full">
            <div className="p-6 border-b border-surface-200 dark:border-surface-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Generate Authentication Vectors</h3>
              <button onClick={() => setShowGenerate(false)} className="p-1 hover:bg-surface-100 dark:hover:bg-surface-700 rounded">✕</button>
            </div>
            <form onSubmit={handleGenerate} className="p-6 space-y-4">
              <div>
                <Label htmlFor="algorithm">Algorithm</Label>
                <Select
                  id="algorithm"
                  value={generateForm.algorithm}
                  onChange={(e) => setGenerateForm(prev => ({ ...prev, algorithm: e.target.value }))}
                  options={[
                    { value: 'milenage', label: 'MILENAGE (3GPP Standard)' },
                    { value: 'xor', label: 'XOR (Test Only)' },
                  ]}
                />
              </div>
              <div>
                <Label htmlFor="count">Number of Vectors</Label>
                <Input
                  id="count"
                  type="number"
                  min={1}
                  max={100}
                  value={String(generateForm.count)}
                  onChange={(e) => setGenerateForm(prev => ({ ...prev, count: Number(e.target.value) }))}
                />
              </div>
              <div>
                <Label htmlFor="rand">RAND (Optional - 32 hex chars)</Label>
                <Input
                  id="rand"
                  value={generateForm.rand || ''}
                  onChange={(e) => setGenerateForm(prev => ({ ...prev, rand: e.target.value }))}
                  placeholder="Auto-generated if empty"
                  maxLength={32}
                />
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t border-surface-200 dark:border-surface-700">
                <Button type="button" variant="secondary" onClick={() => setShowGenerate(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={generateMutation.isPending}>
                  {generateMutation.isPending ? 'Generating...' : 'Generate'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}