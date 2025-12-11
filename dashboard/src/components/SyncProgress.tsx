'use client'

import { useEffect, useState } from 'react'
import { CheckCircle, Clock, Loader2, AlertCircle } from 'lucide-react'

interface SyncStatus {
  documents_processed: number
  sent_to_onyx: number
  failed: number
  rate_per_minute: number
  estimated_remaining_minutes: number
  phase: string
  customers_complete: boolean
  assets_complete: boolean
  tickets_complete: boolean
  last_activity: string
}

export default function SyncProgress() {
  const [status, setStatus] = useState<SyncStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/sync-status')
        const data = await res.json()

        if (data.error) {
          setError(data.error)
        } else {
          setStatus(data)
          setError(null)
        }
      } catch {
        setError('Failed to fetch status')
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  const formatTime = (minutes: number) => {
    if (minutes < 60) return `${minutes}m`
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    return `${hours}h ${mins}m`
  }

  const PhaseIcon = ({ complete, active }: { complete: boolean; active: boolean }) => {
    if (complete) return <CheckCircle className="w-5 h-5 text-green-500" />
    if (active) return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
    return <Clock className="w-5 h-5 text-gray-500" />
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
        <div className="flex items-center gap-2 text-red-400">
          <AlertCircle className="w-5 h-5" />
          {error}
        </div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-gray-700 rounded w-2/3"></div>
      </div>
    )
  }

  const progressPercent =
    status.phase === 'tickets'
      ? Math.min(100, (status.documents_processed / 22000) * 100)
      : status.phase === 'customers'
        ? (status.documents_processed / 1390) * 100
        : 100

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
      <h2 className="text-xl font-bold text-white mb-4">Sync Progress</h2>

      {/* Main stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-3xl font-bold text-green-400">
            {status.documents_processed.toLocaleString()}
          </div>
          <div className="text-sm text-gray-400">Documents Processed</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-3xl font-bold text-blue-400">
            {status.sent_to_onyx.toLocaleString()}
          </div>
          <div className="text-sm text-gray-400">Sent to Onyx</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-3xl font-bold text-red-400">{status.failed}</div>
          <div className="text-sm text-gray-400">Failed</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-3xl font-bold text-yellow-400">
            {formatTime(status.estimated_remaining_minutes)}
          </div>
          <div className="text-sm text-gray-400">Est. Remaining</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-400 mb-1">
          <span>Progress ({status.phase})</span>
          <span>{Math.round(progressPercent)}%</span>
        </div>
        <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Phases */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PhaseIcon
            complete={status.customers_complete}
            active={status.phase === 'customers'}
          />
          <span
            className={
              status.customers_complete
                ? 'text-green-400'
                : status.phase === 'customers'
                  ? 'text-blue-400'
                  : 'text-gray-500'
            }
          >
            Customers
          </span>
        </div>
        <div className="flex-1 h-px bg-gray-700 mx-3" />
        <div className="flex items-center gap-2">
          <PhaseIcon
            complete={status.assets_complete}
            active={status.phase === 'assets'}
          />
          <span
            className={
              status.assets_complete
                ? 'text-green-400'
                : status.phase === 'assets'
                  ? 'text-blue-400'
                  : 'text-gray-500'
            }
          >
            Assets
          </span>
        </div>
        <div className="flex-1 h-px bg-gray-700 mx-3" />
        <div className="flex items-center gap-2">
          <PhaseIcon
            complete={status.tickets_complete}
            active={status.phase === 'tickets'}
          />
          <span
            className={
              status.tickets_complete
                ? 'text-green-400'
                : status.phase === 'tickets'
                  ? 'text-blue-400'
                  : 'text-gray-500'
            }
          >
            Tickets (22k)
          </span>
        </div>
      </div>

      {/* Last activity */}
      <div className="mt-4 text-xs text-gray-500">
        Last activity: {status.last_activity || 'N/A'}
      </div>
    </div>
  )
}
