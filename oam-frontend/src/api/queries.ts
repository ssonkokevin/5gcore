import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from './client'
import type {
  Subscriber,
  SubscriberCreate,
  SubscriberUpdate,
  FullProfile,
  EPSSubscription,
  FiveGSubscription,
  IMSSubscription,
  APNProfile,
  SupplementaryService,
  RoamingProfile,
  CamelServiceProfile,
  AuthVector,
  AuthVectorGenerateRequest,
  AuthVectorResponse,
  BatchUpload,
  BatchUploadRequest,
  IMSIRange,
  IMSIRangeCreate,
  IMSIAllocateRequest,
  IMSIAllocateResponse,
  USSDRoute,
  NetworkNode,
  NetworkNodeCreate,
  MCCMNC,
  PLMNProfile,
  DRALocal,
  DRAPeerSet,
  DRAPeer,
  DRARoute,
  DRATranslate,
  M3UAGlobal,
  M3UALocal,
  M3UALinkset,
  M3UALink,
  STPRoute,
  STPTranslate,
  UECMRegistration,
  KPIData,
  KPITimeSeries,
} from '../types/api'

// Query Keys
export const queryKeys = {
  subscribers: ['subscribers'] as const,
  subscriber: (imsi: string) => ['subscriber', imsi] as const,
  fullProfile: (imsi: string) => ['fullProfile', imsi] as const,
  epsSubscription: (imsi: string) => ['epsSubscription', imsi] as const,
  fiveGSubscription: (imsi: string) => ['fiveGSubscription', imsi] as const,
  imsSubscription: (imsi: string) => ['imsSubscription', imsi] as const,
  apnProfiles: (imsi: string) => ['apnProfiles', imsi] as const,
  supplementaryServices: (imsi: string) => ['supplementaryServices', imsi] as const,
  roamingProfiles: (imsi: string) => ['roamingProfiles', imsi] as const,
  camelProfiles: (imsi: string) => ['camelProfiles', imsi] as const,
  authVector: (imsi: string, params?: Record<string, any>) => ['authVector', imsi, params] as const,
  batchStatus: (batchId: string) => ['batchStatus', batchId] as const,
  imsiRanges: ['imsiRanges'] as const,
  ussdRoutes: ['ussdRoutes'] as const,
  networkNodes: ['networkNodes'] as const,
  mccMnc: ['mccMnc'] as const,
  plmnProfiles: ['plmnProfiles'] as const,
  dra: {
    local: ['dra', 'local'] as const,
    peerSets: ['dra', 'peerSets'] as const,
    peers: ['dra', 'peers'] as const,
    routes: ['dra', 'routes'] as const,
    translates: ['dra', 'translates'] as const,
  },
  stp: {
    m3uaGlobal: ['stp', 'm3uaGlobal'] as const,
    m3uaLocal: ['stp', 'm3uaLocal'] as const,
    linksets: ['stp', 'linksets'] as const,
    links: ['stp', 'links'] as const,
    routes: ['stp', 'routes'] as const,
    translates: ['stp', 'translates'] as const,
  },
  uecm: {
    registrations: ['uecm', 'registrations'] as const,
    registration: (imsi: string, accessType: string) => ['uecm', 'registration', imsi, accessType] as const,
  },
  kpi: {
    current: ['kpi', 'current'] as const,
    timeseries: (hours: number) => ['kpi', 'timeseries', hours] as const,
  },
} as const

// Subscriber Hooks
export const useSubscribers = (page = 1, pageSize = 50) =>
  useQuery({
    queryKey: [...queryKeys.subscribers, page, pageSize],
    queryFn: () => apiGet<{ results: Subscriber[]; count: number }>('/subscribers/', { page, page_size: pageSize }),
  })

export const useSubscriber = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.subscriber(imsi),
    queryFn: () => apiGet<Subscriber>(`/subscribers/${imsi}/`),
    enabled: !!imsi,
  })

export const useFullProfile = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.fullProfile(imsi),
    queryFn: () => apiGet<FullProfile>(`/subscribers/${imsi}/full-profile/`),
    enabled: !!imsi,
  })

export const useCreateSubscriber = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: SubscriberCreate) => apiPost<Subscriber>('/subscribers/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers })
    },
  })
}

export const useUpdateSubscriber = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ imsi, data }: { imsi: string; data: SubscriberUpdate }) =>
      apiPut<Subscriber>(`/subscribers/${imsi}/`, data),
    onSuccess: (_, { imsi }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.subscriber(imsi) })
      queryClient.invalidateQueries({ queryKey: queryKeys.fullProfile(imsi) })
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers })
    },
  })
}

export const useDeleteSubscriber = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (imsi: string) => apiDelete(`/subscribers/${imsi}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers })
    },
  })
}

// Subscription Hooks
export const useEPSSubscription = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.epsSubscription(imsi),
    queryFn: () => apiGet<EPSSubscription>(`/subscribers/${imsi}/eps-subscription/`),
    enabled: !!imsi,
  })

export const useFiveGSubscription = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.fiveGSubscription(imsi),
    queryFn: () => apiGet<FiveGSubscription>(`/subscribers/${imsi}/5g-subscription/`),
    enabled: !!imsi,
  })

export const useIMSSubscription = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.imsSubscription(imsi),
    queryFn: () => apiGet<IMSSubscription>(`/subscribers/${imsi}/ims-subscription/`),
    enabled: !!imsi,
  })

// APN Profile Hooks
export const useAPNProfiles = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.apnProfiles(imsi),
    queryFn: () => apiGet<APNProfile[]>(`/subscribers/${imsi}/apn-profiles/`),
    enabled: !!imsi,
  })

export const useCreateAPNProfile = (imsi: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<APNProfile>) => apiPost<APNProfile>(`/subscribers/${imsi}/apn-profiles/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apnProfiles(imsi) })
    },
  })
}

export const useUpdateAPNProfile = (imsi: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ apn, data }: { apn: string; data: Partial<APNProfile> }) =>
      apiPut<APNProfile>(`/subscribers/${imsi}/apn-profiles/${apn}/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apnProfiles(imsi) })
    },
  })
}

export const useDeleteAPNProfile = (imsi: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (apn: string) => apiDelete(`/subscribers/${imsi}/apn-profiles/${apn}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apnProfiles(imsi) })
    },
  })
}

// Supplementary Service Hooks
export const useSupplementaryServices = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.supplementaryServices(imsi),
    queryFn: () => apiGet<SupplementaryService[]>(`/subscribers/${imsi}/supplementary-services/`),
    enabled: !!imsi,
  })

// Roaming Profile Hooks
export const useRoamingProfiles = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.roamingProfiles(imsi),
    queryFn: () => apiGet<RoamingProfile[]>(`/subscribers/${imsi}/roaming-profiles/`),
    enabled: !!imsi,
  })

// CAMEL Profile Hooks
export const useCamelProfiles = (imsi: string) =>
  useQuery({
    queryKey: queryKeys.camelProfiles(imsi),
    queryFn: () => apiGet<CamelServiceProfile[]>(`/subscribers/${imsi}/camel-profiles/`),
    enabled: !!imsi,
  })

// Auth Vector Hooks
export const useAuthVector = (imsi: string, params?: { rand?: string; algorithm?: string }) =>
  useQuery({
    queryKey: queryKeys.authVector(imsi, params),
    queryFn: () => apiGet<AuthVector>(`/subscribers/${imsi}/auth-vector/`, params),
    enabled: !!imsi,
  })

export const useGenerateAuthVector = (imsi: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: AuthVectorGenerateRequest) =>
      apiPost<AuthVectorResponse>(`/subscribers/${imsi}/auth-vector/generate/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.authVector(imsi) })
    },
  })
}

// Batch Upload Hooks
export const useBatchUpload = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: BatchUploadRequest) => {
      const formData = new FormData()
      formData.append('file', data.file)
      if (data.batch_id) formData.append('batch_id', data.batch_id)
      if (data.auto_derive !== undefined) formData.append('auto_derive', String(data.auto_derive))
      if (data.default_ki) formData.append('default_ki', data.default_ki)
      if (data.default_op) formData.append('default_op', data.default_op)
      if (data.default_k) formData.append('default_k', data.default_k)
      if (data.default_network_access_mode !== undefined) formData.append('default_network_access_mode', String(data.default_network_access_mode))
      if (data.default_subscriber_status !== undefined) formData.append('default_subscriber_status', String(data.default_subscriber_status))
      return apiUpload<BatchUpload>('/subscribers/batch/', formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers })
    },
  })
}

export const useBatchStatus = (batchId: string) =>
  useQuery({
    queryKey: queryKeys.batchStatus(batchId),
    queryFn: () => apiGet<BatchUpload>(`/batches/${batchId}/`),
    enabled: !!batchId,
    refetchInterval: 5000,
  })

// IMSI Range Hooks
export const useIMSIRanges = () =>
  useQuery({
    queryKey: queryKeys.imsiRanges,
    queryFn: () => apiGet<IMSIRange[]>('/imsi-ranges/'),
  })

export const useCreateIMSIRange = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: IMSIRangeCreate) => apiPost<IMSIRange>('/imsi-ranges/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.imsiRanges })
    },
  })
}

export const useAllocateIMSI = () =>
  useMutation({
    mutationFn: (data: IMSIAllocateRequest) => apiPost<IMSIAllocateResponse>('/imsi-ranges/allocate/', data),
  })

// USSD Route Hooks
export const useUSSDRoutes = () =>
  useQuery({
    queryKey: queryKeys.ussdRoutes,
    queryFn: () => apiGet<USSDRoute[]>('/ussd-routes/'),
  })

export const useCreateUSSDRoute = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<USSDRoute>) => apiPost<USSDRoute>('/ussd-routes/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ussdRoutes })
    },
  })
}

// Network Node Hooks
export const useNetworkNodes = (params?: { node_type?: string; plmn_id?: string }) =>
  useQuery({
    queryKey: [...queryKeys.networkNodes, params],
    queryFn: () => apiGet<NetworkNode[]>('/network-nodes/', params),
  })

export const useCreateNetworkNode = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: NetworkNodeCreate) => apiPost<NetworkNode>('/network-nodes/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.networkNodes })
    },
  })
}

// Reference Data Hooks
export const useMCCMNC = () =>
  useQuery({
    queryKey: queryKeys.mccMnc,
    queryFn: () => apiGet<MCCMNC[]>('/reference/mcc-mnc/'),
  })

export const usePLMNProfiles = () =>
  useQuery({
    queryKey: queryKeys.plmnProfiles,
    queryFn: () => apiGet<PLMNProfile[]>('/reference/plmn-profiles/'),
  })

// DRA Hooks
export const useDRALocal = () =>
  useQuery({
    queryKey: queryKeys.dra.local,
    queryFn: () => apiGet<DRALocal[]>('/dra/local/'),
  })

export const useDRAPeerSets = () =>
  useQuery({
    queryKey: queryKeys.dra.peerSets,
    queryFn: () => apiGet<DRAPeerSet[]>('/dra/peer-sets/'),
  })

export const useDRAPeers = () =>
  useQuery({
    queryKey: queryKeys.dra.peers,
    queryFn: () => apiGet<DRAPeer[]>('/dra/peers/'),
  })

export const useDRARoutes = () =>
  useQuery({
    queryKey: queryKeys.dra.routes,
    queryFn: () => apiGet<DRARoute[]>('/dra/routes/'),
  })

export const useDRATranslates = () =>
  useQuery({
    queryKey: queryKeys.dra.translates,
    queryFn: () => apiGet<DRATranslate[]>('/dra/translates/'),
  })

// STP Hooks
export const useM3UAGlobal = () =>
  useQuery({
    queryKey: queryKeys.stp.m3uaGlobal,
    queryFn: () => apiGet<M3UAGlobal[]>('/stp/m3ua/global/'),
  })

export const useM3UALocal = () =>
  useQuery({
    queryKey: queryKeys.stp.m3uaLocal,
    queryFn: () => apiGet<M3UALocal[]>('/stp/m3ua/local/'),
  })

export const useM3UALinksets = () =>
  useQuery({
    queryKey: queryKeys.stp.linksets,
    queryFn: () => apiGet<M3UALinkset[]>('/stp/m3ua/linksets/'),
  })

export const useM3UALinks = () =>
  useQuery({
    queryKey: queryKeys.stp.links,
    queryFn: () => apiGet<M3UALink[]>('/stp/m3ua/links/'),
  })

export const useSTPRoutes = () =>
  useQuery({
    queryKey: queryKeys.stp.routes,
    queryFn: () => apiGet<STPRoute[]>('/stp/routes/'),
  })

export const useSTPTranslates = () =>
  useQuery({
    queryKey: queryKeys.stp.translates,
    queryFn: () => apiGet<STPTranslate[]>('/stp/translates/'),
  })

// UECM Hooks
export const useUECMRegistrations = () =>
  useQuery({
    queryKey: queryKeys.uecm.registrations,
    queryFn: () => apiGet<UECMRegistration[]>('/uecm/registrations/'),
  })

export const useUECMRegistration = (imsi: string, accessType: string) =>
  useQuery({
    queryKey: queryKeys.uecm.registration(imsi, accessType),
    queryFn: () => apiGet<UECMRegistration>(`/uecm/registrations/${imsi}/${accessType}/`),
    enabled: !!imsi && !!accessType,
  })

// KPI Hooks
export const useKPICurrent = () =>
  useQuery({
    queryKey: queryKeys.kpi.current,
    queryFn: () => apiGet<KPIData>('/kpi/current/'),
    refetchInterval: 10000,
  })

export const useKPITimeSeries = (hours = 24) =>
  useQuery({
    queryKey: queryKeys.kpi.timeseries(hours),
    queryFn: () => apiGet<KPITimeSeries[]>(`/kpi/timeseries/`, { hours }),
    refetchInterval: 30000,
  })