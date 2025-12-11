import { NextResponse } from 'next/server'
import Docker from 'dockerode'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'

const docker = new Docker({ socketPath: '/var/run/docker.sock' })

interface SyncProgress {
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

export async function GET() {
  try {
    const container = docker.getContainer('rs-onyx-connector')

    // Get recent logs to parse progress
    const logs = await container.logs({
      stdout: true,
      stderr: true,
      tail: 50,
      timestamps: true,
    })

    const logString = logs.toString('utf8')
    const lines = logString.split('\n').filter(l => l.trim())

    // Parse progress from logs
    let documents = 0
    let sent = 0
    let failed = 0
    let phase = 'unknown'
    let lastTimestamp = ''

    // Look for progress line: "Documents: 900 | Sent to Onyx: 900 | Failed: 0"
    for (const line of lines) {
      const progressMatch = line.match(
        /Documents:\s*(\d+)\s*\|\s*Sent to Onyx:\s*(\d+)\s*\|\s*Failed:\s*(\d+)/
      )
      if (progressMatch) {
        documents = parseInt(progressMatch[1])
        sent = parseInt(progressMatch[2])
        failed = parseInt(progressMatch[3])
      }

      // Detect phase
      if (line.includes('Building customer documents')) {
        phase = 'customers'
      } else if (line.includes('Building asset documents')) {
        phase = 'assets'
      } else if (line.includes('Yielding ticket batch') || line.includes('Fetched tickets')) {
        phase = 'tickets'
      } else if (line.includes('Full load complete')) {
        phase = 'complete'
      }

      // Get timestamp
      const tsMatch = line.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/)
      if (tsMatch) {
        lastTimestamp = tsMatch[1]
      }
    }

    // Estimate rate (rough calculation based on typical throughput)
    const rate = 70 // ~70 docs/min observed

    // Estimate remaining based on phase
    let estimatedTotal = 22000 // tickets
    if (phase === 'customers') {
      estimatedTotal = 1390
    } else if (phase === 'assets') {
      estimatedTotal = 100
    }

    const remaining = Math.max(0, estimatedTotal - documents)
    const estimatedMinutes = Math.ceil(remaining / rate)

    const progress: SyncProgress = {
      documents_processed: documents,
      sent_to_onyx: sent,
      failed: failed,
      rate_per_minute: rate,
      estimated_remaining_minutes: estimatedMinutes,
      phase: phase,
      customers_complete: phase !== 'customers' && documents > 0,
      assets_complete: phase === 'tickets' || phase === 'complete',
      tickets_complete: phase === 'complete',
      last_activity: lastTimestamp,
    }

    return NextResponse.json(progress)
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Failed to get sync status' },
      { status: 500 }
    )
  }
}
