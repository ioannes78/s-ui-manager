<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errorText } from './api'

const route = useRoute()
const router = useRouter()
const logged = ref(Boolean(localStorage.getItem('token')))
const username = ref('admin')
const password = ref('')
const loginLoading = ref(false)
const meta = ref({ version: '2.0.2', user: 'admin' })

const pageTitle = computed(() => route.meta.title || 'S-UI Manager')

const menu = [
  ['/', '运行概览'],
  ['/nodes', '节点管理'],
  ['/users', '中央用户'],
  ['/tasks', '任务中心'],
  ['/alerts', '监控告警'],
  ['/audit', '审计日志'],
]

async function loadMeta() {
  if (!logged.value) return
  try {
    meta.value = (await api.get('/meta')).data
  } catch {
    // The auth interceptor handles expired sessions.
  }
}

async function login() {
  loginLoading.value = true
  try {
    const response = await api.post('/login', { username: username.value, password: password.value })
    localStorage.setItem('token', response.data.access_token)
    logged.value = true
    password.value = ''
    await loadMeta()
    await router.push('/')
  } catch (error) {
    ElMessage.error(errorText(error) === 'Invalid username/password' ? '用户名或密码错误' : errorText(error))
  } finally {
    loginLoading.value = false
  }
}

function logout() {
  localStorage.removeItem('token')
  logged.value = false
}

function authExpired() {
  logged.value = false
}

onMounted(() => {
  window.addEventListener('auth-expired', authExpired)
  loadMeta()
})
onBeforeUnmount(() => window.removeEventListener('auth-expired', authExpired))
</script>

<template>
  <div v-if="!logged" class="login-page">
    <section class="login-copy">
      <div class="logo-mark">S</div>
      <p class="eyebrow">S-UI MANAGER V2.0</p>
      <h1>统一管理每一台<br />S-UI 节点</h1>
      <p>节点、中央用户、配置快照、任务和告警，都在一个控制台完成。</p>
    </section>
    <el-card class="login-card" shadow="always">
      <h2>管理员登录</h2>
      <p class="muted">使用安装完成时生成的管理员凭据</p>
      <el-input v-model="username" size="large" placeholder="管理员用户名" />
      <el-input
        v-model="password"
        size="large"
        type="password"
        show-password
        placeholder="管理员密码"
        @keyup.enter="login"
      />
      <el-button type="primary" size="large" :loading="loginLoading" @click="login">登录控制台</el-button>
    </el-card>
  </div>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="logo-mark small">S</span>
        <span>S-UI Manager<small>V{{ meta.version }}</small></span>
      </div>
      <nav>
        <router-link v-for="item in menu" :key="item[0]" :to="item[0]" :class="{ active: route.path === item[0] }">
          {{ item[1] }}
        </router-link>
      </nav>
      <div class="sidebar-foot">
        <span class="status-dot"></span>
        <div><b>后台服务正常</b><small>{{ meta.user }}</small></div>
      </div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">S-UI UNIFIED OPERATIONS</p>
          <h2>{{ pageTitle }}</h2>
        </div>
        <el-button plain @click="logout">退出登录</el-button>
      </header>
      <main class="page-content">
        <router-view />
      </main>
    </section>
  </div>
</template>
