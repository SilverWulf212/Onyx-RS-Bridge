'use client'

import { useEffect, useState } from 'react'
import { Cpu, HardDrive, Activity } from 'lucide-react'

interface ContainerStat {
  name: string
  cpu_percent: number
  memory_usage: number
  memory_limit: number
  memory_percent: number
  status: string
}

export default function ContainerStats() {
  const [stats, setStats] = useState<ContainerStat[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch('/api/stats')
        const data = await res.json()

        if (data.error) {
          setError(data.error)
        } else {
          setStats(data.containers)
          setError(null)
        }
      } catch {
        setError('Failed to fetch stats')
      }
    }

    fetchStats()
    const interval = setInterval(fetchStats, 3000)
    return () => clearInterval(interval)
  }, [])

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  const getCpuColor = (percent: number) => {
    if (percent > 80) return 'text-red-400'
    if (percent > 50) return 'text-yellow-400'
    return 'text-green-400'
  }

  const getMemColor = (percent: number) => {
    if (percent > 80) return 'text-red-400'
    if (percent > 60) return 'text-yellow-400'
    return 'text-green-400'
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 text-red-400">
        {error}
      </div>
    )
  }

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <div className="px-4 py-3 bg-gray-900 border-b border-gray-700">
        <h2 className="font-semibold text-white flex items-center gap-2">
          <Activity className="w-5 h-5" />
          Container Resources
        </h2>
      </div>

      <div className="divide-y divide-gray-700">
        {stats.map(container => (
          <div key={container.name} className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="font-medium text-white truncate max-w-[200px]">
                {container.name}
              </div>
              <span
                className={`text-xs px-2 py-1 rounded ${
                  container.status === 'running'
                    ? 'bg-green-900/50 text-green-400'
                    : 'bg-gray-700 text-gray-400'
                }`}
              >
                {container.status}
              </span>
            </div>

            {container.status === 'running' && (
              <div className="grid grid-cols-2 gap-4 mt-3">
                {/* CPU */}
                <div>
                  <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
                    <Cpu className="w-3 h-3" />
                    CPU
                  </div>
                  <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        container.cpu_percent > 80
                          ? 'bg-red-500'
                          : container.cpu_percent > 50
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                      } transition-all`}
                      style={{ width: `${Math.min(100, container.cpu_percent)}%` }}
                    />
                  </div>
                  <div className={`text-sm mt-1 ${getCpuColor(container.cpu_percent)}`}>
                    {container.cpu_percent}%
                  </div>
                </div>

                {/* Memory */}
                <div>
                  <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
                    <HardDrive className="w-3 h-3" />
                    Memory
                  </div>
                  <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        container.memory_percent > 80
                          ? 'bg-red-500'
                          : container.memory_percent > 60
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                      } transition-all`}
                      style={{ width: `${Math.min(100, container.memory_percent)}%` }}
                    />
                  </div>
                  <div className={`text-sm mt-1 ${getMemColor(container.memory_percent)}`}>
                    {formatBytes(container.memory_usage)} / {formatBytes(container.memory_limit)}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
