'use client'

import { useEffect, useRef, useState } from 'react'

interface LogViewerProps {
  refreshInterval?: number
}

export default function LogViewer({ refreshInterval = 3000 }: LogViewerProps) {
  const [logs, setLogs] = useState<string[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch('/api/logs?tail=100')
        const data = await res.json()

        if (data.error) {
          setError(data.error)
        } else {
          setLogs(data.lines)
          setError(null)
        }
      } catch (err) {
        setError('Failed to fetch logs')
      }
    }

    fetchLogs()
    const interval = setInterval(fetchLogs, refreshInterval)
    return () => clearInterval(interval)
  }, [refreshInterval])

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const highlightLog = (line: string) => {
    if (line.includes('[error]') || line.includes('ERROR') || line.includes('Failed')) {
      return 'text-red-400'
    }
    if (line.includes('[warning]') || line.includes('WARN')) {
      return 'text-yellow-400'
    }
    if (line.includes('[info]') || line.includes('INFO')) {
      return 'text-blue-400'
    }
    if (line.includes('Documents:') || line.includes('Sent to Onyx')) {
      return 'text-green-400 font-semibold'
    }
    return 'text-gray-300'
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      <div className="flex justify-between items-center px-4 py-2 bg-gray-800 border-b border-gray-700">
        <h2 className="font-semibold text-white">Container Logs</h2>
        <label className="flex items-center gap-2 text-sm text-gray-400">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={e => setAutoScroll(e.target.checked)}
            className="rounded"
          />
          Auto-scroll
        </label>
      </div>

      {error ? (
        <div className="p-4 text-red-400">{error}</div>
      ) : (
        <div
          ref={containerRef}
          className="logs-container h-96 overflow-y-auto p-4 font-mono text-sm"
        >
          {logs.map((line, i) => (
            <div key={i} className={`${highlightLog(line)} whitespace-pre-wrap break-all`}>
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
