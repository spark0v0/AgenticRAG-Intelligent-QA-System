<script setup lang="ts">
import type { Message } from '../types'
import AppIcon from './AppIcon.vue'
import AgentFlowPill from './AgentFlowPill.vue'
import MarkdownContent from './MarkdownContent.vue'
import { useClipboard } from '../composables/useClipboard'
defineProps<{ message: Message; selected: boolean }>()
defineEmits<{ inspect: [runId: string, sourceId?: string] }>()
const { copy, feedback } = useClipboard()
</script>
<template>
  <article class="message" :class="message.role">
    <div class="message-avatar" :class="{ 'assistant-avatar': message.role === 'assistant' }">
      <AppIcon :name="message.role === 'assistant' ? 'spark' : 'user'" :size="18" />
    </div>
    <div class="message-body">
      <div class="message-meta">
        <strong>{{ message.role === 'assistant' ? 'AgenticRAG' : '你' }}</strong
        ><span v-if="message.status === 'streaming'" class="status-pill"
          ><i class="live-dot"></i>生成草稿</span
        ><span v-else-if="message.status === 'success'" class="muted">{{
          message.result?.response_mode === 'live_data_notice' ? '未获取到外部证据' : '回答完成'
        }}</span>
      </div>
      <template v-if="message.role === 'user'"
        ><p class="user-text">{{ message.content }}</p>
        <div v-if="message.attachments?.length" class="message-images">
          <img
            v-for="(image, i) in message.attachments"
            :key="i"
            :src="image.data_url"
            :alt="image.filename"
            loading="lazy"
          /></div
      ></template>
      <template v-else>
        <AgentFlowPill
          :message="message"
          @inspect="message.run_id && $emit('inspect', message.run_id)"
        />
        <MarkdownContent
          v-if="message.content"
          :content="message.content"
          :streaming="message.status === 'streaming'"
          :sources="message.result?.source_map"
          @citation="message.run_id && $emit('inspect', message.run_id, $event)"
        />
        <p
          v-if="message.notice"
          class="message-notice"
          :class="{
            warning:
              message.status === 'error' ||
              message.status === 'cancelled' ||
              message.result?.model_error,
          }"
        >
          {{ message.notice }}
        </p>
        <p v-if="message.result?.evaluation?.unresolved" class="message-notice warning">
          证据检查仍有待核实项：{{ message.result.evaluation.issues.join('；') }}
        </p>
        <div
          v-if="message.content || message.status === 'error' || message.status === 'cancelled'"
          class="message-actions"
        >
          <button v-if="message.content" class="text-button" @click="copy(message.content)">
            <AppIcon name="copy" :size="14" />{{ feedback || '复制回答' }}
          </button>
          <button
            v-if="message.run_id"
            class="text-button"
            :class="{ 'is-selected': selected }"
            @click="$emit('inspect', message.run_id)"
          >
            <AppIcon name="pulse" :size="15" />执行详情<AppIcon name="right" :size="12" />
          </button>
          <button
            v-if="message.result?.source_map?.length && message.run_id"
            class="source-count text-button"
            @click="$emit('inspect', message.run_id, message.result.source_map[0]?.citation_id)"
          >
            <AppIcon name="book" :size="13" />{{ message.result.source_map.length }} 个来源
          </button>
        </div>
      </template>
    </div>
  </article>
</template>
