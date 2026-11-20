import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Search, Filter, ChevronDown, MoreVertical, Edit, Trash2, Eye } from 'lucide-react'
import { useSubscribers, useDeleteSubscriber } from '../../api/queries'
import { Subscriber, SubscriberCreate } from '../../types/api'
import { formatNumber, getStatusBadge, getNetworkAccessModeBadge, formatDate } from '../../utils/format'
import { clsx } from 'clsx'

export function Subscribers() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')

  const { data, isLoading, error, refetch } = useSubscribers(page, pageSize)
  const deleteMutation = useDeleteSubscriber()

  const handleDelete = (imsi: string) => {
    if (window.confirm(`Are you sure you want to delete subscriber ${imsi}?`)) {
      deleteMutation.mutate(imsi, {
        onSuccess: () => refetch(),
      })
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="card p-6 text-center">
        <p className="text-red-600">Failed to load subscribers</p>
        <button onClick={() => refetch()} className="btn-primary mt-4">Retry</button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-100">Subscribers</h1>
          <p className="text-surface-500 dark:text-surface-400">Manage 5G/4G/3G/2G subscriber profiles</p>
        </div>
        <Link to="/subscribers/new" className="btn-primary">
          <Plus className="h-4 w-4 mr-2" />
          Add Subscriber
        </Link>
      </div>

      <div className="card">
        <div className="p-4 border-b border-surface-200 dark:border-surface-700">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-surface-400" />
              <input
                type="text"
                placeholder="Search by IMSI, MSISDN..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="input pl-10"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="input w-full sm:w-48"
            >
              <option value="">All Status</option>
              <option value="0">Active</option>
              <option value="1">Barred</option>
              <option value="2">Suspended</option>
              <option value="3">Detached</option>
            </select>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="input w-full sm:w-40"
            >
              <option value={25}>25 per page</option>
              <option value={50}>50 per page</option>
              <option value={100}>100 per page</option>
            </select>
          </div>
        </div>

        <div className="table-container">
          <table className="table">
            <thead>
              <tr className="table-header">
                <th className="table-head">IMSI</th>
                <th className="table-head">MSISDN</th>
                <th className="table-head">IMEI</th>
                <th className="table-head">Status</th>
                <th className="table-head">Network Access</th>
                <th className="table-head">AMBR (UL/DL)</th>
                <th className="table-head">Batch</th>
                <th className="table-head">Created</th>
                <th className="table-head">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.results.map((sub: Subscriber) => (
                <tr key={sub.imsi} className="table-row">
                  <td className="table-cell font-mono text-sm">{sub.imsi}</td>
                  <td className="table-cell">{sub.msisdn || '—'}</td>
                  <td className="table-cell font-mono text-sm">{sub.imei || '—'}</td>
                  <td className="table-cell">
                    <span className={clsx('badge', getStatusBadge(sub.subscriber_status).className)}>
                      {getStatusBadge(sub.subscriber_status).label}
                    </span>
                  </td>
                  <td className="table-cell">
                    <span className={clsx('badge', getNetworkAccessModeBadge(sub.network_access_mode).className)}>
                      {getNetworkAccessModeBadge(sub.network_access_mode).label}
                    </span>
                  </td>
                  <td className="table-cell font-mono text-sm">
                    {formatNumber(sub.ambr_ul)} / {formatNumber(sub.ambr_dl)}
                  </td>
                  <td className="table-cell text-sm text-surface-500 dark:text-surface-400">
                    {sub.batch_id || '—'}
                  </td>
                  <td className="table-cell text-sm text-surface-500 dark:text-surface-400">
                    {formatDate(sub.created_at)}
                  </td>
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/subscribers/${sub.imsi}`}
                        className="p-1.5 rounded hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                        title="View Details"
                      >
                        <Eye className="h-4 w-4" />
                      </Link>
                      <Link
                        to={`/subscribers/${sub.imsi}/edit`}
                        className="p-1.5 rounded hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
                        title="Edit"
                      >
                        <Edit className="h-4 w-4" />
                      </Link>
                      <button
                        onClick={() => handleDelete(sub.imsi)}
                        disabled={deleteMutation.isPending}
                        className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors text-red-600"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data && data.count > pageSize && (
          <div className="p-4 border-t border-surface-200 dark:border-surface-700 flex items-center justify-between">
            <p className="text-sm text-surface-500 dark:text-surface-400">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, data.count)} of {data.count} subscribers
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(page - 1)}
                disabled={page === 1}
                className="btn-outline px-3 py-1.5 text-sm"
              >
                <ChevronDown className="h-4 w-4 rotate-180" />
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page * pageSize >= data.count}
                className="btn-outline px-3 py-1.5 text-sm"
              >
                <ChevronDown className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}