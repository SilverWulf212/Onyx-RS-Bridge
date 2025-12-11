import SyncProgress from '@/components/SyncProgress'
import ContainerStats from '@/components/ContainerStats'
import LogViewer from '@/components/LogViewer'

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-950 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">
            RS-Bridge Dashboard
          </h1>
          <p className="text-gray-400 mt-1">
            RepairShopr → Onyx Sync Monitor
          </p>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column - Progress and Stats */}
          <div className="lg:col-span-2 space-y-6">
            <SyncProgress />
            <LogViewer />
          </div>

          {/* Right column - Container stats */}
          <div>
            <ContainerStats />
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-600">
          Auto-refreshes every 3-5 seconds • Press Ctrl+C in terminal to stop sync
        </div>
      </div>
    </main>
  )
}
