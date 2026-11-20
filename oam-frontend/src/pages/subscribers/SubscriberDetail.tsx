import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { SubscriberProfile } from './SubscriberProfile'
import { SubscriberSubscriptions } from './SubscriberSubscriptions'
import { SubscriberAPNProfiles } from './SubscriberAPNProfiles'
import { SubscriberSupplementaryServices } from './SubscriberSupplementaryServices'
import { SubscriberRoamingProfiles } from './SubscriberRoamingProfiles'
import { SubscriberCamelProfiles } from './SubscriberCamelProfiles'
import { SubscriberAuthVectors } from './SubscriberAuthVectors'
import { useFullProfile, useSubscriber, useUpdateSubscriber } from '@/api/queries'
import { Subscriber, SubscriberUpdate } from '@/types/api'
import { toast } from 'react-hot-toast'
import { ArrowLeft, Edit } from 'lucide-react'
import { clsx } from 'clsx'

export function SubscriberDetail() {
  const { imsi } = useParams<{ imsi: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('profile')
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState<Partial<SubscriberUpdate>>({})

  const { data: subscriber, isLoading: subscriberLoading } = useSubscriber(imsi!)
  const { data: fullProfile, isLoading: profileLoading } = useFullProfile(imsi!)
  const updateMutation = useUpdateSubscriber()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!imsi) return
    updateMutation.mutate({ imsi, data: formData }, {
      onSuccess: () => {
        toast.success('Subscriber updated successfully')
        setEditing(false)
      },
      onError: () => {
        toast.error('Failed to update subscriber')
      },
    })
  }

  const handleChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  if (subscriberLoading || profileLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (!subscriber) {
    return (
      <div className="card p-6 text-center">
        <p className="text-red-600">Subscriber not found</p>
        <Link to="/subscribers" className="btn-primary mt-4 inline-block">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Subscribers
        </Link>
      </div>
    )
  }

  const tabs = [
    { id: 'profile', label: 'Profile', icon: null },
    { id: 'subscriptions', label: 'Subscriptions', icon: null },
    { id: 'apn', label: 'APN/DNN Profiles', icon: null },
    { id: 'supplementary', label: 'Supplementary Services', icon: null },
    { id: 'roaming', label: 'Roaming Profiles', icon: null },
    { id: 'camel', label: 'CAMEL Profiles', icon: null },
    { id: 'auth', label: 'Auth Vectors', icon: null },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link to="/subscribers" className="btn-outline">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">Subscriber Details</h1>
            <p className="text-surface-500 dark:text-surface-400 font-mono">{imsi}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant={editing ? 'secondary' : 'outline'}
            onClick={() => setEditing(!editing)}
            disabled={editing && updateMutation.isPending}
          >
            {editing ? 'Cancel' : 'Edit'}
            {editing && updateMutation.isPending && <span className="animate-spin ml-2 h-4 w-4" />}
          </Button>
          {editing && (
            <Button variant="primary" type="submit" form="subscriber-form" disabled={updateMutation.isPending}>
              Save
            </Button>
          )}
        </div>
      </div>

      <form id="subscriber-form" onSubmit={handleSubmit}>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-7">
            {tabs.map((tab) => (
              <TabsTrigger key={tab.id} value={tab.id}>{tab.label}</TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="profile">
            <SubscriberProfile
              subscriber={subscriber}
              editing={editing}
              formData={formData}
              onChange={handleChange}
            />
          </TabsContent>

          <TabsContent value="subscriptions">
            <SubscriberSubscriptions
              fullProfile={fullProfile}
              subscriber={subscriber}
              editing={editing}
              formData={formData}
              onChange={handleChange}
            />
          </TabsContent>

          <TabsContent value="apn">
            <SubscriberAPNProfiles
              fullProfile={fullProfile}
              imsi={imsi!}
            />
          </TabsContent>

          <TabsContent value="supplementary">
            <SubscriberSupplementaryServices
              fullProfile={fullProfile}
              imsi={imsi!}
            />
          </TabsContent>

          <TabsContent value="roaming">
            <SubscriberRoamingProfiles
              fullProfile={fullProfile}
              imsi={imsi!}
            />
          </TabsContent>

          <TabsContent value="camel">
            <SubscriberCamelProfiles
              fullProfile={fullProfile}
              imsi={imsi!}
            />
          </TabsContent>

          <TabsContent value="auth">
            <SubscriberAuthVectors imsi={imsi!} />
          </TabsContent>
        </Tabs>
      </form>
    </div>
  )
}