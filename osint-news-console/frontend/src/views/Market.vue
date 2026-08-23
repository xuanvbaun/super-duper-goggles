<script setup>
import { computed, ref } from 'vue'
import {
  heatmap,
  marketAnomalies,
  marketEvents,
  marketIndexes,
  marketMeta,
  marketTimes,
  sectors,
  sparklinePoints,
  volumeSeries,
} from '../marketData.js'

const hoverIndex = ref(null)
const selectedEvent = ref(marketEvents[1])

const normalizedSeries = computed(() => marketIndexes.slice(0, 3).map(item => {
  const first = item.series[0]
  return {
    ...item,
    values: item.series.map(value => ((value - first) / first) * 100),
  }
}))

const chartRange = computed(() => {
  const values = normalizedSeries.value.flatMap(item => item.values)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const padding = Math.max(0.08, (max - min) * 0.12)
  return { min: min - padding, max: max + padding }
})

const maxVolume = Math.max(...volumeSeries)

function chartPoints(values) {
  const { min, max } = chartRange.value
  const range = max - min || 1
  return values.map((value, index) => {
    const x = (index / Math.max(1, values.length - 1)) * 100
    const y = 40 - ((value - min) / range) * 36
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
}

function updateHover(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  hoverIndex.value = Math.round(ratio * (marketTimes.length - 1))
}

function eventLeft(index) {
  return `${index / (marketTimes.length - 1) * 100}%`
}

function tooltipLeft() {
  if (hoverIndex.value === null) return '0%'
  const ratio = hoverIndex.value / (marketTimes.length - 1)
  return `${Math.max(8, Math.min(82, ratio * 100))}%`
}

function heatClass(value) {
  if (value >= 1.5) return 'heat-strong-up'
  if (value > 0) return 'heat-up'
  if (value <= -1.5) return 'heat-strong-down'
  return 'heat-down'
}
</script>

<template>
  <div class="page market-page">
    <header class="section-heading market-heading">
      <div>
        <p class="eyebrow">Market intelligence</p>
        <h1>市场观察</h1>
        <p>用数据曲线、板块表现和新闻事件查看市场变化，不提供交易建议。</p>
      </div>
      <span class="demo-notice"><i></i>{{ marketMeta.label }}</span>
    </header>

    <div class="market-index-grid">
      <article v-for="item in marketIndexes" :key="item.code" class="market-index-card panel">
        <div class="market-index-card-head">
          <div>
            <strong>{{ item.name }}</strong>
            <small>{{ item.code }}</small>
          </div>
          <span :class="item.change >= 0 ? 'market-up' : 'market-down'">
            {{ item.change >= 0 ? '+' : '' }}{{ item.change.toFixed(2) }}%
          </span>
        </div>
        <div class="market-index-value">{{ item.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</div>
        <svg class="sparkline" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
          <polyline :points="sparklinePoints(item.series)" :stroke="item.color"></polyline>
        </svg>
      </article>
    </div>

    <div class="market-layout">
      <section class="market-chart-panel panel">
        <div class="panel-heading-row">
          <div>
            <p class="eyebrow">Intraday comparison</p>
            <h2>市场实时走势</h2>
          </div>
          <span class="demo-chip">分时 · 演示</span>
        </div>

        <div class="chart-legend">
          <span v-for="item in normalizedSeries" :key="item.code">
            <i :style="{ background: item.color }"></i>{{ item.name }}
          </span>
        </div>

        <div class="interactive-chart" @mousemove="updateHover" @mouseleave="hoverIndex = null">
          <div class="chart-grid" aria-hidden="true"></div>
          <svg viewBox="0 0 100 44" preserveAspectRatio="none" role="img" aria-label="三项指数的演示分时走势">
            <line x1="0" y1="22" x2="100" y2="22" class="chart-zero-line"></line>
            <polyline
              v-for="item in normalizedSeries"
              :key="item.code"
              :points="chartPoints(item.values)"
              :stroke="item.color"
              class="chart-line"
            ></polyline>
            <line
              v-if="hoverIndex !== null"
              :x1="hoverIndex / (marketTimes.length - 1) * 100"
              y1="0"
              :x2="hoverIndex / (marketTimes.length - 1) * 100"
              y2="44"
              class="chart-crosshair"
            ></line>
          </svg>

          <button
            v-for="event in marketEvents"
            :key="event.time"
            type="button"
            class="chart-event-marker"
            :class="{ active: selectedEvent.time === event.time }"
            :style="{ left: eventLeft(event.index) }"
            :title="`${event.time} ${event.title}`"
            @click.stop="selectedEvent = event"
          >N</button>

          <div v-if="hoverIndex !== null" class="chart-tooltip" :style="{ left: tooltipLeft() }">
            <strong>{{ marketTimes[hoverIndex] }}</strong>
            <span v-for="item in normalizedSeries" :key="item.code">
              <i :style="{ background: item.color }"></i>
              {{ item.name }} {{ item.values[hoverIndex] >= 0 ? '+' : '' }}{{ item.values[hoverIndex].toFixed(2) }}%
            </span>
          </div>
        </div>

        <div class="chart-time-axis" aria-hidden="true">
          <span>09:30</span><span>10:30</span><span>11:30</span><span>14:00</span><span>15:00</span>
        </div>

        <div class="volume-bars" aria-label="演示成交量">
          <i
            v-for="(value, index) in volumeSeries"
            :key="index"
            :class="index % 3 === 0 ? 'volume-down' : 'volume-up'"
            :style="{ height: `${Math.max(8, value / maxVolume * 100)}%` }"
          ></i>
        </div>

        <div class="selected-market-event">
          <span>{{ selectedEvent.time }}</span>
          <div>
            <strong>{{ selectedEvent.source }} · {{ selectedEvent.title }}</strong>
            <small>关联板块：{{ selectedEvent.related }}。这里只展示时间对应关系，不判断因果或涨跌方向。</small>
          </div>
        </div>
      </section>

      <aside class="market-right-rail">
        <section class="panel market-anomaly-panel">
          <div class="panel-heading-row">
            <h2>异动观察</h2>
            <span class="neutral-badge">仅数据</span>
          </div>
          <article v-for="item in marketAnomalies" :key="item.time" class="market-anomaly-row">
            <i :class="['anomaly-icon', `tone-${item.tone}`]"></i>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.time }} · {{ item.detail }}</p>
            </div>
          </article>
        </section>

        <section class="panel market-event-panel">
          <h2>新闻影响时间线</h2>
          <button
            v-for="event in marketEvents"
            :key="event.time"
            type="button"
            :class="{ active: selectedEvent.time === event.time }"
            @click="selectedEvent = event"
          >
            <span>{{ event.time }}</span>
            <div><strong>{{ event.source }}</strong><small>{{ event.title }}</small></div>
          </button>
        </section>

        <section class="panel market-data-status">
          <h2>数据状态</h2>
          <div><span>行情曲线</span><b class="status-demo">演示</b></div>
          <div><span>新闻来源</span><b class="status-live">已连接</b></div>
          <small>{{ marketMeta.updatedAt }}</small>
        </section>
      </aside>
    </div>

    <div class="market-lower-grid">
      <section class="panel sector-panel">
        <div class="panel-heading-row"><h2>板块表现</h2><span>演示涨跌幅</span></div>
        <div v-for="sector in sectors" :key="sector.name" class="sector-row">
          <strong>{{ sector.name }}</strong>
          <div class="sector-track"><i :class="sector.change >= 0 ? 'bar-up' : 'bar-down'" :style="{ width: `${Math.abs(sector.change) / 2.5 * 100}%` }"></i></div>
          <span :class="sector.change >= 0 ? 'market-up' : 'market-down'">{{ sector.change >= 0 ? '+' : '' }}{{ sector.change.toFixed(2) }}%</span>
          <svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
            <polyline :points="sparklinePoints(sector.trend)" :stroke="sector.change >= 0 ? '#ff5f57' : '#55c98b'"></polyline>
          </svg>
        </div>
      </section>

      <section class="panel heatmap-panel">
        <div class="panel-heading-row"><h2>市场热度</h2><span>按成交活跃度</span></div>
        <div class="heatmap-grid">
          <div
            v-for="item in heatmap"
            :key="item.name"
            :class="['heat-cell', heatClass(item.value)]"
            :style="{ flexGrow: item.size }"
          >
            <strong>{{ item.name }}</strong>
            <span>{{ item.value >= 0 ? '+' : '' }}{{ item.value.toFixed(2) }}%</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
