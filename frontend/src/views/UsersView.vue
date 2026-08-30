<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorText, formatBytes, formatTime } from '../api'

const users = ref([])
const nodes = ref([])
const loading = ref(false)
const query = ref('')
const editOpen = ref(false)
const editId = ref(null)
const syncOpen = ref(false)
const syncUser = ref(null)
const syncForm = ref({ node_ids: [], action: 'add' })
const plan = ref(null)
const syncing = ref(false)
const form = ref(emptyForm())

function emptyForm() {
  return { username: '', email: '', credential: '', enabled: true, total_gb: 0, expire_at: null, limit_ip: 0, notes: '' }
}

async function load() {
  loading.value = true
  try {
    const [userResponse, nodeResponse] = await Promise.all([api.get('/users', { params: { query: query.value } }), api.get('/nodes')])
    users.value = userResponse.data
    nodes.value = nodeResponse.data.filter((item) => item.enabled)
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { loading.value = false }
}

function addUser() {
  editId.value = null
  form.value = emptyForm()
  editOpen.value = true
}

function editUser(item) {
  editId.value = item.id
  form.value = { ...item, credential: '', expire_at: item.expire_at ? new Date(item.expire_at) : null }
  editOpen.value = true
}

async function saveUser() {
  const payload = { ...form.value }
  delete payload.bindings
  delete payload.credential_hint
  delete payload.created_at
  delete payload.updated_at
  delete payload.used_bytes
  if (!payload.credential) delete payload.credential
  try {
    const response = editId.value ? await api.patch(`/users/${editId.value}`, payload) : await api.post('/users', payload)
    editOpen.value = false
    if (response.data.generated_credential) {
      await ElMessageBox.alert(`<div>系统已生成客户端凭据，请立即保存：</div><div class="credential-box">${response.data.generated_credential}</div>`, '用户创建成功', { dangerouslyUseHTMLString: true, confirmButtonText: '我已保存' })
    } else {
      ElMessage.success(editId.value ? '中央用户已更新' : '中央用户已创建')
    }
    await load()
  } catch (error) { ElMessage.error(errorText(error)) }
}

async function removeUser(item) {
  try {
    await ElMessageBox.confirm(`删除中央用户“${item.username}”？该操作不会自动删除远程节点中的客户端。`, '确认删除', { type: 'warning' })
    await api.delete(`/users/${item.id}`)
    ElMessage.success('中央用户已删除')
    await load()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorText(error)) }
}

function openSync(item) {
  syncUser.value = item
  syncForm.value = { node_ids: item.bindings?.map((binding) => binding.node_id) || [], action: item.bindings?.length ? 'edit' : 'add' }
  plan.value = null
  syncOpen.value = true
}

async function previewSync() {
  if (!syncForm.value.node_ids.length) return ElMessage.warning('请选择至少一台节点')
  syncing.value = true
  try {
    plan.value = (await api.post(`/users/${syncUser.value.id}/sync`, { ...syncForm.value, dry_run: true })).data.plan
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { syncing.value = false }
}

async function executeSync() {
  if (!plan.value) return ElMessage.warning('请先生成同步预览')
  try {
    await ElMessageBox.confirm(`确认对 ${plan.value.nodes.length} 台节点执行 ${syncForm.value.action}？不同 S-UI 版本字段可能存在差异。`, '执行用户同步', { type: 'warning' })
    syncing.value = true
    const response = (await api.post(`/users/${syncUser.value.id}/sync`, { ...syncForm.value, dry_run: false })).data
    const failed = response.results.filter((item) => !item.ok).length
    syncOpen.value = false
    failed ? ElMessage.warning(`任务 #${response.job_id} 完成，${failed} 台失败`) : ElMessage.success(`任务 #${response.job_id} 同步成功`)
    await load()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorText(error)) }
  finally { syncing.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <div><h3>中央用户数据库</h3><span class="muted">维护统一用户资料，并通过预演后同步到指定节点</span></div>
    <el-button type="primary" @click="addUser">创建用户</el-button>
  </div>
  <el-alert class="notice" title="V2 首次同步必须先预演。S-UI 不同版本的 clients 字段可能不同，正式使用前请在测试节点验证。" type="info" show-icon :closable="false" />
  <div class="filters"><el-input v-model="query" clearable placeholder="搜索用户名或邮箱" @keyup.enter="load" /><el-button @click="load">查询</el-button></div>
  <el-card class="panel" shadow="never">
    <el-table :data="users" v-loading="loading">
      <el-table-column label="用户" min-width="170"><template #default="scope"><div class="table-primary">{{ scope.row.username }}</div><div class="table-secondary">{{ scope.row.email || scope.row.credential_hint }}</div></template></el-table-column>
      <el-table-column label="状态" width="90"><template #default="scope"><el-tag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
      <el-table-column label="流量" width="150"><template #default="scope"><div>{{ formatBytes(scope.row.used_bytes) }}</div><div class="muted">限额 {{ scope.row.total_gb ? `${scope.row.total_gb} GB` : '不限' }}</div></template></el-table-column>
      <el-table-column label="到期时间" width="180"><template #default="scope">{{ formatTime(scope.row.expire_at) }}</template></el-table-column>
      <el-table-column label="IP限制" width="90"><template #default="scope">{{ scope.row.limit_ip || '不限' }}</template></el-table-column>
      <el-table-column label="节点同步" min-width="180"><template #default="scope"><div class="tag-list"><el-tag v-for="binding in scope.row.bindings" :key="binding.id" size="small" :type="binding.sync_status === 'synced' ? 'success' : 'danger'">{{ binding.node_name }} · {{ binding.sync_status }}</el-tag><span v-if="!scope.row.bindings?.length" class="muted">尚未同步</span></div></template></el-table-column>
      <el-table-column label="操作" width="220" fixed="right"><template #default="scope"><el-button size="small" type="primary" plain @click="openSync(scope.row)">同步</el-button><el-button size="small" @click="editUser(scope.row)">编辑</el-button><el-button size="small" type="danger" text @click="removeUser(scope.row)">删除</el-button></template></el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="editOpen" :title="editId ? '编辑中央用户' : '创建中央用户'" width="620px">
    <el-form label-width="100px">
      <el-form-item label="用户名" required><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
      <el-form-item label="客户端凭据"><el-input v-model="form.credential" :placeholder="editId ? '留空表示不修改' : '留空自动生成 UUID'" /></el-form-item>
      <el-form-item label="总流量"><el-input-number v-model="form.total_gb" :min="0" :precision="2" /><span class="muted">&nbsp;GB，0表示不限</span></el-form-item>
      <el-form-item label="到期时间"><el-date-picker v-model="form.expire_at" type="datetime" placeholder="不设置表示永不过期" style="width:100%" /></el-form-item>
      <el-form-item label="IP数量"><el-input-number v-model="form.limit_ip" :min="0" :max="1000" /><span class="muted">&nbsp;0表示不限</span></el-form-item>
      <el-form-item label="状态"><el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="3" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="editOpen = false">取消</el-button><el-button type="primary" @click="saveUser">保存</el-button></template>
  </el-dialog>

  <el-dialog v-model="syncOpen" :title="`同步用户 · ${syncUser?.username || ''}`" width="680px">
    <el-form label-width="90px">
      <el-form-item label="操作"><el-radio-group v-model="syncForm.action" @change="plan = null"><el-radio-button value="add">新增</el-radio-button><el-radio-button value="edit">更新</el-radio-button><el-radio-button value="delete">删除</el-radio-button></el-radio-group></el-form-item>
      <el-form-item label="目标节点"><el-select v-model="syncForm.node_ids" multiple collapse-tags collapse-tags-tooltip placeholder="选择节点" style="width:100%" @change="plan = null"><el-option v-for="node in nodes" :key="node.id" :label="`${node.name} · ${node.region || '未知地区'}`" :value="node.id" /></el-select></el-form-item>
    </el-form>
    <el-card v-if="plan" shadow="never"><div><b>变更计划</b></div><p>动作：{{ plan.action }}；节点：{{ plan.nodes.map((item) => item.name).join('、') }}</p><pre class="json-box">{{ JSON.stringify(plan.payload, null, 2) }}</pre></el-card>
    <template #footer><el-button @click="syncOpen = false">取消</el-button><el-button :loading="syncing" @click="previewSync">1. 生成预览</el-button><el-button type="danger" :disabled="!plan" :loading="syncing" @click="executeSync">2. 确认执行</el-button></template>
  </el-dialog>
</template>
