import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Detail from '../views/Detail.vue'
import Stats from '../views/Stats.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/news/:id', component: Detail },
  { path: '/stats', component: Stats },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // 浏览器返回时恢复之前滚动位置
    if (savedPosition) {
      return savedPosition
    }
    // 否则滚到顶部
    return { top: 0 }
  },
})

export default router
