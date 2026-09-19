<script setup lang="ts">
import type { KnowledgeDocument } from '../../types/knowledge'
import { activeIndex, indexLabels } from '../../types/knowledge'
defineProps<{ documents: KnowledgeDocument[]; busy: boolean }>()
defineEmits<{ action: [doc: KnowledgeDocument, action: 'retry' | 'cancel' | 'delete'] }>()
function status(doc: KnowledgeDocument) {
  return doc.status === 'completed' && doc.job?.status !== 'completed'
    ? doc.job?.status || doc.status
    : doc.status
}
</script>
<template>
  <div class="kb-table-wrap">
    <table class="kb-table">
      <thead>
        <tr>
          <th scope="col">文档</th>
          <th scope="col">索引状态</th>
          <th scope="col">片段</th>
          <th scope="col">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="doc in documents" :key="doc.id">
          <td>
            <strong class="kb-filename" :title="doc.name">{{ doc.name }}</strong
            ><small
              >{{ doc.ext.slice(1).toUpperCase() }} · {{ (doc.size / 1024).toFixed(1) }} KiB</small
            >
          </td>
          <td>
            <span class="kb-status" :class="status(doc)">{{ indexLabels[status(doc)] }}</span
            ><small v-if="doc.job?.status === 'indexing' && doc.job.total"
              >{{ doc.job.processed }} / {{ doc.job.total }} 片段</small
            ><small v-if="doc.status === 'completed' && doc.job?.status !== 'completed'"
              >已提交的旧索引仍可用</small
            ><small v-if="doc.needs_rebuild">配置已变化，请重建索引</small>
            <p v-if="doc.error || doc.job?.error" class="kb-error">
              {{ doc.error || doc.job?.error }}
            </p>
          </td>
          <td>{{ doc.chunk_count }}</td>
          <td>
            <div class="kb-row-actions">
              <button
                v-if="
                  activeIndex(doc.job?.status) &&
                  !['deleting', 'delete_failed'].includes(doc.status)
                "
                :disabled="busy"
                @click="$emit('action', doc, 'cancel')"
              >
                取消
              </button>
              <button
                v-else-if="!['deleting', 'delete_failed'].includes(doc.status)"
                :disabled="busy"
                @click="$emit('action', doc, 'retry')"
              >
                {{ doc.status === 'completed' ? '重建' : '重试' }}
              </button>
              <button
                :disabled="busy || doc.status === 'deleting'"
                class="kb-danger"
                @click="$emit('action', doc, 'delete')"
              >
                {{ doc.status === 'delete_failed' ? '重试清理' : '删除' }}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
