<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errorText, formatTime } from '../api'

const rows = ref([])
const query = ref('')
const loading = ref(false)
const detailOpen = ref(false)
const detail = ref(null)

async function load() {
  loading.value = true
  try { rows.value = (await api.get('/audit', { params: { query: query.value, limit: 200 } })).data }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { loading.value = false }
}

function showDetail(row) { detail.value = row; detailOpen.value = true }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><h3>操作审计日志</h3><span class="muted">记录节点、用户、任务、快照和告警操作</span></div><el-button :loading="loading" @click="load">刷新</el-button></div>
  <div class="filters"><el-input v-model="query" clearable placeholder="搜索目标或详情" @keyup.enter="load" /><el-button @click="load">查询</el-button></div>
  <el-card class="panel" shadow="never">
    <el-table :data="rows" v-loading="loading">
      <el-table-column label="时间" width="185"><template #default="scope">{{ formatTime(scope.row.created_at) }}</template></el-table-column>
      <el-table-column prop="actor" label="操作者" width="120" />
      <el-table-column prop="action" label="动作" width="190" />
      <el-table-column prop="target" label="目标" min-width="180" />
      <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
      <el-table-column width="90"><template #default="scope"><el-button size="small" @click="showDetail(scope.row)">查看</el-button></template></el-table-column>
    </el-table>
  </el-card>
  <el-drawer v-model="detailOpen" title="审计详情" size="560px"><template v-if="detail"><div class="detail-grid"><div class="detail-item"><label>时间</label>{{ formatTime(detail.created_at) }}</div><div class="detail-item"><label>操作者</label>{{ detail.actor }}</div><div class="detail-item"><label>动作</label>{{ detail.action }}</div><div class="detail-item"><label>目标</label>{{ detail.target }}</div></div><h4>详细内容</h4><pre class="json-box">{{ detail.detail || '无' }}</pre></template></el-drawer>
</template>
