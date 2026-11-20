import { Subscriber, SubscriberUpdate } from '@/types/api'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { clsx } from 'clsx'

interface SubscriberProfileProps {
  subscriber: Subscriber
  editing: boolean
  formData: Partial<SubscriberUpdate>
  onChange: (field: string, value: any) => void
}

export function SubscriberProfile({ subscriber, editing, formData, onChange }: SubscriberProfileProps) {
  const getValue = (field: keyof SubscriberUpdate, defaultValue: any) => {
    const val = formData[field] !== undefined ? formData[field] : subscriber[field]
    if (typeof val === 'boolean') return val ? 'on' : ''
    return val ?? defaultValue
  }

  if (editing) {
    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <div className="space-y-4">
          <div>
            <Label htmlFor="imsi">IMSI</Label>
            <Input id="imsi" value={subscriber.imsi} readOnly className="bg-surface-100 dark:bg-surface-800" />
          </div>
          <div>
            <Label htmlFor="msisdn">MSISDN</Label>
            <Input
              id="msisdn"
              value={getValue('msisdn', '') || ''}
              onChange={(e) => onChange('msisdn', e.target.value)}
              placeholder="Mobile Station ISDN Number"
            />
          </div>
          <div>
            <Label htmlFor="imei">IMEI</Label>
            <Input
              id="imei"
              value={getValue('imei', '') || ''}
              onChange={(e) => onChange('imei', e.target.value)}
              placeholder="International Mobile Equipment Identity"
            />
          </div>
          <div>
            <Label htmlFor="imei_sv">IMEI SV</Label>
            <Input
              id="imei_sv"
              value={getValue('imei_sv', '') || ''}
              onChange={(e) => onChange('imei_sv', e.target.value)}
              placeholder="IMEI Software Version"
            />
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <Label htmlFor="network_access_mode">Network Access Mode</Label>
            <Select
              id="network_access_mode"
              value={String(getValue('network_access_mode', subscriber.network_access_mode))}
              onChange={(e) => onChange('network_access_mode', Number(e.target.value))}
              options={[
                { value: '0', label: 'GPRS Only' },
                { value: '1', label: 'CS Only' },
                { value: '2', label: 'GPRS + CS' },
                { value: '3', label: '5G Only' },
                { value: '4', label: '5G + EPC' },
              ]}
            />
          </div>
          <div>
            <Label htmlFor="subscriber_status">Subscriber Status</Label>
            <Select
              id="subscriber_status"
              value={String(getValue('subscriber_status', subscriber.subscriber_status))}
              onChange={(e) => onChange('subscriber_status', Number(e.target.value))}
              options={[
                { value: '0', label: 'Active' },
                { value: '1', label: 'Barred' },
                { value: '2', label: 'Suspended' },
                { value: '3', label: 'Detached' },
              ]}
            />
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="roaming_restricted"
              checked={Boolean(getValue('roaming_restricted', subscriber.roaming_restricted))}
              onChange={(checked) => onChange('roaming_restricted', checked)}
            />
            <Label htmlFor="roaming_restricted" className="mb-0">Roaming Restricted</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="prose_enabled"
              checked={Boolean(getValue('prose_enabled', subscriber.prose_enabled))}
              onChange={(checked) => onChange('prose_enabled', checked)}
            />
            <Label htmlFor="prose_enabled" className="mb-0">5G ProSe Enabled (Rel-17)</Label>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <Label htmlFor="ambr_ul">AMBR UL (bps)</Label>
            <Input
              id="ambr_ul"
              type="number"
              value={String(getValue('ambr_ul', subscriber.ambr_ul))}
              onChange={(e) => onChange('ambr_ul', Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="ambr_dl">AMBR DL (bps)</Label>
            <Input
              id="ambr_dl"
              type="number"
              value={String(getValue('ambr_dl', subscriber.ambr_dl))}
              onChange={(e) => onChange('ambr_dl', Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="sqn">Sequence Number (SQN)</Label>
            <Input
              id="sqn"
              type="number"
              value={String(getValue('sqn', subscriber.sqn))}
              onChange={(e) => onChange('sqn', Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="amf">AMF (hex)</Label>
            <Input
              id="amf"
              value={getValue('amf', subscriber.amf) || ''}
              onChange={(e) => onChange('amf', e.target.value)}
              placeholder="8000"
            />
          </div>
        </div>

        <div className="space-y-4 lg:col-span-3">
          <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Security Keys (Read-Only in Detail View)</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="k">5G Root Key (K) - 256-bit hex</Label>
              <Input id="k" value={subscriber.k || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="ki">4G/3G/2G Root Key (Ki) - 128-bit hex</Label>
              <Input id="ki" value={subscriber.ki || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="op">OP (Operator Variant) - 128-bit hex</Label>
              <Input id="op" value={subscriber.op || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="opc">OPc (Derived) - 128-bit hex</Label>
              <Input id="opc" value={subscriber.opc || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="k_asme">K_ASME</Label>
              <Input id="k_asme" value={subscriber.k_asme || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="k_seaf">K_SEAF</Label>
              <Input id="k_seaf" value={subscriber.k_seaf || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="k_ausf">K_AUSF</Label>
              <Input id="k_ausf" value={subscriber.k_ausf || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
            <div>
              <Label htmlFor="kc">Kc (2G/3G Cipher Key)</Label>
              <Input id="kc" value={subscriber.kc || ''} readOnly className="font-mono text-sm bg-surface-100 dark:bg-surface-800" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      <div className="space-y-3">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Identity</h3>
        <dl className="space-y-2">
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">IMSI</dt>
            <dd className="font-mono font-medium">{subscriber.imsi}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">MSISDN</dt>
            <dd>{subscriber.msisdn || '—'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">IMEI</dt>
            <dd className="font-mono">{subscriber.imei || '—'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">IMEI SV</dt>
            <dd className="font-mono">{subscriber.imei_sv || '—'}</dd>
          </div>
        </dl>
      </div>

      <div className="space-y-3">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Network Access</h3>
        <dl className="space-y-2">
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">Access Mode</dt>
            <dd>{subscriber.network_access_mode === 3 ? '5G Only' : subscriber.network_access_mode === 2 ? 'GPRS+CS' : subscriber.network_access_mode === 1 ? 'CS Only' : 'GPRS Only'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">Status</dt>
            <dd>{subscriber.subscriber_status === 0 ? 'Active' : subscriber.subscriber_status === 1 ? 'Barred' : subscriber.subscriber_status === 2 ? 'Suspended' : 'Detached'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">Roaming Restricted</dt>
            <dd>{subscriber.roaming_restricted ? 'Yes' : 'No'}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">ProSe Enabled</dt>
            <dd>{subscriber.prose_enabled ? 'Yes' : 'No'}</dd>
          </div>
        </dl>
      </div>

      <div className="space-y-3">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">QoS / AMBR</h3>
        <dl className="space-y-2">
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">AMBR UL</dt>
            <dd className="font-mono">{subscriber.ambr_ul.toLocaleString()} bps</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">AMBR DL</dt>
            <dd className="font-mono">{subscriber.ambr_dl.toLocaleString()} bps</dd>
          </div>
        </dl>
      </div>

      <div className="space-y-3">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Authentication</h3>
        <dl className="space-y-2">
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">SQN</dt>
            <dd className="font-mono">{subscriber.sqn}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-surface-500 dark:text-surface-400">AMF</dt>
            <dd className="font-mono">{subscriber.amf}</dd>
          </div>
        </dl>
      </div>

      <div className="lg:col-span-3 space-y-3">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Security Keys (Derived)</h3>
        <div className="grid gap-3 md:grid-cols-4">
          {[
            { label: 'K (5G Root)', value: subscriber.k },
            { label: 'Ki (4G/3G/2G)', value: subscriber.ki },
            { label: 'OP', value: subscriber.op },
            { label: 'OPc', value: subscriber.opc },
            { label: 'K_ASME', value: subscriber.k_asme },
            { label: 'K_SEAF', value: subscriber.k_seaf },
            { label: 'K_AUSF', value: subscriber.k_ausf },
            { label: 'Kc', value: subscriber.kc },
          ].map((item) => (
            <div key={item.label} className="p-3 bg-surface-50 dark:bg-surface-800/50 rounded-lg">
              <dt className="text-xs text-surface-500 dark:text-surface-400">{item.label}</dt>
              <dd className="font-mono text-sm break-all">{item.value || '—'}</dd>
            </div>
          ))}
        </div>
      </div>

      <div className="lg:col-span-3 space-y-3">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100">Metadata</h3>
        <dl className="grid gap-3 md:grid-cols-4">
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">Batch ID</dt>
            <dd>{subscriber.batch_id || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">IMSI Range</dt>
            <dd className="font-mono">{subscriber.imsi_range_start} - {subscriber.imsi_range_end}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">MVNO</dt>
            <dd>{subscriber.mvno_mcc && subscriber.mvno_mnc ? `${subscriber.mvno_mcc}-${subscriber.mvno_mnc}` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">Created</dt>
            <dd>{new Date(subscriber.created_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">Updated</dt>
            <dd>{new Date(subscriber.updated_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">RedCap</dt>
            <dd>{subscriber.redcap_allowed ? 'Yes' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">NTN</dt>
            <dd>{subscriber.ntn_allowed ? 'Yes' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-xs text-surface-500 dark:text-surface-400">XR</dt>
            <dd>{subscriber.xr_allowed ? 'Yes' : 'No'}</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}