<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import KnowledgeField from '../components/home/KnowledgeField.vue'
import { useClipboard } from '../composables/useClipboard'
import '../styles/_home.scss'

const main = ref<HTMLElement>()
const activeTab = ref<'chat' | 'waterfall' | 'retrieval'>('chat')
const { copy, feedback } = useClipboard()

const quickStartCmd = `git clone https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System.git
cd AgenticRAG-Intelligent-QA-System
.\\start.bat`

const entries = [
  { to: '/knowledge', title: '知识库', icon: 'book' },
  { to: '/runs', title: '运行分析', icon: 'pulse' },
  { to: '/tools', title: '工具中心', icon: 'tool' },
]

const features = [
  {
    icon: 'spark',
    tag: '智能协作',
    title: '五智能体自主编排闭环',
    desc: 'Router 意图路由、Planner 任务拆解、Retriever 检索、Generator 流式生成与 Critic 质量评审，自动触发证据核验与受限纠错。',
  },
  {
    icon: 'layers',
    tag: '混合精排',
    title: '三路检索对比竞技场',
    desc: '集成 BM25 稀疏检索、BGE 向量语义检索与 RRF 互惠排名融合，并在界面中实时并排评测各路召回质量与重排得分。',
  },
  {
    icon: 'book',
    tag: '证据穿梭',
    title: '研报级事实原文溯源',
    desc: '回答中每个 [S1] 来源标签精准锚定原文片段，支持 PDF.js 站内即时阅读、缩放与页码定位，让每一次回答真正有据可依。',
  },
  {
    icon: 'pulse',
    tag: '全链路观测',
    title: '毫秒级执行时延瀑布',
    desc: '基于真实 perf_counter 捕获每个智能体阶段的起止与耗时，透明展示 Token 消耗、工具调用输入输出与执行证据链路。',
  },
]

const techTags = [
  'FastAPI',
  'Vue 3',
  'TypeScript',
  'ChromaDB',
  'BGE-small',
  'Tavily Search',
  'MCP 协议',
  'SQLite',
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
        <a href="#features" class="home-nav-item">核心特性</a>
        <a href="#showcase" class="home-nav-item">实景演示</a>
        <a href="#quickstart" class="home-nav-item">极速开始</a>
        <a
          href="https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System"
          target="_blank"
          rel="noopener noreferrer"
          class="home-nav-button"
        >
          <AppIcon name="spark" :size="15" />
          GitHub Star ⭐
        </a>
        <RouterLink to="/chat" class="home-nav-button home-nav-enter">
          工作台
          <AppIcon name="right" :size="16" />
        </RouterLink>
      </nav>
    </header>

    <main id="home-main" ref="main" class="home-main" tabindex="-1">
      <!-- Hero Section with WebGL Background -->
      <section class="home-hero" aria-labelledby="home-title">
        <KnowledgeField />

        <div class="home-copy">
          <div class="home-badge">
            <span class="badge-dot"></span>
            <span>多智能体协作 · 智能搜索与问答工作台 v1.0</span>
          </div>

          <h1 id="home-title">AgenticRAG</h1>
          <p class="home-statement">
            让大模型每一次回答，<br class="mobile-break" />
            都<span class="gradient-text">有据可查、有迹可循</span>。
          </p>
          <p class="home-description">
            面向深度研究与企业知识库的 Agentic RAG
            系统。通过路由、规划、检索、生成与评审五智能体闭环协作，连接本地文档、联网实时数据与 MCP
            外部工具。
          </p>

          <div class="home-actions">
            <RouterLink to="/chat" class="home-cta">
              进入工作台
              <AppIcon name="diagonal" :size="20" />
            </RouterLink>
            <a
              href="https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System"
              target="_blank"
              rel="noopener noreferrer"
              class="home-cta-secondary"
            >
              <AppIcon name="code" :size="18" />
              查看 GitHub 源码
            </a>
          </div>

          <div class="home-tech-pills" aria-label="核心技术栈">
            <span v-for="tag in techTags" :key="tag" class="tech-pill">{{ tag }}</span>
          </div>
        </div>
      </section>

      <!-- Section 2: Interactive Product Showcase -->
      <section id="showcase" class="home-showcase-section" aria-labelledby="showcase-title">
        <div class="section-header">
          <span class="section-tag">实景工作台视效</span>
          <h2 id="showcase-title">沉浸式工作台，重塑 Agentic 人机交互</h2>
          <p>告别黑盒与幻觉，将检索过程、决策逻辑与原文证据完整呈现在你眼前。</p>
        </div>

        <div class="showcase-card">
          <!-- Showcase Tabs -->
          <div class="showcase-tabs" role="tablist">
            <button
              type="button"
              class="showcase-tab"
              :class="{ active: activeTab === 'chat' }"
              @click="activeTab = 'chat'"
            >
              <AppIcon name="chat" :size="16" />
              智能研报与双栏证据画布
            </button>
            <button
              type="button"
              class="showcase-tab"
              :class="{ active: activeTab === 'waterfall' }"
              @click="activeTab = 'waterfall'"
            >
              <AppIcon name="pulse" :size="16" />
              五智能体执行流与时延瀑布
            </button>
            <button
              type="button"
              class="showcase-tab"
              :class="{ active: activeTab === 'retrieval' }"
              @click="activeTab = 'retrieval'"
            >
              <AppIcon name="layers" :size="16" />
              三路检索竞技场 (BM25 / BGE / RRF)
            </button>
          </div>

          <!-- Tab Content 1: Chat & Evidence Canvas -->
          <div v-if="activeTab === 'chat'" class="showcase-viewport showcase-split">
            <div class="mock-chat-pane">
              <div class="mock-msg mock-user">
                <div class="mock-avatar">U</div>
                <div class="mock-msg-content">
                  微服务网关在高并发架构下的熔断限流机制与技术选型是什么？
                </div>
              </div>

              <div class="mock-msg mock-assistant">
                <div class="mock-avatar ai">A</div>
                <div class="mock-msg-content">
                  <div class="mock-agent-pill">
                    <span class="pill-dot"></span>
                    <span class="pill-text">Router 规划分析</span>
                    <span class="pill-arr">→</span>
                    <span class="pill-text text-accent">Retriever 本地 RAG · 3篇来源</span>
                    <span class="pill-arr">→</span>
                    <span class="pill-text text-success">Critic 校验通过 100%</span>
                    <span class="pill-timing">2.4s</span>
                  </div>

                  <div class="mock-answer-body">
                    <p>
                      在复杂分布式高并发场景下，微服务网关通常采用<strong>令牌桶算法与漏桶算法</strong>实现高精度的流量整形
                      <span class="mock-citation">[S1]</span>。
                    </p>
                    <p>
                      对于服务熔断与降级，业界主流方案通常采用 <strong>Sentinel</strong> 或
                      <strong>Resilience4j</strong
                      >，网关通过实时统计错误率或慢调用比例触发动态断路器
                      <span class="mock-citation">[S2]</span>。
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div class="mock-evidence-pane">
              <div class="mock-evidence-header">
                <AppIcon name="book" :size="15" />
                <span>技术架构规格说明书.pdf · 第 14 页</span>
                <span class="mock-match-badge">匹配度 94.8% · BGE+BM25 融合</span>
              </div>
              <div class="mock-doc-preview">
                <div class="doc-line">### 3.4 核心网关限流与熔断设计</div>
                <div class="doc-highlight">
                  "网关层采用基于滑动时间窗口的统计模型，当单节点 QPS 超过阈值时触发 Sentinel
                  熔断回退，将流量平滑导流至备用降级集群..."
                </div>
                <div class="doc-line">
                  其底层指标通过 Prometheus 实时采集，支持动态推送到配置中心实现毫秒级生效。
                </div>
              </div>
            </div>
          </div>

          <!-- Tab Content 2: Agentic Waterfall -->
          <div v-else-if="activeTab === 'waterfall'" class="showcase-viewport">
            <div class="mock-kpi-bar">
              <div class="kpi-item"><span>Query ID</span><strong>#trace-8921f</strong></div>
              <div class="kpi-item"><span>总执行耗时</span><strong>2.4s</strong></div>
              <div class="kpi-item"><span>检索轮次</span><strong>2 轮</strong></div>
              <div class="kpi-item"><span>Token 消耗</span><strong>1,420</strong></div>
              <div class="kpi-item">
                <span>Critic 核验</span><strong class="text-success">98.4% (通过)</strong>
              </div>
            </div>

            <div class="mock-waterfall-list">
              <div class="mock-wf-row">
                <span class="wf-name">1. Router 意图路由</span>
                <div class="wf-bar-track">
                  <div class="wf-bar bar-router" style="left: 0%; width: 8%">18ms</div>
                </div>
              </div>
              <div class="mock-wf-row">
                <span class="wf-name">2. Planner 规划拆解 (2个子查询)</span>
                <div class="wf-bar-track">
                  <div class="wf-bar bar-planner" style="left: 8%; width: 14%">210ms</div>
                </div>
              </div>
              <div class="mock-wf-row">
                <span class="wf-name">3. Retriever 多路双轴检索</span>
                <div class="wf-bar-track">
                  <div class="wf-bar bar-retriever" style="left: 22%; width: 48%">1,240ms</div>
                </div>
              </div>
              <div class="mock-wf-row">
                <span class="wf-name">4. Generator 综合流式回答</span>
                <div class="wf-bar-track">
                  <div class="wf-bar bar-generator" style="left: 70%; width: 22%">760ms</div>
                </div>
              </div>
              <div class="mock-wf-row">
                <span class="wf-name">5. Critic 交叉校验与自纠错</span>
                <div class="wf-bar-track">
                  <div class="wf-bar bar-critic" style="left: 92%; width: 8%">180ms</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Tab Content 3: Tri-Retrieval Arena -->
          <div v-else class="showcase-viewport">
            <div class="mock-arena-query">
              <span class="query-label">测试查询 Query:</span>
              <span class="query-content">"微服务网关在高并发场景下的熔断限流机制是什么？"</span>
            </div>

            <div class="mock-arena-grid">
              <div class="arena-col">
                <div class="col-head">关键词检索 (BM25 稀疏)</div>
                <div class="arena-card rank-gold">
                  <div class="card-meta">
                    <span class="badge-gold">#1 命中</span><small>得分 18.42</small>
                  </div>
                  <p>微服务网关在高并发场景下的熔断限流机制与技术选型...</p>
                </div>
                <div class="arena-card rank-silver">
                  <div class="card-meta">
                    <span class="badge-silver">#2 命中</span><small>得分 12.10</small>
                  </div>
                  <p>服务熔断限流常见中间件选型比较...</p>
                </div>
              </div>

              <div class="arena-col">
                <div class="col-head">语义向量检索 (BGE 稠密)</div>
                <div class="arena-card rank-gold">
                  <div class="card-meta">
                    <span class="badge-gold">#1 命中</span><small>相似度 0.912</small>
                  </div>
                  <p>高并发服务治理架构下的流量整形与降级策略...</p>
                </div>
                <div class="arena-card rank-silver">
                  <div class="card-meta">
                    <span class="badge-silver">#2 命中</span><small>相似度 0.887</small>
                  </div>
                  <p>基于分布式网关的熔断与容灾实践指南...</p>
                </div>
              </div>

              <div class="arena-col col-highlight">
                <div class="col-head">RRF 互惠融合精排 (最终采用)</div>
                <div class="arena-card rank-champion">
                  <div class="card-meta">
                    <span class="badge-champion">🥇 综合最佳</span><small>RRF 0.0328</small>
                  </div>
                  <p>微服务网关在高并发场景下的熔断限流机制与技术选型...</p>
                </div>
                <div class="arena-card rank-gold">
                  <div class="card-meta">
                    <span class="badge-gold">🥈 次优平衡</span><small>RRF 0.0315</small>
                  </div>
                  <p>高并发服务治理架构下的流量整形与降级策略...</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Section 3: Core Capabilities Grid -->
      <section id="features" class="home-features-section" aria-labelledby="features-title">
        <div class="section-header">
          <span class="section-tag">核心能力矩阵</span>
          <h2 id="features-title">为长程专业创作与严谨问答打造</h2>
          <p>融合智能体自主推演与确定性代码控制，保证系统每一次调用的严谨性与透明度。</p>
        </div>

        <div class="features-grid">
          <article v-for="feat in features" :key="feat.title" class="feature-card">
            <div class="feature-icon-wrapper">
              <AppIcon :name="feat.icon" :size="24" />
            </div>
            <span class="feature-tag">{{ feat.tag }}</span>
            <h3>{{ feat.title }}</h3>
            <p>{{ feat.desc }}</p>
          </article>
        </div>
      </section>

      <!-- Section 4: 60-Second Quick Start -->
      <section id="quickstart" class="home-quickstart-section" aria-labelledby="quickstart-title">
        <div class="quickstart-card">
          <div class="quickstart-text">
            <span class="section-tag">极速体验</span>
            <h2 id="quickstart-title">一键克隆，60 秒在本机跑起来</h2>
            <p>
              完全基于本机运行。预置 FastEmbed CPU 本地嵌入、FastAPI 自动化管理与 Vue 3
              前端静态托管，无需配置庞大的云端向量服务。
            </p>
            <div class="quickstart-checks">
              <div class="check-item">
                <AppIcon name="check" :size="16" /> 本地 CPU 支持 BGE 语义检索
              </div>
              <div class="check-item">
                <AppIcon name="check" :size="16" /> 兼容 OpenAI / DeepSeek / Ollama
              </div>
              <div class="check-item">
                <AppIcon name="check" :size="16" /> 支持 stdio / HTTP MCP 工具协议
              </div>
            </div>
          </div>

          <div class="quickstart-terminal">
            <div class="terminal-bar">
              <span class="t-dot red"></span>
              <span class="t-dot yellow"></span>
              <span class="t-dot green"></span>
              <span class="terminal-title">PowerShell 7</span>
              <button class="terminal-copy" @click="copy(quickStartCmd)">
                <AppIcon name="copy" :size="14" />
                {{ feedback || '复制代码' }}
              </button>
            </div>
            <pre class="terminal-body"><code><span class="t-comment"># 1. 克隆代码仓库</span>
git clone https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System.git
cd AgenticRAG-Intelligent-QA-System

<span class="t-comment"># 2. 一键启动后端与静态服务</span>
.\start.bat</code></pre>
          </div>
        </div>
      </section>

      <!-- Bottom Destinations Row (Preserving existing workflow links for full compatibility) -->
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

    <!-- Footer -->
    <footer class="home-footer">
      <div class="footer-content">
        <div class="footer-left">
          <div class="footer-brand">
            <strong>AgenticRAG</strong>
            <small>基于 Agentic 架构的智能搜索与问答系统</small>
          </div>
          <p class="footer-desc">让大模型的每一次回答，都有据可查、有迹可循。</p>
        </div>
        <div class="footer-links">
          <a
            href="https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System"
            target="_blank"
            rel="noopener noreferrer"
            >GitHub 仓库</a
          >
          <a href="http://127.0.0.1:8000/docs" target="_blank">Swagger API 文档</a>
          <RouterLink to="/knowledge">知识库管理</RouterLink>
          <RouterLink to="/runs">运行分析瀑布</RouterLink>
          <RouterLink to="/chat">问答工作台</RouterLink>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© 2026 spark0v0 / AgenticRAG Project. MIT License.</span>
        <span>面向企业与个人研究者的开源本地化智能问答套件</span>
      </div>
    </footer>
  </div>
</template>
