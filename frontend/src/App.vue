<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const logged = ref(!!localStorage.getItem('token'))
const user = ref('admin')
const pass = ref('')
const nodes = ref([])
const dashboard = ref({ nodes: [] })
const logs = ref([])
const loading = ref(false)
const addOpen = ref(false)
const rawOpen = ref(false)
const selected = ref([])
const form = ref({
  name: '',
  region: '',
  base_url: '',
  api_token: '',
  verify_tls: true,
  enabled: true,
})
const raw = ref({
  node_ids: [],
  object: 'clients',
  action: 'edit',
  data: '{}',
  initUsers: null,
})

const onlineCount = computed(
  () => dashboard.value.nodes?.filter((item) => item.online).length || 0,
)

async function login() {
  try {
    const response = await api.post('/login', {
      username: user.value,
      password: pass.value,
    })
    localStorage.setItem('token', response.data.access_token)
    logged.value = true
    await refresh()
  } catch {
    ElMessage.error('登录失败')
  }
}

function logout() {
  localStorage.removeItem('token')
  logged.value = false
}

async function refresh() {
  loading.value = true
  try {
    const [nodeResponse, dashboardResponse, auditResponse] = await Promise.all([
      api.get('/nodes'),
      api.get('/dashboard'),
      api.get('/audit?limit=50'),
    ])
    nodes.value = nodeResponse.data
    dashboard.value = dashboardResponse.data
    logs.value = auditResponse.data
  } catch (error) {
    if (error.response?.status === 401) logout()
  } finally {
    loading.value = false
  }
}

async function addNode() {
  await api.post('/nodes', form.value)
  addOpen.value = false
  form.value = {
    name: '',
    region: '',
    base_url: '',
    api_token: '',
    verify_tls: true,
    enabled: true,
  }
  await refresh()
}

async function testNode(id) {
  const response = await api.post(`/nodes/${id}/test`)
  alert(response.data.ok ? '连接成功' : `连接失败：${response.data.error}`)
  await refresh()
}

async function delNode(id) {
  if (!confirm('确定删除该节点？')) return
  await api.delete(`/nodes/${id}`)
  await refresh()
}

function toggleSelected(id, checked) {
  if (checked) {
    if (!selected.value.includes(id)) selected.value.push(id)
    return
  }
  const index = selected.value.indexOf(id)
  if (index >= 0) selected.value.splice(index, 1)
}

async function restartCore() {
  if (!selected.value.length) return alert('请选择节点')
  await api.post('/actions/restart-core', { node_ids: selected.value })
  await refresh()
}

async function rawSave() {
  let data
  try {
    data = JSON.parse(raw.value.data)
  } catch {
    return alert('data 不是合法 JSON')
  }

  if (!selected.value.length) return alert('请选择节点')
  const payload = { ...raw.value, node_ids: selected.value, data }
  const response = await api.post('/actions/raw-save', payload)
  alert(JSON.stringify(response.data, null, 2))
  rawOpen.value = false
  await refresh()
}

function shape(value) {
  if (value == null) return '-'
  if (typeof value === 'string' || typeof value === 'number') return value
  return JSON.stringify(value).slice(0, 160)
}
</script>

<template>
  <div v-if="!logged" class="login">
    <el-card>
      <h2>S-UI Manager</h2>
      <el-input v-model="user" placeholder="用户名" />
      <el-input v-model="pass" type="password" placeholder="密码" @keyup.enter="login" />
      <el-button type="primary" @click="login">登录</el-button>
    </el-card>
  </div>

  <div v-else class="layout">
    <aside>
      <div class="brand">S-UI Manager <small>V1.0</small></div>
      <div class="menu">Dashboard<br />节点管理<br />批量操作<br />审计日志</div>
      <el-button text @click="logout">退出</el-button>
    </aside>

    <main>
      <header>
        <h2>统一控制台</h2>
        <div>
          <el-button @click="refresh">刷新</el-button>
          <el-button type="primary" @click="addOpen = true">添加 VPS</el-button>
        </div>
      </header>

      <section class="cards">
        <el-card><div class="kpi">{{ nodes.length }}</div><div>节点总数</div></el-card>
        <el-card><div class="kpi">{{ onlineCount }}</div><div>在线节点</div></el-card>
        <el-card><div class="kpi">{{ selected.length }}</div><div>已选节点</div></el-card>
      </section>

      <el-card>
        <template #header>
          <div class="row">
            <b>节点</b>
            <div>
              <el-button @click="restartCore">批量重启 Core</el-button>
              <el-button type="warning" @click="rawOpen = true">高级批量写入</el-button>
            </div>
          </div>
        </template>

        <el-table :data="dashboard.nodes" v-loading="loading">
          <el-table-column width="55">
            <template #default="scope">
              <el-checkbox
                :model-value="selected.includes(scope.row.node.id)"
                @change="toggleSelected(scope.row.node.id, $event)"
              />
            </template>
          </el-table-column>
          <el-table-column label="节点" min-width="150">
            <template #default="scope">
              <b>{{ scope.row.node.name }}</b>
              <div class="muted">{{ scope.row.node.region }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="95">
            <template #default="scope">
              <el-tag :type="scope.row.online ? 'success' : 'danger'">
                {{ scope.row.online ? '在线' : '离线' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="S-UI Status">
            <template #default="scope">
              <span class="mono">{{ shape(scope.row.status?.obj || scope.row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="190">
            <template #default="scope">
              <el-button size="small" @click="testNode(scope.row.node.id)">测试</el-button>
              <el-button size="small" type="danger" @click="delNode(scope.row.node.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card style="margin-top: 18px">
        <template #header><b>最近操作</b></template>
        <el-table :data="logs">
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column prop="action" label="动作" width="170" />
          <el-table-column prop="target" label="目标" />
          <el-table-column prop="actor" label="操作者" width="100" />
        </el-table>
      </el-card>
    </main>

    <el-dialog v-model="addOpen" title="添加 S-UI 节点" width="520px">
      <el-form label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="地区"><el-input v-model="form.region" /></el-form-item>
        <el-form-item label="面板地址">
          <el-input v-model="form.base_url" placeholder="https://host.example.com/app" />
        </el-form-item>
        <el-form-item label="API Token"><el-input v-model="form.api_token" type="password" /></el-form-item>
        <el-form-item label="校验 TLS"><el-switch v-model="form.verify_tls" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addOpen = false">取消</el-button>
        <el-button type="primary" @click="addNode">保存并测试</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="rawOpen" title="高级批量写入（兼容模式）" width="650px">
      <el-alert
        title="会直接调用各节点 /apiv2/save，请先备份数据库并在单节点验证 payload。"
        type="warning"
        show-icon
        :closable="false"
      />
      <el-form label-width="95px" style="margin-top: 15px">
        <el-form-item label="对象">
          <el-select v-model="raw.object">
            <el-option
              v-for="item in ['clients', 'inbounds', 'outbounds', 'tls', 'services', 'endpoints', 'config', 'settings']"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="动作"><el-input v-model="raw.action" /></el-form-item>
        <el-form-item label="data JSON">
          <el-input v-model="raw.data" type="textarea" :rows="12" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rawOpen = false">取消</el-button>
        <el-button type="danger" @click="rawSave">执行批量写入</el-button>
      </template>
    </el-dialog>
  </div>
</template>
