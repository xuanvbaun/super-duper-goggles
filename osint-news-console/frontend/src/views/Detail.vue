<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { fetchNewsDetail } from '../api.js'

const route = useRoute()
const article = ref(null)
const loading = ref(true)

function scoreLabel(score) {
  if (!score) return ''
  if (score >= 60) return '高可信'
  if (score >= 30) return '中可信'
  return '低可信'
}
function scoreBgClass(score) {
  if (!score) return ''
  if (score >= 60) return 'score-bg-high'
  if (score >= 30) return 'score-bg-mid'
  return 'score-bg-low'
}

onMounted(async () => {
  try {
    const res = await fetchNewsDetail(route.params.id)
    article.value = res.data
  } catch (e) {
    console.error('加载详情失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div v-if="loading" class="loading">
      <div class="spinner"></div>
    </div>

    <div v-else-if="!article" class="empty">
      <p style="font-size:48px;margin-bottom:8px">🗞️</p>
      <p>此文已过期或不存在</p>
      <p style="font-size:14px;color:var(--text-muted);margin-top:4px">新闻数据仅保留 7 天</p>
    </div>

    <!-- ── 文章详情 ── -->
    <article v-else style="max-width:800px">
      <!-- 标题区 -->
      <header style="margin-bottom:28px;padding-bottom:20px;border-bottom:2px solid var(--accent)">
        <h1 style="font-family:var(--serif);font-size:2rem;font-weight:900;line-height:1.3;letter-spacing:-0.5px;margin-bottom:14px">
          {{ article.title }}
        </h1>

        <div style="display:flex;flex-wrap:wrap;gap:14px;font-family:var(--sans);font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px">
          <span>{{ article.source_name }}</span>
          <span v-if="article.ai_category">{{ article.ai_category }}</span>
          <span v-if="article.published_at">{{ article.published_at?.slice(0, 16) }}</span>
        </div>

        <div v-if="article.rule_score"
          :class="['detail-score', scoreBgClass(article.rule_score)]"
          style="display:inline-block;padding:6px 16px;font-family:var(--sans);font-size:13px;font-weight:700">
          可信度 {{ article.rule_score }} · {{ scoreLabel(article.rule_score) }}
        </div>
      </header>

      <!-- 标签 -->
      <div v-if="article.ai_tags?.length" style="margin-bottom:24px;display:flex;gap:8px;flex-wrap:wrap">
        <span class="tag" v-for="tag in article.ai_tags.filter(t=>!['Mock','开发阶段'].includes(t))" :key="tag">{{ tag }}</span>
      </div>

      <!-- 新闻摘要 -->
      <section v-if="article.raw_summary || article.ai_summary" style="margin-bottom:24px;background:var(--paper-white);padding:20px;border:1px solid var(--border-light)">
        <h3 style="font-family:var(--sans);font-size:10px;text-transform:uppercase;letter-spacing:2px;color:var(--text-muted);margin-bottom:10px">
          新闻摘要
        </h3>
        <p style="font-family:var(--serif);font-size:0.95rem;line-height:1.75;color:#555">
          {{ article.raw_summary || article.ai_summary }}
        </p>
      </section>

      <!-- 原文链接 -->
      <a :href="article.url" target="_blank"
        style="display:inline-flex;align-items:center;gap:6px;font-family:var(--sans);font-size:13px;text-transform:uppercase;letter-spacing:1px;padding:10px 20px;border:1px solid var(--accent);color:var(--accent);transition:all 0.2s">
        阅读原文 →
      </a>
    </article>
  </div>
</template>
