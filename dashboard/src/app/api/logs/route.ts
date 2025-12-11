import { NextRequest, NextResponse } from 'next/server'
import Docker from 'dockerode'

const docker = new Docker({ socketPath: '/var/run/docker.sock' })

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const tail = parseInt(searchParams.get('tail') || '100')
  const containerName = searchParams.get('container') || 'rs-onyx-connector'

  try {
    const container = docker.getContainer(containerName)

    const logs = await container.logs({
      stdout: true,
      stderr: true,
      tail: tail,
      timestamps: false,
    })

    // Parse docker logs (remove header bytes)
    const logString = logs.toString('utf8')
    const lines = logString
      .split('\n')
      .map(line => {
        // Remove docker log header (8 bytes)
        if (line.length > 8) {
          return line.substring(8).replace(/[\x00-\x08]/g, '')
        }
        return line
      })
      .filter(line => line.trim())

    return NextResponse.json({
      container: containerName,
      lines: lines,
      count: lines.length,
    })
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Failed to fetch logs' },
      { status: 500 }
    )
  }
}
