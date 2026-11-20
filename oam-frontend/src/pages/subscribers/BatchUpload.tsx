import { useState, useRef } from 'react'
import { useBatchUpload } from '@/api/queries'
import type { BatchUpload } from '@/types/api'
import { Button } from '@/components/ui/Button'
import { Upload, FileText, AlertCircle, CheckCircle, Loader2, Download } from 'lucide-react'
import { Input, Label } from '@/components/ui'
import { toast } from 'react-hot-toast'
import { clsx } from 'clsx'
import Papa from 'papaparse'

interface BatchUploadFormData {
  file: File | null
  batch_id: string
  auto_derive: boolean
  default_ki: string
  default_op: string
  default_k: string
  default_network_access_mode: number
  default_subscriber_status: number
}

export function BatchUpload() {
  const [formData, setFormData] = useState<BatchUploadFormData>({
    file: null,
    batch_id: '',
    auto_derive: true,
    default_ki: '',
    default_op: '',
    default_k: '',
    default_network_access_mode: 2,
    default_subscriber_status: 0,
  })
  const [previewData, setPreviewData] = useState<any[]>([])
  const [showPreview, setShowPreview] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const uploadMutation = useBatchUpload()

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0])
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0])
    }
  }

  const handleFile = (file: File) => {
    setFormData(prev => ({ ...prev, file }))
    parseFile(file)
  }

  const parseFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      if (file.name.endsWith('.csv')) {
        Papa.parse(content, {
          header: true,
          skipEmptyLines: true,
          complete: (results) => {
            setPreviewData(results.data.slice(0, 10))
            setShowPreview(true)
          },
        })
      } else if (file.name.endsWith('.json')) {
        try {
          const data = JSON.parse(content)
          const arr = Array.isArray(data) ? data : [data]
          setPreviewData(arr.slice(0, 10))
          setShowPreview(true)
        } catch {
          toast.error('Invalid JSON file')
        }
      }
    }
    reader.readAsText(file)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.file) {
      toast.error('Please select a file')
      return
    }
    const requestData = {
      file: formData.file,
      batch_id: formData.batch_id,
      auto_derive: formData.auto_derive,
      default_ki: formData.default_ki,
      default_op: formData.default_op,
      default_k: formData.default_k,
      default_network_access_mode: formData.default_network_access_mode,
      default_subscriber_status: formData.default_subscriber_status,
    }
    uploadMutation.mutate(requestData, {
      onSuccess: (result: BatchUpload) => {
        toast.success(`Batch upload started: ${result.batch_id}`)
        setFormData(prev => ({ ...prev, file: null, batch_id: '' }))
        setPreviewData([])
        setShowPreview(false)
      },
      onError: () => {
        toast.error('Batch upload failed')
      },
    })
  }

  const downloadTemplate = () => {
    const csv = `imsi,msisdn,imei,k,ki,op,opc,sqn,amf,network_access_mode,subscriber_status,ambr_ul,ambr_dl
641080000000001,256700000001,351234567890123,,1234567890ABCDEF1234567890ABCDEF,,0,8000,2,0,100000000,1000000000
641080000000002,256700000002,351234567890124,,FEDCBA0987654321FEDCBA0987654321,,0,8000,2,0,100000000,1000000000
641080000000003,256700000003,351234567890125,,11111111111111111111111111111111,,0,8000,2,0,100000000,1000000000`
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'subscriber-template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">Batch Subscriber Upload</h1>
          <p className="text-surface-500 dark:text-surface-400">Upload CSV/JSON file to provision multiple subscribers at once</p>
        </div>
        <Button variant="outline" onClick={downloadTemplate}>
          <Download className="h-4 w-4 mr-2" />
          Download Template
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="card p-6 space-y-6">
        <div
          className={clsx(
            'border-2 border-dashed rounded-xl p-8 text-center transition-colors',
            dragActive ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-surface-300 dark:border-surface-600'
          )}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            onChange={handleFileChange}
            className="hidden"
            id="batch-file"
          />
          <label htmlFor="batch-file" className="cursor-pointer">
            <div className="flex flex-col items-center gap-4">
              <Upload className="h-12 w-12 text-surface-400 dark:text-surface-500" />
              <div>
                <p className="text-lg font-medium text-surface-900 dark:text-surface-100">
                  Drag & drop CSV or JSON file here, or click to browse
                </p>
                <p className="text-sm text-surface-500 dark:text-surface-400">
                  Max 100,000 records per batch. Required columns: imsi
                </p>
              </div>
              {formData.file && (
                <div className="flex items-center gap-3 px-4 py-2 bg-surface-100 dark:bg-surface-800 rounded-lg w-full max-w-md">
                  <FileText className="h-5 w-5 text-primary-600 dark:text-primary-400" />
                  <span className="flex-1 text-left font-mono text-sm truncate">{formData.file.name}</span>
                  <span className="text-sm text-surface-500 dark:text-surface-400">
                    {(formData.file.size / 1024).toFixed(1)} KB
                  </span>
                  <button
                    type="button"
                    onClick={() => { setFormData(prev => ({ ...prev, file: null })); setPreviewData([]); setShowPreview(false); }}
                    className="text-surface-400 hover:text-red-600"
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="batch_id">Batch ID (Optional)</Label>
            <Input
              id="batch_id"
              value={formData.batch_id}
              onChange={(e) => setFormData(prev => ({ ...prev, batch_id: e.target.value }))}
              placeholder="Auto-generated if empty"
            />
          </div>
          <div className="flex items-center gap-2">
            <Input
              type="checkbox"
              id="auto_derive"
              checked={formData.auto_derive}
              onChange={(e) => setFormData(prev => ({ ...prev, auto_derive: e.target.checked }))}
            />
            <Label htmlFor="auto_derive" className="mb-0">Auto-derive OPc/5G keys from K/Ki</Label>
          </div>
          <div>
            <Label htmlFor="default_network_access_mode">Default Network Access Mode</Label>
            <Input
              id="default_network_access_mode"
              type="select"
              value={String(formData.default_network_access_mode)}
              onChange={(e) => setFormData(prev => ({ ...prev, default_network_access_mode: Number(e.target.value) }))}
            >
              <option value="0">GPRS Only</option>
              <option value="1">CS Only</option>
              <option value="2">GPRS + CS</option>
              <option value="3">5G Only</option>
              <option value="4">5G + EPC</option>
            </Input>
          </div>
          <div>
            <Label htmlFor="default_subscriber_status">Default Status</Label>
            <Input
              id="default_subscriber_status"
              type="select"
              value={String(formData.default_subscriber_status)}
              onChange={(e) => setFormData(prev => ({ ...prev, default_subscriber_status: Number(e.target.value) }))}
            >
              <option value="0">Active</option>
              <option value="1">Barred</option>
              <option value="2">Suspended</option>
              <option value="3">Detached</option>
            </Input>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3 border-t border-surface-200 dark:border-surface-700 pt-4">
          <div>
            <Label htmlFor="default_ki">Default Ki (128-bit hex)</Label>
            <Input
              id="default_ki"
              value={formData.default_ki}
              onChange={(e) => setFormData(prev => ({ ...prev, default_ki: e.target.value }))}
              placeholder="For records without Ki"
              className="font-mono text-sm"
            />
          </div>
          <div>
            <Label htmlFor="default_op">Default OP (128-bit hex)</Label>
            <Input
              id="default_op"
              value={formData.default_op}
              onChange={(e) => setFormData(prev => ({ ...prev, default_op: e.target.value }))}
              placeholder="For records without OP"
              className="font-mono text-sm"
            />
          </div>
          <div>
            <Label htmlFor="default_k">Default K (256-bit hex)</Label>
            <Input
              id="default_k"
              value={formData.default_k}
              onChange={(e) => setFormData(prev => ({ ...prev, default_k: e.target.value }))}
              placeholder="For records without K"
              className="font-mono text-sm"
            />
          </div>
        </div>

        {showPreview && previewData.length > 0 && (
          <div className="border-t border-surface-200 dark:border-surface-700 pt-4">
            <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-3">Preview (First 10 Records)</h3>
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr className="table-header">
                    {Object.keys(previewData[0]).map((key) => (
                      <th key={key} className="table-head">{key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
{previewData.map((row, i) => (
                      <tr key={i} className="table-row">
                        {Object.values(row).map((val, j) => (
                          <td key={j} className="table-cell text-sm font-mono truncate max-w-xs">{String(val || '—')}</td>
                        ))}
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-4 border-t border-surface-200 dark:border-surface-700">
          <Button type="submit" disabled={!formData.file || uploadMutation.isPending}>
            {uploadMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                Start Batch Upload
              </>
            )}
          </Button>
        </div>
      </form>

      {uploadMutation.isSuccess && (
        <div className="card p-6 border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20">
          <div className="flex items-start gap-4">
            <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400 mt-0.5" />
            <div>
              <h3 className="font-medium text-green-800 dark:text-green-200">Batch Upload Completed</h3>
              <p className="text-sm text-green-700 dark:text-green-300 mt-1">
                Batch ID: <span className="font-mono">{uploadMutation.data?.batch_id}</span>
              </p>
              <p className="text-sm text-green-700 dark:text-green-300">
                Total: {uploadMutation.data?.total_records} | Success: {uploadMutation.data?.successful_records} | Failed: {uploadMutation.data?.failed_records}
              </p>
              {uploadMutation.data?.error_log && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-sm font-medium">View Error Log</summary>
                  <pre className="mt-2 p-3 bg-surface-100 dark:bg-surface-800 rounded text-xs overflow-auto max-h-40">
                    {JSON.stringify(uploadMutation.data.error_log, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}