<script setup lang="ts">
import { useWorkbench } from '../stores/workbench'
import AppIcon from '../components/AppIcon.vue'
const store = useWorkbench()
function time(value?: number) {
  return value ? new Date(value * 1000).toLocaleString('zh-CN') : '本次启动后暂无成功调用'
}
</script>
<template>
  <main class="page-view">
    <div class="page-title">
      <div>
        <span class="eyebrow">WORKSPACE / SYSTEM</span>
        <h1>系统概览</h1>
        <p>模型档案与服务状态</p>
      </div>
      <button class="secondary-button" :disabled="store.loading" @click="store.initialize()">
        <AppIcon name="refresh" :size="16" />刷新状态
      </button>
    </div>
    <div class="overview-grid">
      <div>
        <AppIcon name="pulse" :size="22" /><span>工作台服务</span
        ><strong>{{ store.system && !store.error ? '已连接' : '未连接' }}</strong>
      </div>
      <div>
        <AppIcon name="layers" :size="22" /><span>已注册工具</span
        ><strong>{{ store.system?.tools.length ?? '—' }}<em>个</em></strong>
      </div>
      <div>
        <AppIcon name="chat" :size="22" /><span>历史会话</span
        ><strong>{{ store.sessions.length }}<em>组</em></strong>
      </div>
    </div>
    <section class="settings-section">
      <div class="section-heading">
        <h2>模型档案</h2>
        <span class="subtle-badge">只读</span>
      </div>
      <div class="model-table-wrap">
        <table class="model-table">
          <thead>
            <tr>
              <th>模型 / 提供方</th>
              <th>图片输入</th>
              <th>回答模式</th>
              <th>配置状态</th>
              <th>调用记录</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="profile in store.system?.model_profiles" :key="profile.id">
              <td>
                <strong>{{ profile.label }}</strong
                ><small>{{ profile.provider }} · {{ profile.model_name }}</small>
              </td>
              <td>{{ profile.supports_vision ? '配置声明支持' : '不支持' }}</td>
              <td>{{ profile.supports_streaming ? '真实流式' : '完整结果' }}</td>
              <td>
                <span class="status-badge" :class="{ ready: profile.configured }">{{
                  profile.configured ? '已配置' : '未配置'
                }}</span>
              </td>
              <td>
                <span>{{ profile.connection_verified ? '调用成功' : '尚未验证' }}</span
                ><small>{{ time(profile.last_success_at) }}</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!store.system?.model_profiles.length" class="empty-page">暂无模型档案</p>
    </section>
    <section class="settings-section">
      <h2>运行边界</h2>
      <dl class="system-notes">
        <div>
          <dt>质量评审</dt>
          <dd>Critic 使用规则评分作为修订参考，不代表事实准确率。</dd>
        </div>
        <div>
          <dt>外部依赖</dt>
          <dd>网络搜索、天气与模型供应方的可用性以本轮调用结果为准。</dd>
        </div>
        <div>
          <dt>停止生成</dt>
          <dd>
            取消本轮后续任务并关闭流连接；同步工具请求可能持续到超时，供应方计算与计费状态不由工作台保证。
          </dd>
        </div>
        <div>
          <dt>会话存储</dt>
          <dd>本机 SQLite 保存消息与运行记录，原有 JSON 历史兼容导入。</dd>
        </div>
      </dl>
    </section>
  </main>
</template>
