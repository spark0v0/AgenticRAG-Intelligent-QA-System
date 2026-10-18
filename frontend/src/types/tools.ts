import type { Json } from './index'

export interface MCPSettings {
  name: string
  transport: 'stdio' | 'streamable_http'
  url: string
  command: string
  args: string[]
  env_names: string[]
  token_env: string
  timeout_seconds: number
}
export interface MCPTool {
  name: string
  description: string
  schema: Record<string, Json>
  read_only: boolean
}
export interface MCPServer extends MCPSettings {
  id: string
  revision: number
  enabled: boolean
  selected_tools: string[]
  tools: MCPTool[]
  checked_at: number | null
  check_ok: boolean | null
  check_message: string
  last_call: { tool: string; status: string; at: number; duration_ms?: number } | null
}
export interface ToolTrialResult {
  status: 'success' | 'error' | 'timeout'
  error: string | null
  documents: { content: string; source: string }[]
  metadata: { latency_ms: number }
}
