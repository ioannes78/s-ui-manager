<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorText, formatTime } from '../api'

const nodes = ref([])
const loading = ref(false)
const query = ref('')
const group = ref('')
const selected = ref([])
const editOpen = ref(false)
const editId = ref(null)
const detailOpen = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const snapshotOpen = ref(false)
const snapshots = ref([])
const snapshotNode = ref(null)
const rawOpen = ref(false)
const raw = ref({ object: 'clients', action: 'edit', data: '{}' })
const form = ref(emptyForm())

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
  detailLoading.value = true
  detail.value = null
  try { detail.value = (await api.get(`/nodes/${node.id}/details`)).data }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { detailLoading.value = false }
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

onMounted(load)
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

  <el-drawer v-model="detailOpen" title="节点实时详情" size="70%">
    <div v-loading="detailLoading">
      <div v-if="detail" class="detail-grid"><div v-for="key in ['status','clients','inbounds','onlines']" :key="key"><h4>{{ key }}</h4><pre class="json-box">{{ JSON.stringify(detail[key], null, 2) }}</pre></div></div>
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
