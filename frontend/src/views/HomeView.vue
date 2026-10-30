<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import KnowledgeField from '../components/home/KnowledgeField.vue'
import '../styles/_home.scss'

const main = ref<HTMLElement>()

const entries = [
  { to: '/knowledge', title: '知识库', icon: 'book' },
  { to: '/runs', title: '运行分析', icon: 'pulse' },
  { to: '/tools', title: '工具中心', icon: 'tool' },
]
</script>

<template>
  <div class="home-page">
    <a class="home-skip" href="#home-main" @click.prevent="main?.focus()">跳到主要内容</a>

    <!-- Top Navigation Bar -->
    <header class="home-nav">
      <RouterLink to="/" class="home-brand" aria-label="AgenticRAG 主页">
        <svg viewBox="0 0 32 32" aria-hidden="true" class="home-brand-symbol">
          <path d="m5 25 11-19 11 19M10 18h12M16 6v19" />
          <circle cx="5" cy="25" r="2" />
          <circle cx="27" cy="25" r="2" />
          <circle cx="16" cy="6" r="2" />
          <circle cx="16" cy="25" r="2" />
        </svg>
        <span>AgenticRAG</span>
      </RouterLink>

      <nav class="home-nav-links" aria-label="主页导航">
        <a
          href="https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System"
          target="_blank"
          rel="noopener noreferrer"
          class="home-nav-button"
        >
          GitHub
          <AppIcon name="diagonal" :size="14" />
        </a>
        <RouterLink to="/chat" class="home-nav-button home-nav-enter">
          工作台
          <AppIcon name="right" :size="16" />
        </RouterLink>
      </nav>
    </header>

    <main id="home-main" ref="main" class="home-main" tabindex="-1">
      <!-- Full-bleed Cinematic Hero Section with Interactive WebGL Canvas -->
      <section class="home-hero" aria-labelledby="home-title">
        <KnowledgeField />

        <div class="home-copy">
          <h1 id="home-title">AgenticRAG</h1>
          <p class="home-statement">让答案，有据可循。</p>
          <p class="home-description">连接本地知识、网络与工具。</p>

          <div class="home-actions">
            <RouterLink to="/chat" class="home-cta">
              进入工作台
              <AppIcon name="diagonal" :size="20" />
            </RouterLink>
          </div>
        </div>
      </section>

      <!-- Bottom Destinations Dock -->
      <nav class="home-destinations" aria-label="探索工作台">
        <RouterLink
          v-for="entry in entries"
          :key="entry.to"
          :to="entry.to"
          class="home-destination"
        >
          <AppIcon :name="entry.icon" :size="21" />
          <span class="home-destination-title">{{ entry.title }}</span>
          <AppIcon name="diagonal" :size="19" class="home-destination-arrow" />
        </RouterLink>
      </nav>
    </main>
  </div>
</template>
