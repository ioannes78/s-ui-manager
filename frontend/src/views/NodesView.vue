<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorText, formatBytes, formatTime } from '../api'

const nodes = ref([])
const loading = ref(false)
const query = ref('')
const group = ref('')
const selected = ref([])
const editOpen = ref(false)
const editId = ref(null)
const detailOpen = ref(false)
const detailNode = ref(null)
const detailTab = ref('overview')
const rawSource = ref('overview')
const detailSections = ref(sectionState())
const detailDrawerSize = ref(drawerSize())
const snapshotOpen = ref(false)
const snapshots = ref([])
const snapshotNode = ref(null)
const rawOpen = ref(false)
const raw = ref({ object: 'clients', action: 'edit', data: '{}' })
const form = ref(emptyForm())

const sectionConfig = {
  overview: { endpoint: 'status', label: '运行概览' },
  clients: { endpoint: 'clients', label: '客户端' },
  inbounds: { endpoint: 'inbounds', label: '入站' },
  onlines: { endpoint: 'onlines', label: '在线情况' },
}

const statusData = computed(() => unwrap(detailSections.value.overview.data))
const clientRows = computed(() => findArray(detailSections.value.clients.data, ['clients', 'users']))
const inboundRows = computed(() => findArray(detailSections.value.inbounds.data, ['inbounds']))
const onlineData = computed(() => unwrap(detailSections.value.onlines.data))
const onlineGroups = computed(() => [
  { key: 'user', title: '在线用户', values: arrayValue(onlineData.value, ['user', 'users']) },
  { key: 'inbound', title: '活跃入站', values: arrayValue(onlineData.value, ['inbound', 'inbounds']) },
  { key: 'outbound', title: '活跃出站', values: arrayValue(onlineData.value, ['outbound', 'outbounds']) },
])
const rawJson = computed(() => maskedJson(detailSections.value[rawSource.value]?.data))

function sectionState() {
  return Object.fromEntries(['overview', 'clients', 'inbounds', 'onlines'].map((key) => [key, { data: null, loading: false, error: '', loaded: false }]))
}

function drawerSize() {
  if (window.innerWidth <= 850) return '100%'
  if (window.innerWidth <= 1200) return '90%'
  return '80%'
}

function syncDrawerSize() {
  detailDrawerSize.value = drawerSize()
}

function unwrap(value) {
  if (!value || typeof value !== 'object') return value || {}
  if (value.obj && typeof value.obj === 'object') return value.obj
  if (value.data && typeof value.data === 'object') return unwrap(value.data)
  return value
}

function findArray(value, keys) {
  const object = unwrap(value)
  if (Array.isArray(object)) return object
  for (const key of keys) if (Array.isArray(object?.[key])) return object[key]
  return []
}

function arrayValue(object, keys) {
  for (const key of keys) if (Array.isArray(object?.[key])) return object[key]
  return []
}

function numberValue(object, keys, fallback = 0) {
  for (const key of keys) {
    const value = Number(object?.[key])
    if (Number.isFinite(value)) return value
  }
  return fallback
}

function nestedValue(object, names) {
  for (const name of names) if (object?.[name] && typeof object[name] === 'object') return object[name]
  return {}
}

function percent(current, total) {
  const result = total > 0 ? current / total * 100 : 0
  return Math.max(0, Math.min(100, Number(result.toFixed(1))))
}

function cpuPercent() {
  return Math.max(0, Math.min(100, numberValue(statusData.value, ['cpu', 'cpu_percent', 'cpuPercent'])))
}

function memoryInfo() {
  const item = nestedValue(statusData.value, ['mem', 'memory'])
  const current = numberValue(item, ['current', 'used', 'usage'])
  const total = numberValue(item, ['total', 'max'])
  return { current, total, percent: percent(current, total) }
}

function diskInfo() {
  const item = nestedValue(statusData.value, ['dsk', 'disk'])
  const current = numberValue(item, ['current', 'used', 'usage'])
  const total = numberValue(item, ['total', 'max'])
  return { current, total, percent: percent(current, total) }
}

function networkInfo() {
  const item = nestedValue(statusData.value, ['net', 'network'])
  return {
    down: numberValue(item, ['recv', 'receive', 'down', 'download']),
    up: numberValue(item, ['sent', 'psent', 'send', 'up', 'upload']),
  }
}

function ioInfo() {
  const item = nestedValue(statusData.value, ['dio', 'disk_io', 'io'])
  return { read: numberValue(item, ['read']), write: numberValue(item, ['write']) }
}

function clientTraffic(row) {
  const up = numberValue(row, ['up', 'upload'])
  const down = numberValue(row, ['down', 'download'])
  return formatBytes(up + down)
}

function clientLimit(row) {
  const value = numberValue(row, ['volume', 'total', 'limit'])
  return value > 0 ? formatBytes(value) : '不限'
}

function expiryText(row) {
  const value = row?.expiry ?? row?.expire_at ?? row?.expiry_time
  if (!value) return '永不过期'
  const number = Number(value)
  if (Number.isFinite(number)) return formatTime(number > 1e12 ? number : number * 1000)
  return formatTime(value)
}

function listText(value) {
  if (!Array.isArray(value) || !value.length) return '-'
  return value.map((item) => typeof item === 'object' ? (item.name || item.tag || item.id || JSON.stringify(item)) : item).join('、')
}

function maskSensitive(value) {
  if (Array.isArray(value)) return value.map(maskSensitive)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, /password|passwd|token|secret|private.?key/i.test(key) ? '******' : maskSensitive(item)]))
}

function maskedJson(value) {
  return value == null ? '暂无数据' : JSON.stringify(maskSensitive(value), null, 2)
}

const groups = computed(() => [...new Set(nodes.value.map((item) => item.group_name).filter(Boolean))])

function emptyForm() {
  return { name: '', region: '', base_url: '', api_token: '', verify_tls: true, enabled: true, group_name: '', tags_text: '', notes: '' }
}

async function load() {
  loading.value = true
  try {
    nodes.value = (await api.get('/nodes', { params: { query: query.value, group_name: group.value } })).data
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    loading.value = false
  }
}

function addNode() {
  editId.value = null
  form.value = emptyForm()
  editOpen.value = true
}

function editNode(node) {
  editId.value = node.id
  form.value = { ...node, api_token: '', tags_text: (node.tags || []).join(', ') }
  editOpen.value = true
}

async function saveNode() {
  const payload = { ...form.value, tags: form.value.tags_text.split(',').map((item) => item.trim()).filter(Boolean) }
  delete payload.tags_text
  if (editId.value && !payload.api_token) delete payload.api_token
  try {
    if (editId.value) await api.patch(`/nodes/${editId.value}`, payload)
    else await api.post('/nodes', payload)
    ElMessage.success(editId.value ? '节点已更新' : '节点已添加并完成连接测试')
    editOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorText(error))
  }
}

async function testNode(node) {
  try {
    const result = (await api.post(`/nodes/${node.id}/test`)).data
    result.ok ? ElMessage.success(`${node.name} 连接成功，${result.latency_ms} ms`) : ElMessage.error(result.error)
    await load()
  } catch (error) {
    ElMessage.error(errorText(error))
  }
}

async function removeNode(node) {
  try {
    await ElMessageBox.confirm(`删除节点“${node.name}”？远程 S-UI 不会被卸载。`, '确认删除', { type: 'warning' })
    await api.delete(`/nodes/${node.id}`)
    ElMessage.success('节点记录已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorText(error))
  }
}

function onSelection(rows) {
  selected.value = rows.map((item) => item.id)
}

async function restartSelected() {
  if (!selected.value.length) return ElMessage.warning('请先选择节点')
  try {
    await ElMessageBox.confirm(`将在 ${selected.value.length} 台节点上重启 sing-box Core，确认继续？`, '批量操作', { type: 'warning' })
    const response = (await api.post('/actions/restart-core', { node_ids: selected.value })).data
    const failed = response.results.filter((item) => !item.ok).length
    failed ? ElMessage.warning(`任务 #${response.job_id} 完成，${failed} 台失败`) : ElMessage.success(`任务 #${response.job_id} 全部成功`)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorText(error))
  }
}

async function runRawSave() {
  if (!selected.value.length) return ElMessage.warning('请先选择节点')
  let data
  try { data = JSON.parse(raw.value.data) } catch { return ElMessage.error('data 不是合法 JSON') }
  try {
    await ElMessageBox.confirm('高级写入会直接修改远程 S-UI，请确认已经备份并在单节点验证。', '高风险操作', { type: 'error' })
    const response = (await api.post('/actions/raw-save', { ...raw.value, data, node_ids: selected.value })).data
    rawOpen.value = false
    ElMessage.success(`批量任务 #${response.job_id} 已完成`)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorText(error))
  }
}

async function showDetails(node) {
  detailOpen.value = true
  detailNode.value = node
  detailTab.value = 'overview'
  rawSource.value = 'overview'
  detailSections.value = sectionState()
  await loadDetailSection('overview')
}

async function loadDetailSection(key, force = false) {
  const section = detailSections.value[key]
  const config = sectionConfig[key]
  if (!section || !config || !detailNode.value || section.loading || (section.loaded && !force)) return
  section.loading = true
  section.error = ''
  try {
    section.data = (await api.get(`/nodes/${detailNode.value.id}/${config.endpoint}`)).data
    section.loaded = true
  } catch (error) {
    section.error = errorText(error)
  } finally {
    section.loading = false
  }
}

function changeDetailTab(name) {
  detailTab.value = name
  if (sectionConfig[name]) loadDetailSection(name)
  if (name === 'raw') loadDetailSection(rawSource.value)
}

function changeRawSource(name) {
  rawSource.value = name
  loadDetailSection(name)
}

async function refreshDetail() {
  const key = detailTab.value === 'raw' ? rawSource.value : detailTab.value
  await loadDetailSection(key, true)
  if (!detailSections.value[key].error) ElMessage.success(`${sectionConfig[key].label}已刷新`)
}

async function restartDetailNode() {
  const node = detailNode.value
  if (!node) return
  try {
    await ElMessageBox.confirm(`将在“${node.name}”上重启 sing-box Core，确认继续？`, '节点操作', { type: 'warning' })
    const response = (await api.post('/actions/restart-core', { node_ids: [node.id] })).data
    const result = response.results?.[0]
    result?.ok ? ElMessage.success('Core 重启成功') : ElMessage.error(result?.error || 'Core 重启失败')
    await loadDetailSection('overview', true)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorText(error))
  }
}

async function copyRaw() {
  try {
    await navigator.clipboard.writeText(rawJson.value)
    ElMessage.success('已复制原始数据')
  } catch {
    ElMessage.error('复制失败，请检查浏览器剪贴板权限')
  }
}

async function showSnapshots(node) {
  snapshotNode.value = node
  snapshotOpen.value = true
  try { snapshots.value = (await api.get(`/nodes/${node.id}/snapshots`)).data }
  catch (error) { ElMessage.error(errorText(error)) }
}

async function createSnapshot() {
  try {
    const result = await ElMessageBox.prompt('输入快照说明', '创建配置快照', { inputValue: '手动快照', inputValidator: (value) => Boolean(value.trim()) || '请输入说明' })
    await api.post(`/nodes/${snapshotNode.value.id}/snapshots`, { label: result.value.trim() })
    ElMessage.success('配置快照创建成功')
    await showSnapshots(snapshotNode.value)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorText(error))
  }
}

async function inspectSnapshot(snapshot) {
  try {
    const response = (await api.get(`/snapshots/${snapshot.id}`)).data
    await ElMessageBox.alert(`<pre class="json-box">${escapeHtml(JSON.stringify(response.payload, null, 2))}</pre>`, `快照 #${snapshot.id}`, { dangerouslyUseHTMLString: true, customClass: 'wide-message' })
  } catch (error) { ElMessage.error(errorText(error)) }
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char])
}

onMounted(() => {
  load()
  window.addEventListener('resize', syncDrawerSize)
})
onBeforeUnmount(() => window.removeEventListener('resize', syncDrawerSize))
</script>

<template>
  <div class="page-head">
    <div><h3>节点与分组</h3><span class="muted">集中维护连接信息、标签、快照和远程操作</span></div>
    <div class="page-actions"><el-button :disabled="!selected.length" @click="restartSelected">批量重启 Core</el-button><el-button type="warning" :disabled="!selected.length" @click="rawOpen = true">高级批量写入</el-button><el-button type="primary" @click="addNode">添加节点</el-button></div>
  </div>
  <div class="filters"><el-input v-model="query" clearable placeholder="搜索节点、地区或标签" @keyup.enter="load" /><el-select v-model="group" clearable placeholder="全部分组" @change="load"><el-option v-for="item in groups" :key="item" :label="item" :value="item" /></el-select><el-button @click="load">查询</el-button></div>
  <el-card class="panel" shadow="never">
    <el-table :data="nodes" v-loading="loading" @selection-change="onSelection">
      <el-table-column type="selection" width="48" />
      <el-table-column label="节点" min-width="175"><template #default="scope"><div class="table-primary">{{ scope.row.name }}</div><div class="table-secondary">{{ scope.row.base_url }}</div></template></el-table-column>
      <el-table-column label="分组/地区" width="150"><template #default="scope"><div>{{ scope.row.group_name || '未分组' }}</div><div class="muted">{{ scope.row.region || '-' }}</div></template></el-table-column>
      <el-table-column label="标签" min-width="145"><template #default="scope"><div class="tag-list"><el-tag v-for="tag in scope.row.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag><span v-if="!scope.row.tags?.length" class="muted">-</span></div></template></el-table-column>
      <el-table-column label="状态" width="110"><template #default="scope"><span class="node-status" :class="{ online: scope.row.online }"><i></i>{{ scope.row.online ? '在线' : '离线' }}</span><div class="muted">{{ scope.row.last_latency_ms == null ? '-' : `${scope.row.last_latency_ms} ms` }}</div></template></el-table-column>
      <el-table-column label="最后检查" width="180"><template #default="scope">{{ formatTime(scope.row.last_checked_at) }}</template></el-table-column>
      <el-table-column label="操作" width="320" fixed="right"><template #default="scope"><el-button size="small" @click="testNode(scope.row)">测试</el-button><el-button size="small" @click="showDetails(scope.row)">详情</el-button><el-button size="small" @click="showSnapshots(scope.row)">快照</el-button><el-button size="small" @click="editNode(scope.row)">编辑</el-button><el-button size="small" type="danger" text @click="removeNode(scope.row)">删除</el-button></template></el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="editOpen" :title="editId ? '编辑节点' : '添加 S-UI 节点'" width="620px">
    <el-form label-width="95px">
      <el-form-item label="节点名称" required><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="面板地址" required><el-input v-model="form.base_url" placeholder="https://host.example.com/app" /></el-form-item>
      <el-form-item label="API Token" :required="!editId"><el-input v-model="form.api_token" type="password" show-password :placeholder="editId ? '留空表示不修改' : 'S-UI API Token'" /></el-form-item>
      <el-form-item label="分组"><el-input v-model="form.group_name" placeholder="例如：亚洲节点" /></el-form-item>
      <el-form-item label="地区"><el-input v-model="form.region" placeholder="例如：香港" /></el-form-item>
      <el-form-item label="标签"><el-input v-model="form.tags_text" placeholder="生产, 高速, 备用（逗号分隔）" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="3" /></el-form-item>
      <el-form-item label="选项"><el-checkbox v-model="form.verify_tls">校验 TLS</el-checkbox><el-checkbox v-model="form.enabled">启用监控</el-checkbox></el-form-item>
    </el-form>
    <template #footer><el-button @click="editOpen = false">取消</el-button><el-button type="primary" @click="saveNode">保存</el-button></template>
  </el-dialog>

  <el-drawer v-model="detailOpen" :size="detailDrawerSize" class="node-detail-drawer" :with-header="false">
    <div v-if="detailNode" class="node-detail">
      <header class="node-detail-head">
        <div class="node-detail-title">
          <div class="node-detail-name-line">
            <h3>{{ detailNode.name }}</h3>
            <span class="node-status" :class="{ online: detailNode.online }"><i></i>{{ detailNode.online ? '在线' : '离线' }}</span>
          </div>
          <div class="node-detail-meta">
            <span>{{ detailNode.group_name || '未分组' }}<template v-if="detailNode.region"> · {{ detailNode.region }}</template></span>
            <span>{{ detailNode.last_latency_ms == null ? '延迟未知' : `${detailNode.last_latency_ms} ms` }}</span>
            <span>版本 {{ detailNode.sui_version || '未知' }}</span>
            <span class="node-detail-url">{{ detailNode.base_url }}</span>
          </div>
        </div>
        <div class="node-detail-actions">
          <el-button @click="refreshDetail">刷新当前页</el-button>
          <el-button type="warning" plain @click="restartDetailNode">重启 Core</el-button>
          <el-button circle aria-label="关闭" @click="detailOpen = false">×</el-button>
        </div>
      </header>

      <el-tabs v-model="detailTab" class="node-detail-tabs" @tab-change="changeDetailTab">
        <el-tab-pane label="运行概览" name="overview">
          <div v-loading="detailSections.overview.loading" class="detail-section">
            <el-alert v-if="detailSections.overview.error" :title="detailSections.overview.error" type="error" show-icon :closable="false">
              <template #default><el-button size="small" @click="loadDetailSection('overview', true)">重试</el-button></template>
            </el-alert>
            <template v-else-if="detailSections.overview.loaded">
              <div class="resource-grid">
                <div class="resource-card">
                  <div class="resource-card-head"><span>CPU 使用率</span><b>{{ cpuPercent() }}%</b></div>
                  <el-progress :percentage="cpuPercent()" :stroke-width="9" :show-text="false" />
                </div>
                <div class="resource-card">
                  <div class="resource-card-head"><span>内存</span><b>{{ memoryInfo().percent }}%</b></div>
                  <el-progress :percentage="memoryInfo().percent" :stroke-width="9" :show-text="false" />
                  <small>{{ formatBytes(memoryInfo().current) }} / {{ formatBytes(memoryInfo().total) }}</small>
                </div>
                <div class="resource-card">
                  <div class="resource-card-head"><span>磁盘</span><b>{{ diskInfo().percent }}%</b></div>
                  <el-progress :percentage="diskInfo().percent" :stroke-width="9" :show-text="false" />
                  <small>{{ formatBytes(diskInfo().current) }} / {{ formatBytes(diskInfo().total) }}</small>
                </div>
                <div class="resource-card resource-card-accent">
                  <span>网络流量</span>
                  <div class="traffic-pair"><b>↓ {{ formatBytes(networkInfo().down) }}</b><b>↑ {{ formatBytes(networkInfo().up) }}</b></div>
                  <small>实时累计接收 / 发送</small>
                </div>
              </div>
              <div class="detail-summary-grid">
                <div class="detail-item"><label>磁盘读取</label><strong>{{ formatBytes(ioInfo().read) }}</strong></div>
                <div class="detail-item"><label>磁盘写入</label><strong>{{ formatBytes(ioInfo().write) }}</strong></div>
                <div class="detail-item"><label>最后健康检查</label><strong>{{ formatTime(detailNode.last_checked_at) }}</strong></div>
                <div class="detail-item"><label>最近成功连接</label><strong>{{ formatTime(detailNode.last_ok_at) }}</strong></div>
              </div>
            </template>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`客户端 ${detailSections.clients.loaded ? clientRows.length : ''}`" name="clients">
          <div v-loading="detailSections.clients.loading" class="detail-section">
            <el-alert v-if="detailSections.clients.error" :title="detailSections.clients.error" type="error" show-icon :closable="false"><template #default><el-button size="small" @click="loadDetailSection('clients', true)">重试</el-button></template></el-alert>
            <template v-else-if="detailSections.clients.loaded">
              <el-empty v-if="!clientRows.length" description="暂无客户端" />
              <div v-else class="responsive-data-list">
                <article v-for="row in clientRows" :key="row.id ?? row.name" class="data-card">
                  <div class="data-card-head"><div><b>{{ row.name || `客户端 #${row.id}` }}</b><small>#{{ row.id ?? '-' }}</small></div><el-tag :type="row.enable === false ? 'info' : 'success'" size="small">{{ row.enable === false ? '停用' : '启用' }}</el-tag></div>
                  <dl><div><dt>绑定入站</dt><dd>{{ listText(row.inbounds) }}</dd></div><div><dt>已用流量</dt><dd>{{ clientTraffic(row) }}</dd></div><div><dt>流量上限</dt><dd>{{ clientLimit(row) }}</dd></div><div><dt>到期时间</dt><dd>{{ expiryText(row) }}</dd></div></dl>
                </article>
              </div>
            </template>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`入站 ${detailSections.inbounds.loaded ? inboundRows.length : ''}`" name="inbounds">
          <div v-loading="detailSections.inbounds.loading" class="detail-section">
            <el-alert v-if="detailSections.inbounds.error" :title="detailSections.inbounds.error" type="error" show-icon :closable="false"><template #default><el-button size="small" @click="loadDetailSection('inbounds', true)">重试</el-button></template></el-alert>
            <template v-else-if="detailSections.inbounds.loaded">
              <el-empty v-if="!inboundRows.length" description="暂无入站" />
              <div v-else class="responsive-data-list">
                <article v-for="row in inboundRows" :key="row.id ?? row.tag" class="data-card">
                  <div class="data-card-head"><div><b>{{ row.tag || `入站 #${row.id}` }}</b><small>#{{ row.id ?? '-' }}</small></div><el-tag size="small" effect="plain">{{ row.type || row.protocol || '未知协议' }}</el-tag></div>
                  <dl><div><dt>监听地址</dt><dd>{{ row.listen || '::' }}</dd></div><div><dt>端口</dt><dd>{{ row.listen_port ?? row.port ?? '-' }}</dd></div><div><dt>TLS</dt><dd>{{ (row.tls_id || row.tls?.enabled) ? '已启用' : '未启用' }}</dd></div><div><dt>客户端数</dt><dd>{{ Array.isArray(row.users) ? row.users.length : 0 }}</dd></div></dl>
                </article>
              </div>
            </template>
          </div>
        </el-tab-pane>

        <el-tab-pane label="在线情况" name="onlines">
          <div v-loading="detailSections.onlines.loading" class="detail-section">
            <el-alert v-if="detailSections.onlines.error" :title="detailSections.onlines.error" type="error" show-icon :closable="false"><template #default><el-button size="small" @click="loadDetailSection('onlines', true)">重试</el-button></template></el-alert>
            <template v-else-if="detailSections.onlines.loaded">
              <div class="online-grid">
                <section v-for="groupItem in onlineGroups" :key="groupItem.key" class="online-card">
                  <div class="online-card-title"><b>{{ groupItem.title }}</b><span>{{ groupItem.values.length }}</span></div>
                  <div v-if="groupItem.values.length" class="online-tags"><el-tag v-for="(item, index) in groupItem.values" :key="index" effect="plain">{{ typeof item === 'object' ? (item.name || item.tag || item.id || JSON.stringify(item)) : item }}</el-tag></div>
                  <el-empty v-else :image-size="48" description="暂无数据" />
                </section>
              </div>
            </template>
          </div>
        </el-tab-pane>

        <el-tab-pane label="原始数据" name="raw">
          <div class="raw-toolbar">
            <el-select v-model="rawSource" size="small" aria-label="原始数据类型" @change="changeRawSource">
              <el-option v-for="(item, key) in sectionConfig" :key="key" :label="item.label" :value="key" />
            </el-select>
            <span class="muted">敏感字段已自动隐藏</span>
            <el-button size="small" @click="copyRaw">复制 JSON</el-button>
          </div>
          <div v-loading="detailSections[rawSource].loading">
            <el-alert v-if="detailSections[rawSource].error" :title="detailSections[rawSource].error" type="error" show-icon :closable="false" />
            <pre v-else class="json-box detail-json">{{ rawJson }}</pre>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>

  <el-drawer v-model="snapshotOpen" :title="`${snapshotNode?.name || ''} · 配置快照`" size="620px">
    <el-button type="primary" @click="createSnapshot">创建快照</el-button>
    <el-table :data="snapshots" style="margin-top:16px"><el-table-column prop="id" label="ID" width="70" /><el-table-column prop="label" label="说明" /><el-table-column label="时间" width="180"><template #default="scope">{{ formatTime(scope.row.created_at) }}</template></el-table-column><el-table-column width="90"><template #default="scope"><el-button size="small" @click="inspectSnapshot(scope.row)">查看</el-button></template></el-table-column></el-table>
  </el-drawer>

  <el-dialog v-model="rawOpen" title="高级批量写入" width="680px">
    <el-alert class="notice" title="该功能直接调用节点 /apiv2/save，请先创建快照并在单节点测试。" type="warning" show-icon :closable="false" />
    <el-form label-width="90px"><el-form-item label="对象"><el-select v-model="raw.object"><el-option v-for="item in ['clients','inbounds','outbounds','tls','services','endpoints','config','settings']" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="动作"><el-select v-model="raw.action"><el-option v-for="item in ['add','edit','delete','update','save','bulk','editBulk']" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="data JSON"><el-input v-model="raw.data" type="textarea" :rows="14" /></el-form-item></el-form>
    <template #footer><el-button @click="rawOpen = false">取消</el-button><el-button type="danger" @click="runRawSave">确认执行</el-button></template>
  </el-dialog>
</template>
