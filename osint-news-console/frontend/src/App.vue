<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isLocalAccess = ['127.0.0.1', 'localhost', '::1'].includes(window.location.hostname)
const pageTitle = computed(() => {
  if (route.path.startsWith('/market')) return '市场观察'
  if (route.path.startsWith('/stats')) return '来源状态'
  if (route.path.startsWith('/news/')) return '新闻详情'
  return '实时新闻'
})
</script>

<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <router-link to="/" class="app-brand" aria-label="返回新闻首页">
        <span class="brand-mark">O</span>
        <span><strong>OSINT</strong><small>新闻控制台</small></span>
      </router-link>

      <nav class="side-nav" aria-label="主要导航">
        <router-link to="/" exact-active-class="active"><i>▤</i><span>实时新闻</span></router-link>
        <router-link to="/market" active-class="active"><i>◉</i><span>市场观察</span></router-link>
        <router-link to="/stats" active-class="active"><i>◌</i><span>来源状态</span></router-link>
        <a v-if="isLocalAccess" href="/device-admin"><i>▣</i><span>设备管理</span><small>仅本机</small></a>
      </nav>

      <div class="sidebar-foot">
        <span class="live-dot"></span>
        <div><strong>本地服务运行中</strong><small>数据保留 7 天</small></div>
      </div>
    </aside>

    <main class="app-main">
      <header class="app-topbar">
        <div>
          <p class="topbar-kicker">OSINT NEWS CONSOLE</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="topbar-status">
          <span><i class="live-dot"></i>服务正常</span>
          <span class="topbar-device">本地部署</span>
        </div>
      </header>
      <router-view />
    </main>

    <nav class="bottom-nav" aria-label="移动端导航">
      <router-link to="/" exact-active-class="active"><span class="icon">▤</span>新闻</router-link>
      <router-link to="/market" active-class="active"><span class="icon">◉</span>市场</router-link>
      <router-link to="/stats" active-class="active"><span class="icon">◌</span>来源</router-link>
      <a v-if="isLocalAccess" href="/device-admin"><span class="icon">▣</span>设备</a>
    </nav>
  </div>
</template>
