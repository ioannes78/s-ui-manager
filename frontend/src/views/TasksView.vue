<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errorText, formatTime } from '../api'

const tasks = ref([])
const status = ref('')
const loading = ref(false)
const detailOpen = ref(false)
const detail = ref(null)

async function load() {
  loading.value = true
  try { tasks.value = (await api.get('/tasks', { params: { status: status.value } })).data }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { loading.value = false }
}

async function showDetail(task) {
  try {
    detail.value = (await api.get(`/tasks/${task.id}`)).data
    detailOpen.value = true
  } catch (error) { ElMessage.error(errorText(error)) }
}

onMounted(load)
</script>

<template>
  <div class="page-head"><div><h3>批量任务与执行结果</h3><span class="muted">每一个目标节点均保留独立的成功或失败记录</span></div><el-button :loading="loading" @click="load">刷新</el-button></div>
  <div class="filters"><el-select v-model="status" clearable placeholder="全部状态" @change="load"><el-option v-for="item in ['running','success','partial','failed']" :key="item" :label="item" :value="item" /></el-select></div>
  <el-card class="panel" shadow="never">
    <el-table :data="tasks" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="任务" min-width="180"><template #default="scope"><div class="table-primary">{{ scope.row.kind }}</div><div class="table-secondary">操作者：{{ scope.row.actor }}</div></template></el-table-column>
      <el-table-column label="状态" width="110"><template #default="scope"><b :class="`status-${scope.row.status}`">{{ scope.row.status }}</b></template></el-table-column>
      <el-table-column label="执行结果" width="220"><template #default="scope"><div class="progress-line"><el-progress :percentage="scope.row.target_count ? Math.round(scope.row.success_count / scope.row.target_count * 100) : 0" :show-text="false" /><span>{{ scope.row.success_count }}成功 / {{ scope.row.failure_count }}失败</span></div></template></el-table-column>
      <el-table-column label="创建时间" width="185"><template #default="scope">{{ formatTime(scope.row.created_at) }}</template></el-table-column>
      <el-table-column width="95" fixed="right"><template #default="scope"><el-button size="small" @click="showDetail(scope.row)">详情</el-button></template></el-table-column>
    </el-table>
  </el-card>
  <el-drawer v-model="detailOpen" :title="`任务 #${detail?.id || ''}`" size="680px">
    <template v-if="detail"><div class="detail-grid"><div class="detail-item"><label>类型</label>{{ detail.kind }}</div><div class="detail-item"><label>状态</label>{{ detail.status }}</div><div class="detail-item"><label>创建时间</label>{{ formatTime(detail.created_at) }}</div><div class="detail-item"><label>完成时间</label>{{ formatTime(detail.finished_at) }}</div></div><h4>目标执行结果</h4><el-table :data="detail.targets"><el-table-column prop="target_name" label="节点" /><el-table-column label="状态" width="100"><template #default="scope"><span :class="`status-${scope.row.status}`">{{ scope.row.status }}</span></template></el-table-column><el-table-column label="结果" min-width="260"><template #default="scope"><pre class="json-box">{{ JSON.stringify(scope.row.detail, null, 2) }}</pre></template></el-table-column></el-table></template>
  </el-drawer>
</template>
