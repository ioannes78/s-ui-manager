<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errorText, formatTime } from '../api'

const data = ref({ summary: {}, nodes: [], recent_tasks: [] })
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = (await api.get('/dashboard')).data
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <div>
      <h3>全局运行状态</h3>
      <span class="muted">节点状态由后台健康监控定时更新</span>
    </div>
    <el-button type="primary" :loading="loading" @click="load">刷新数据</el-button>
  </div>

  <section class="metric-grid">
    <el-card class="metric-card" shadow="never"><div class="metric-label">节点总数</div><div class="metric-value">{{ data.summary.nodes || 0 }}</div></el-card>
    <el-card class="metric-card" shadow="never"><div class="metric-label">在线节点</div><div class="metric-value good">{{ data.summary.online_nodes || 0 }}</div></el-card>
    <el-card class="metric-card" shadow="never"><div class="metric-label">启用用户</div><div class="metric-value">{{ data.summary.enabled_users || 0 }}</div></el-card>
    <el-card class="metric-card" shadow="never"><div class="metric-label">7天内到期</div><div class="metric-value warn">{{ data.summary.expiring_users || 0 }}</div></el-card>
    <el-card class="metric-card" shadow="never"><div class="metric-label">未处理告警</div><div class="metric-value bad">{{ data.summary.open_alerts || 0 }}</div></el-card>
  </section>

  <el-card class="panel" shadow="never" v-loading="loading">
    <template #header><div class="panel-title"><b>节点概览</b><router-link to="/nodes">进入节点管理</router-link></div></template>
    <el-table :data="data.nodes">
      <el-table-column label="节点" min-width="170">
        <template #default="scope"><div class="table-primary">{{ scope.row.name }}</div><div class="table-secondary">{{ scope.row.region || '未设置地区' }} · {{ scope.row.group_name || '未分组' }}</div></template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="scope"><span class="node-status" :class="{ online: scope.row.online }"><i></i>{{ scope.row.online ? '在线' : '离线' }}</span></template>
      </el-table-column>
      <el-table-column prop="last_latency_ms" label="延迟" width="100"><template #default="scope">{{ scope.row.last_latency_ms == null ? '-' : `${scope.row.last_latency_ms} ms` }}</template></el-table-column>
      <el-table-column prop="sui_version" label="S-UI版本" width="130"><template #default="scope">{{ scope.row.sui_version || '-' }}</template></el-table-column>
      <el-table-column label="最近检查" width="180"><template #default="scope">{{ formatTime(scope.row.last_checked_at) }}</template></el-table-column>
      <el-table-column label="异常" min-width="220"><template #default="scope"><span :class="scope.row.last_error ? 'error-text' : 'muted'">{{ scope.row.last_error || '无' }}</span></template></el-table-column>
    </el-table>
  </el-card>

  <el-card class="panel" shadow="never">
    <template #header><div class="panel-title"><b>最近任务</b><router-link to="/tasks">查看全部</router-link></div></template>
    <el-table :data="data.recent_tasks">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="kind" label="任务类型" min-width="150" />
      <el-table-column label="结果" width="130"><template #default="scope"><span :class="`status-${scope.row.status}`">{{ scope.row.status }}</span></template></el-table-column>
      <el-table-column label="目标" width="160"><template #default="scope">{{ scope.row.success_count }}/{{ scope.row.target_count }} 成功</template></el-table-column>
      <el-table-column label="创建时间" width="190"><template #default="scope">{{ formatTime(scope.row.created_at) }}</template></el-table-column>
    </el-table>
  </el-card>
</template>
