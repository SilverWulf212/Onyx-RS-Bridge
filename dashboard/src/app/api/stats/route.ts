import { NextResponse } from 'next/server'
import Docker from 'dockerode'

const docker = new Docker({ socketPath: '/var/run/docker.sock' })

interface ContainerStats {
  name: string
  cpu_percent: number
  memory_usage: number
  memory_limit: number
  memory_percent: number
  status: string
}

export async function GET() {
  try {
    const containers = await docker.listContainers({ all: true })

    // Filter for relevant containers
    const relevantContainers = containers.filter(c =>
      c.Names.some(n =>
        n.includes('rs-onyx') ||
        n.includes('onyx-api') ||
        n.includes('onyx-index') ||
        n.includes('onyx-background')
      )
    )

    const stats: ContainerStats[] = await Promise.all(
      relevantContainers.map(async c => {
        const container = docker.getContainer(c.Id)
        const name = c.Names[0].replace('/', '')

        if (c.State !== 'running') {
          return {
            name,
            cpu_percent: 0,
            memory_usage: 0,
            memory_limit: 0,
            memory_percent: 0,
            status: c.State,
          }
        }

        try {
          const statsData = await container.stats({ stream: false })

          // Calculate CPU percentage
          const cpuDelta =
            statsData.cpu_stats.cpu_usage.total_usage -
            statsData.precpu_stats.cpu_usage.total_usage
          const systemDelta =
            statsData.cpu_stats.system_cpu_usage -
            statsData.precpu_stats.system_cpu_usage
          const cpuCount = statsData.cpu_stats.online_cpus || 1
          const cpuPercent =
            systemDelta > 0 ? (cpuDelta / systemDelta) * cpuCount * 100 : 0

          // Memory
          const memUsage = statsData.memory_stats.usage || 0
          const memLimit = statsData.memory_stats.limit || 1
          const memPercent = (memUsage / memLimit) * 100

          return {
            name,
            cpu_percent: Math.round(cpuPercent * 10) / 10,
            memory_usage: memUsage,
            memory_limit: memLimit,
            memory_percent: Math.round(memPercent * 10) / 10,
            status: c.State,
          }
        } catch {
          return {
            name,
            cpu_percent: 0,
            memory_usage: 0,
            memory_limit: 0,
            memory_percent: 0,
            status: c.State,
          }
        }
      })
    )

    return NextResponse.json({ containers: stats })
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Failed to fetch stats' },
      { status: 500 }
    )
  }
}
