<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { marketAnomalies, marketBreadth, marketIndexes, marketMeta } from '../marketData.js'

const router = useRouter()
const activePage = ref(0)
const pointer = { active: false, x: 0, y: 0 }

const maxChange = Math.max(...marketIndexes.map(item => Math.abs(item.change)), 0.01)
const breadthTotal = marketBreadth.rising + marketBreadth.falling + marketBreadth.flat

function barStyle(change) {
  const width = Math.max(7, (Math.abs(change) / maxChange) * 46)
  return change >= 0
    ? { left: '50%', width: `${width}%` }
    : { right: '50%', width: `${width}%` }
}

function setPage(page) {
  activePage.value = Math.max(0, Math.min(1, page))
}

function onPointerDown(event) {
  if (event.target.closest('.market-page-dot')) return
  pointer.active = true
  pointer.x = event.clientX
  pointer.y = event.clientY
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function onPointerUp(event) {
  if (!pointer.active || event.target.closest('.market-page-dot')) return
  pointer.active = false
  const deltaX = event.clientX - pointer.x
  const deltaY = event.clientY - pointer.y
  const horizontalSwipe = Math.abs(deltaX) > 36 && Math.abs(deltaX) > Math.abs(deltaY) * 1.15

  if (horizontalSwipe) {
    setPage(deltaX < 0 ? activePage.value + 1 : activePage.value - 1)
    return
  }

  if (Math.abs(deltaX) < 8 && Math.abs(deltaY) < 8) {
    router.push('/market')
  }
}

function onKeydown(event) {
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    setPage(activePage.value - 1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    setPage(activePage.value + 1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    router.push('/market')
  }
}
</script>

<template>
  <section
    class="market-snapshot"
    role="link"
    tabindex="0"
    aria-label="市场概览，点击进入完整市场页面，左右滑动切换内容"
    @pointerdown="onPointerDown"
    @pointerup="onPointerUp"
    @pointercancel="pointer.active = false"
    @keydown="onKeydown"
  >
    <div class="market-page-dots" aria-label="市场卡片分页">
      <button
        v-for="page in 2"
        :key="page"
        type="button"
        class="market-page-dot"
        :class="{ active: activePage === page - 1 }"
        :aria-label="`显示第 ${page} 页`"
        :aria-current="activePage === page - 1 ? 'page' : undefined"
        @pointerdown.stop
        @pointerup.stop
        @click.stop="setPage(page - 1)"
      ></button>
    </div>

    <div class="snapshot-pages" :style="{ transform: `translateX(-${activePage * 50}%)` }">
      <div class="snapshot-page snapshot-index-page">
        <div v-for="item in marketIndexes" :key="item.code" class="snapshot-index-row">
          <span class="snapshot-index-name">{{ item.name }}</span>
          <span :class="['snapshot-index-change', item.change >= 0 ? 'market-up' : 'market-down']">
            {{ item.change >= 0 ? '+' : '' }}{{ item.change.toFixed(2) }}%
          </span>
          <span class="snapshot-divergence" aria-hidden="true">
            <i class="snapshot-zero"></i>
            <i
              :class="['snapshot-bar', item.change >= 0 ? 'bar-up' : 'bar-down']"
              :style="barStyle(item.change)"
            ></i>
          </span>
        </div>

        <div class="market-breadth-labels">
          <span>上涨 {{ marketBreadth.rising }}</span>
          <span>下跌 {{ marketBreadth.falling }}</span>
        </div>
        <div class="market-breadth-bar" aria-label="上涨与下跌股票数量占比">
          <i class="breadth-up" :style="{ width: `${marketBreadth.rising / breadthTotal * 100}%` }"></i>
          <i class="breadth-flat" :style="{ width: `${marketBreadth.flat / breadthTotal * 100}%` }"></i>
          <i class="breadth-down" :style="{ width: `${marketBreadth.falling / breadthTotal * 100}%` }"></i>
        </div>
      </div>

      <div class="snapshot-page snapshot-anomaly-page">
        <article v-for="item in marketAnomalies" :key="item.time + item.title" class="snapshot-anomaly">
          <i :class="['anomaly-icon', `tone-${item.tone}`]"></i>
          <div>
            <div class="snapshot-anomaly-title">{{ item.title }}</div>
            <div class="snapshot-anomaly-detail">{{ item.time }} · {{ item.detail }}</div>
          </div>
        </article>
      </div>
    </div>

    <span class="market-demo-label">{{ marketMeta.label }}</span>
  </section>
</template>
