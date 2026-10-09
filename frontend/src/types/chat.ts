import type { ExecutionEvent, ImageAttachment, Message, RunStatus, SearchScope } from './index'

// Editable conversation selections are separate from the immutable request of each run.
export interface Conversation {
  id: string
  title: string
  knowledgeBaseId?: string
  searchScope?: SearchScope
  modelProfile?: string
  thinkingMode?: string
  messages: Message[]
  events: ExecutionEvent[]
  status: RunStatus
  activeRun?: string
  draft: string
  images: ImageAttachment[]
  error?: string
  restoreNotice?: string
}
