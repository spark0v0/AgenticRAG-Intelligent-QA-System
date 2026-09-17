<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorkbench } from '../stores/workbench'
import AppIcon from '../components/AppIcon.vue'
const store = useWorkbench()
const search = ref('')
const protocol = ref('all')
const protocols = computed(() => [...new Set(store.system?.tools.map((t) => t.protocol) ?? [])])
const tools = computed(() =>
  (store.system?.tools ?? []).filter(
    (t) =>
      (protocol.value === 'all' || t.protocol === protocol.value) &&
      `${t.name} ${t.description}`.toLowerCase().includes(search.value.toLowerCase()),
  ),
)
const names: Record<string, string> = {
  knowledge_base_search: '本地知识检索',
  knowledge_graph_search: '知识关系查询',
  web_search: '互联网搜索',
  weather_lookup: '实时天气',
  calculator: '数学计算',
  project_capability_lookup: '项目能力查询',
}
</script>
<template>
  <main class="page-view">
    <div class="page-title">
      <div>
        <span class="eyebrow">WORKSPACE / TOOLS</span>
        <h1>工具中心</h1>
        <p>已注册 {{ store.system?.tools.length ?? 0 }} 个工具</p>
      </div>
      <span class="subtle-badge">只读</span>
    </div>
    <div class="page-toolbar">
      <label class="search-field"
        ><AppIcon name="search" :size="18" /><input
          v-model="search"
          placeholder="搜索工具"
          aria-label="搜索工具"
      /></label>
      <div class="filter-tabs" aria-label="工具协议筛选">
        <button
          :class="{ active: protocol === 'all' }"
          :aria-pressed="protocol === 'all'"
          @click="protocol = 'all'"
        >
          全部
        </button>
        <button
          v-for="item in protocols"
          :key="item"
          :class="{ active: protocol === item }"
          :aria-pressed="protocol === item"
          @click="protocol = item"
        >
          {{ item }}
        </button>
      </div>
    </div>
    <p v-if="!tools.length" class="empty-page">
      {{ store.loading ? '正在加载工具…' : '暂无匹配工具' }}
    </p>
    <div class="tool-list">
      <article v-for="tool in tools" :key="tool.name" class="tool-card">
        <span class="tool-card-icon"
          ><AppIcon
            :name="
              tool.tags.includes('realtime') ? 'globe' : tool.protocol === 'mcp' ? 'layers' : 'tool'
            "
            :size="22"
        /></span>
        <div class="tool-main">
          <div class="tool-title">
            <h2>{{ names[tool.name] || tool.name }}</h2>
            <span class="protocol-badge">{{ tool.protocol }}</span>
          </div>
          <code>{{ tool.name }}</code>
          <p>{{ tool.description }}</p>
          <div class="tool-tags">
            <span v-for="tag in tool.tags" :key="tag">{{ tag }}</span>
          </div>
          <details class="schema-details">
            <summary><AppIcon name="code" :size="16" />参数 Schema</summary>
            <pre>{{ JSON.stringify(tool.schema, null, 2) }}</pre>
          </details>
        </div>
        <div class="tool-meta">
          <span><i class="live-dot"></i>已注册</span><small>连接未验证</small
          ><small>{{ tool.timeout_seconds }}s 超时</small>
        </div>
      </article>
    </div>
    <p class="page-footnote">MCP 示例服务与配置式知识图谱的结果以每次实际执行记录为准。</p>
  </main>
</template>
