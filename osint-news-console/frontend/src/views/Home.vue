<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchNews, getDailyUrl } from '../api.js'

const route = useRoute()
const router = useRouter()
const SCROLL_KEY = 'osint_home_scroll'

const articles = ref([])
const loading = ref(true)
const error = ref('')
const page = ref(1)
const total = ref(0)
const pages = ref(0)
const searchQuery = ref('')
const viewMode = ref('today')

// 分类从 URL 读取，返回时保持状态
const selectedCategory = ref(route.query.category || '')
const categories = ['全部', '综合', '科技', '安全', '财经', '国际', '社会', '法律', '军事', '其他']

const headline = computed(() => articles.value[0] || null)
const mainArticles = computed(() => articles.value.length > 1 ? articles.value.slice(1) : [])

function setCategory(cat) {
  const val = cat === '全部' ? '' : cat
  selectedCategory.value = val
  page.value = 1
  // 同步到 URL
  if (val) {
    router.replace({ query: { category: val } })
  } else {
    router.replace({ query: {} })
  }
  loadNews()
}

function switchView(mode) {
  viewMode.value = mode
  page.value = 1
  searchQuery.value = ''
  loadNews()
}

async function loadNews() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value, size: 20 }
    if (selectedCategory.value) params.category = selectedCategory.value
    if (searchQuery.value) params.search = searchQuery.value
    if (viewMode.value === 'today') params.date = 'today'
    const res = await fetchNews(params)
    articles.value = res.data.items
    total.value = res.data.total
    pages.value = res.data.pages
  } catch (e) {
    console.error('加载新闻失败:', e)
    error.value = e.message || '网络请求失败，请确认后端已启动'
  } finally {
    loading.value = false
  }
}

function search() { page.value = 1; loadNews() }
function prevPage() { if (page.value > 1) { page.value--; loadNews(); } }
function nextPage() { if (page.value < pages.value) { page.value++; loadNews(); } }

function scoreClass(score) {
  if (!score) return ''
  if (score >= 60) return 'score-high'
  if (score >= 30) return 'score-mid'
  return 'score-low'
}

onMounted(() => {
  if (route.query.category) selectedCategory.value = route.query.category
  loadNews()

  // 恢复滚动位置
  const saved = sessionStorage.getItem(SCROLL_KEY)
  if (saved) {
    setTimeout(() => {
      window.scrollTo({ top: parseInt(saved), behavior: 'instant' })
    }, 100)
  }
})

// 监听浏览器后退/前进
window.addEventListener('popstate', () => {
  const saved = sessionStorage.getItem(SCROLL_KEY)
  if (saved) window.scrollTo({ top: parseInt(saved), behavior: 'instant' })
})

onBeforeUnmount(() => {
  sessionStorage.setItem(SCROLL_KEY, String(window.scrollY))
})
</script>

<template>
  <div class="page">
    <!-- 搜索栏 -->
    <div class="search-bar">
      <input v-model="searchQuery" placeholder="搜索新闻标题..." @keyup.enter="search" />
      <button @click="search">搜索</button>
    </div>

    <!-- 分类导航 -->
    <div class="category-filter">
      <button v-for="cat in categories" :key="cat"
        :class="{ active: selectedCategory === cat || (cat === '全部' && !selectedCategory) }"
        @click="setCategory(cat)">{{ cat }}</button>
    </div>

    <!-- 今日/往期 + 日报 -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid var(--accent)">
      <div style="display:flex;gap:0">
        <button :class="viewMode === 'today' ? 'btn-primary' : 'btn-secondary'" @click="switchView('today')" style="border-right:none">今日新闻</button>
        <button :class="viewMode === 'all' ? 'btn-primary' : 'btn-secondary'" @click="switchView('all')">往期存档</button>
      </div>
      <a :href="getDailyUrl()" target="_blank" style="font-family:var(--sans);font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--accent);text-decoration:none;border:1px solid var(--accent);padding:6px 14px">📄 昨日日报</a>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading"><div class="spinner"></div><p style="margin-top:12px">新闻正在排版中...</p></div>

    <!-- 错误 -->
    <div v-else-if="error" class="empty">
      <p style="font-size:48px;margin-bottom:8px">⚠️</p>
      <p style="color:var(--accent);font-weight:700">印刷机故障</p>
      <p style="font-size:14px;color:var(--text-muted);margin:4px 0 20px">{{ error }}</p>
      <button class="btn-primary" @click="loadNews">重新排版</button>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!articles.length" class="empty">
      <p style="font-size:48px;margin-bottom:8px">📰</p>
      <p>{{ viewMode === 'today' ? '今日尚未排印' : '暂无往期新闻' }}</p>
      <p style="font-size:14px;color:var(--text-muted);margin-top:4px">{{ viewMode === 'today' ? '编辑正在采集新闻，稍后再来' : '数据保留 7 天，过期自动清理' }}</p>
      <button v-if="viewMode === 'today'" class="btn-secondary" @click="switchView('all')" style="margin-top:20px">查看往期存档</button>
      <button v-else class="btn-secondary" @click="loadNews" style="margin-top:20px">刷新</button>
    </div>

    <!-- 报纸内容 -->
    <div v-else class="news-grid">
      <div class="main-column">
        <!-- 头条 -->
        <router-link v-if="headline" :to="`/news/${headline.id}`" class="news-card headline-card">
          <div class="card-meta">
            <span>{{ headline.source_name }}</span>
            <span v-if="headline.ai_category">{{ headline.ai_category }}</span>
            <span v-if="headline.published_at">{{ headline.published_at?.slice(0, 10) }}</span>
          </div>
          <h2 class="card-title">{{ headline.title }}</h2>
          <div class="card-summary" v-if="headline.raw_summary">{{ headline.raw_summary }}</div>
          <div class="card-tags" v-if="headline.ai_tags?.length">
            <span class="tag" v-for="tag in headline.ai_tags.filter(t=>!['Mock','开发阶段'].includes(t)).slice(0, 5)" :key="tag">{{ tag }}</span>
          </div>
        </router-link>

        <!-- 其余新闻 -->
        <router-link v-for="article in mainArticles" :key="article.id" :to="`/news/${article.id}`" class="news-card">
          <div class="card-meta">
            <span>{{ article.source_name }}</span>
            <span v-if="article.ai_category">{{ article.ai_category }}</span>
            <span v-if="article.published_at">{{ article.published_at?.slice(0, 10) }}</span>
            <span v-if="article.rule_score" :class="scoreClass(article.rule_score)" style="font-weight:700">{{ article.rule_score }}分</span>
          </div>
          <h2 class="card-title">{{ article.title }}</h2>
          <div class="card-summary" v-if="article.raw_summary">{{ article.raw_summary }}</div>
          <div class="card-tags" v-if="article.ai_tags?.length">
            <span class="tag" v-for="tag in article.ai_tags.filter(t=>!['Mock','开发阶段'].includes(t)).slice(0, 4)" :key="tag">{{ tag }}</span>
          </div>
        </router-link>

        <div v-if="pages > 1" class="pagination">
          <button @click="prevPage" :disabled="page <= 1">← 前页</button>
          <span>第 {{ page }} 版 · 共 {{ pages }} 版</span>
          <button @click="nextPage" :disabled="page >= pages">后页 →</button>
        </div>
      </div>

      <!-- 侧栏 -->
      <aside class="sidebar">
        <h3>📊 今日版面</h3>
        <div class="side-item">{{ viewMode === 'today' ? '今日已收录' : '存档共' }} <strong>{{ total }}</strong> 篇</div>
        <div class="side-item" v-if="viewMode === 'today'">往期存档可查看 7 天内全部新闻</div>
        <div class="side-item" style="padding-top:12px;border-top:1px solid var(--border-light)">
          <a :href="getDailyUrl()" target="_blank" style="font-size:0.85rem;font-weight:700">📄 查看昨日日报</a>
          <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">浏览器打开后 Ctrl+P 即可另存 PDF</div>
        </div>
        <div class="side-item" style="font-size:0.82rem;color:var(--text-muted)">数据保留 7 天 · 每日凌晨清理</div>
      </aside>
    </div>
  </div>
</template>
