export type RunStatus = 'idle' | 'submitting' | 'streaming' | 'success' | 'error' | 'cancelled'
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json }
export interface ImageAttachment {
  type: 'image'
  filename: string
  mime_type: string
  size?: number
  data_url: string
}
export interface Source {
  citation_id: string
  source: string
  score?: number
  excerpt?: string
}
export interface ToolCall {
  tool: string
  status: string
  error?: string
  document_count?: number
  metadata?: Record<string, Json>
}
export interface QueryResult {
  answer: string
  session_id: string
  run_id?: string
  session_title?: string
  turn_count?: number
  sources: string[]
  source_map?: Source[]
  evaluation_score?: number
  confidence?: number
  model?: string
  model_provider?: string
  model_profile?: string
  model_error?: string
  response_mode?: string
  routing?: { route?: string; intent?: string; reasoning?: string }
  critic_feedback?: string
  critic_suggestions?: string[]
  tool_calls?: ToolCall[]
  execution_trace?: ExecutionEvent[]
  messages?: Message[]
}
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  run_id?: string
  attachments?: ImageAttachment[]
  status?: RunStatus
  result?: QueryResult
  notice?: string
}
export interface SessionSummary {
  session_id: string
  session_title: string
  turn_count: number
  updated_at: number
  preview: string
}
export interface RunRecord {
  id: string
  session_id: string
  status: 'running' | 'success' | 'error' | 'cancelled'
  started_at: number
  finished_at?: number
  query: string
  result?: QueryResult
  error?: string
  attachments?: ImageAttachment[]
}
export interface SessionDetail {
  session_id: string
  session_title: string
  messages: Message[]
  trace: ExecutionEvent[]
  runs: RunRecord[]
}
export interface ToolSpec {
  name: string
  description: string
  protocol: string
  tags: string[]
  timeout_seconds: number
  schema: Record<string, Json>
}
export interface ModelProfile {
  id: string
  label: string
  provider: string
  model_name: string
  supports_vision: boolean
  supports_streaming: boolean
  configured: boolean
  connection_verified: boolean
  last_success_at?: number
}
export interface SystemStatus {
  status: string
  model_ready: boolean
  connection_verified: boolean
  default_model_profile: string
  model_profiles: ModelProfile[]
  tools: ToolSpec[]
  agents: string[]
  image_limits: { count: number; bytes: number }
}
export interface QueryRequest {
  query: string
  session_id: string
  run_id: string
  model_profile: string
  images: ImageAttachment[]
  context: { thinking_mode: string }
}
export type EventPayloads = {
  started: { mode: 'live' }
  answer_start: { generation: number; draft: boolean }
  sources: { items: Source[]; generation: number }
  delta: { text: string; generation: number }
  stage: {
    node: string
    stage_id: string
    round: number
    status: string
    started_at: number
    finished_at?: number
    duration_ms?: number
    input?: string
    output?: string
    metadata?: Record<string, Json>
  }
  tool: {
    call_id: string
    tool: string
    status: string
    protocol: string
    input: Record<string, Json>
    started_at: number
    finished_at?: number
    duration_ms?: number
    document_count?: number
    error?: string
    output?: string[]
  }
  transport: { mode: 'stream' | 'buffered'; message: string }
  notice: { message: string }
  info: { step: string; summary: Record<string, Json> }
  retrieval_round: { round: number; strategy: string }
  completed: { result: QueryResult }
  error: { message: string }
  cancelled: { message: string }
}
export type ExecutionEvent = {
  [K in keyof EventPayloads]: {
    type: K
    data: EventPayloads[K]
    seq: number
    run_id: string
    session_id: string
    timestamp: number
  }
}[keyof EventPayloads]
export type StageEvent = Extract<ExecutionEvent, { type: 'stage' }>
export type ToolEvent = Extract<ExecutionEvent, { type: 'tool' }>
