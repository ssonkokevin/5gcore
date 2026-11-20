import { FullProfile, EPSSubscription, FiveGSubscription, IMSSubscription, SubscriberUpdate } from '@/types/api'
import { Input, Label, Switch } from '@/components/ui'
import { formatNumber } from '@/utils/format'

interface SubscriberSubscriptionsProps {
  fullProfile: FullProfile | undefined
  subscriber: any
  editing: boolean
  formData: Partial<SubscriberUpdate>
  onChange: (field: string, value: any) => void
}

export function SubscriberSubscriptions({ fullProfile, subscriber, editing, formData, onChange }: SubscriberSubscriptionsProps) {
  const eps = fullProfile?.eps
  const fiveg = fullProfile?.fiveg
  const ims = fullProfile?.ims

  const formDataRecord = formData as Record<string, any>
  const getValue = (field: string, defaultValue: any) => 
    formDataRecord[field] !== undefined ? formDataRecord[field] : subscriber[field]

  if (editing) {
    return (
      <div className="space-y-6">
        <div className="card p-6">
          <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4">EPS Subscription (4G)</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="eps_ue_ambr_ul">UE AMBR UL (bps)</Label>
              <Input
                id="eps_ue_ambr_ul"
                type="number"
                value={String(eps?.ue_ambr_ul || getValue('ambr_ul', subscriber.ambr_ul))}
                onChange={(e) => onChange('ambr_ul', Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="eps_ue_ambr_dl">UE AMBR DL (bps)</Label>
              <Input
                id="eps_ue_ambr_dl"
                type="number"
                value={String(eps?.ue_ambr_dl || getValue('ambr_dl', subscriber.ambr_dl))}
                onChange={(e) => onChange('ambr_dl', Number(e.target.value))}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="eps_nb_iot"
                checked={Boolean(eps?.nb_iot_allowed)}
                onChange={(checked) => console.log('NB-IoT', checked)}
              />
              <Label htmlFor="eps_nb_iot" className="mb-0">NB-IoT Allowed</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="eps_emtc"
                checked={Boolean(eps?.emtc_allowed)}
                onChange={(checked) => console.log('eMTC', checked)}
              />
              <Label htmlFor="eps_emtc" className="mb-0">eMTC Allowed</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="eps_v2x"
                checked={Boolean(eps?.v2x_allowed)}
                onChange={(checked) => console.log('V2X', checked)}
              />
              <Label htmlFor="eps_v2x" className="mb-0">V2X Allowed</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="eps_redcap"
                checked={Boolean(eps?.redcap_allowed)}
                onChange={(checked) => console.log('RedCap', checked)}
              />
              <Label htmlFor="eps_redcap" className="mb-0">RedCap Allowed</Label>
            </div>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4">5G Subscription</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="fiveg_ue_ambr_ul">UE AMBR UL (bps)</Label>
              <Input
                id="fiveg_ue_ambr_ul"
                type="number"
                value={String(fiveg?.ue_ambr_ul || getValue('ambr_ul', subscriber.ambr_ul))}
                onChange={(e) => onChange('ambr_ul', Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="fiveg_ue_ambr_dl">UE AMBR DL (bps)</Label>
              <Input
                id="fiveg_ue_ambr_dl"
                type="number"
                value={String(fiveg?.ue_ambr_dl || getValue('ambr_dl', subscriber.ambr_dl))}
                onChange={(e) => onChange('ambr_dl', Number(e.target.value))}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_urllc"
                checked={Boolean(fiveg?.urllc_allowed)}
                onChange={(checked) => console.log('URLLC', checked)}
              />
              <Label htmlFor="fiveg_urllc" className="mb-0">URLLC Allowed</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_mmtc"
                checked={Boolean(fiveg?.mmtc_allowed)}
                onChange={(checked) => console.log('mMTC', checked)}
              />
              <Label htmlFor="fiveg_mmtc" className="mb-0">mMTC Allowed</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_v2x"
                checked={Boolean(fiveg?.v2x_allowed_5g)}
                onChange={(checked) => console.log('V2X 5G', checked)}
              />
              <Label htmlFor="fiveg_v2x" className="mb-0">V2X Allowed (5G)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_redcap"
                checked={Boolean(fiveg?.redcap_allowed_5g)}
                onChange={(checked) => console.log('RedCap 5G', checked)}
              />
              <Label htmlFor="fiveg_redcap" className="mb-0">RedCap Allowed (5G)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_ntn"
                checked={Boolean(fiveg?.ntn_allowed_5g)}
                onChange={(checked) => console.log('NTN 5G', checked)}
              />
              <Label htmlFor="fiveg_ntn" className="mb-0">NTN Allowed (5G)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_xr"
                checked={Boolean(fiveg?.xr_allowed_5g)}
                onChange={(checked) => console.log('XR 5G', checked)}
              />
              <Label htmlFor="fiveg_xr" className="mb-0">XR Allowed (5G)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fiveg_aiml"
                checked={Boolean(fiveg?.aiml_allowed_5g)}
                onChange={(checked) => console.log('AI/ML 5G', checked)}
              />
              <Label htmlFor="fiveg_aiml" className="mb-0">AI/ML Allowed (5G)</Label>
            </div>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4">IMS Subscription</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="ims_impi">IMPI</Label>
              <Input
                id="ims_impi"
                value={ims?.impi || ''}
                onChange={(e) => console.log('IMPI', e.target.value)}
                disabled={!editing}
              />
            </div>
            <div>
              <Label htmlFor="ims_domain">IMS Domain</Label>
              <Input
                id="ims_domain"
                value={ims?.ims_domain || ''}
                onChange={(e) => console.log('IMS Domain', e.target.value)}
                disabled={!editing}
              />
            </div>
            <div>
              <Label htmlFor="ims_scscf">S-CSCF Name</Label>
              <Input
                id="ims_scscf"
                value={ims?.scscf_name || ''}
                onChange={(e) => console.log('S-CSCF', e.target.value)}
                disabled={!editing}
              />
            </div>
            <div>
              <Label htmlFor="ims_auth_scheme">Auth Scheme</Label>
              <Input
                id="ims_auth_scheme"
                value={ims?.auth_scheme || ''}
                disabled={!editing}
              />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="card p-6">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4">EPS Subscription (4G)</h3>
        <dl className="grid gap-3 md:grid-cols-3">
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">UE AMBR UL</dt><dd className="font-mono">{formatNumber(eps?.ue_ambr_ul || 0)} bps</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">UE AMBR DL</dt><dd className="font-mono">{formatNumber(eps?.ue_ambr_dl || 0)} bps</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">Default APN</dt><dd>{eps?.default_apn || '—'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">NB-IoT</dt><dd>{eps?.nb_iot_allowed ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">eMTC</dt><dd>{eps?.emtc_allowed ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">V2X</dt><dd>{eps?.v2x_allowed ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">RedCap</dt><dd>{eps?.redcap_allowed ? 'Yes' : 'No'}</dd></div>
        </dl>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4">5G Subscription</h3>
        <dl className="grid gap-3 md:grid-cols-3">
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">UE AMBR UL</dt><dd className="font-mono">{formatNumber(fiveg?.ue_ambr_ul || 0)} bps</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">UE AMBR DL</dt><dd className="font-mono">{formatNumber(fiveg?.ue_ambr_dl || 0)} bps</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">SUPI</dt><dd className="font-mono">{fiveg?.supi || '—'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">URLLC</dt><dd>{fiveg?.urllc_allowed ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">mMTC</dt><dd>{fiveg?.mmtc_allowed ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">V2X</dt><dd>{fiveg?.v2x_allowed_5g ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">RedCap</dt><dd>{fiveg?.redcap_allowed_5g ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">NTN</dt><dd>{fiveg?.ntn_allowed_5g ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">XR</dt><dd>{fiveg?.xr_allowed_5g ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">AI/ML</dt><dd>{fiveg?.aiml_allowed_5g ? 'Yes' : 'No'}</dd></div>
        </dl>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-medium text-surface-900 dark:text-surface-100 mb-4">IMS Subscription</h3>
        <dl className="grid gap-3 md:grid-cols-3">
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">IMPI</dt><dd className="font-mono">{ims?.impi || '—'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">IMS Domain</dt><dd>{ims?.ims_domain || '—'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">S-CSCF</dt><dd>{ims?.scscf_name || '—'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">Reg Status</dt><dd>{ims?.reg_status || 'unregistered'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">Auth Scheme</dt><dd>{ims?.auth_scheme || 'AKAv1-MD5'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">MTSI</dt><dd>{ims?.mtsi_allowed ? 'Yes' : 'No'}</dd></div>
          <div><dt className="text-xs text-surface-500 dark:text-surface-400">RCS</dt><dd>{ims?.rcs_allowed ? 'Yes' : 'No'}</dd></div>
        </dl>
      </div>
    </div>
  )
}