<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <!-- 顶部导航 -->
  <header class="nav-bar">
    <span class="nav-title">📰 OSINT 新闻控制台</span>
    <nav class="nav-links">
      <router-link to="/">首页</router-link>
      <router-link to="/stats">统计</router-link>
    </nav>
  </header>

  <!-- 页面内容 -->
  <router-view />

  <!-- 底部导航（手机） -->
  <nav class="bottom-nav">
    <router-link to="/">
      <span class="icon">📋</span>
      新闻
    </router-link>
    <router-link to="/stats">
      <span class="icon">📊</span>
      统计
    </router-link>
  </nav>
</template>
