<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errorText, formatTime } from '../api'

const alerts = ref([])
const status = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try { alerts.value = (await api.get('/alerts', { params: { status: status.value } })).data }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { loading.value = false }
}

async function update(alert, action) {
  try {
    await api.patch(`/alerts/${alert.id}`, { action })
    ElMessage.success('告警状态已更新')
    await load()
  } catch (error) { ElMessage.error(errorText(error)) }
}

onMounted(load)
</script>

<template>
  <div class="page-head"><div><h3>节点健康告警</h3><span class="muted">后台按照配置周期检查启用节点，恢复后自动关闭离线告警</span></div><el-button :loading="loading" @click="load">立即刷新</el-button></div>
  <div class="filters"><el-select v-model="status" clearable placeholder="全部状态" @change="load"><el-option v-for="item in ['open','acknowledged','resolved']" :key="item" :label="item" :value="item" /></el-select></div>
  <el-card class="panel" shadow="never">
    <el-table :data="alerts" v-loading="loading">
      <el-table-column label="级别" width="90"><template #default="scope"><el-tag :type="scope.row.severity === 'critical' ? 'danger' : 'warning'">{{ scope.row.severity }}</el-tag></template></el-table-column>
      <el-table-column label="节点" width="150"><template #default="scope"><div class="table-primary">{{ scope.row.node_name || '-' }}</div><div class="table-secondary">{{ scope.row.alert_type }}</div></template></el-table-column>
      <el-table-column prop="message" label="告警信息" min-width="300" show-overflow-tooltip />
      <el-table-column label="状态" width="130"><template #default="scope">{{ scope.row.status }}</template></el-table-column>
      <el-table-column label="最后发生" width="185"><template #default="scope">{{ formatTime(scope.row.last_seen_at) }}</template></el-table-column>
      <el-table-column label="操作" width="175" fixed="right"><template #default="scope"><el-button v-if="scope.row.status === 'open'" size="small" @click="update(scope.row, 'acknowledge')">确认</el-button><el-button v-if="scope.row.status !== 'resolved'" size="small" type="success" plain @click="update(scope.row, 'resolve')">解决</el-button><el-button v-else size="small" @click="update(scope.row, 'reopen')">重开</el-button></template></el-table-column>
    </el-table>
  </el-card>
</template>
