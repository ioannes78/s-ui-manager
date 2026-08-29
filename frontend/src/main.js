import { createApp, ref, computed, onMounted } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import axios from 'axios'
import './style.css'

const api=axios.create({baseURL:'/api'})
api.interceptors.request.use(c=>{
  const t=localStorage.getItem('token'); if(t) c.headers.Authorization='Bearer '+t; return c
})

const App={
setup(){
 const logged=ref(!!localStorage.getItem('token')), user=ref('admin'), pass=ref(''), nodes=ref([]),
 dashboard=ref({nodes:[]}), logs=ref([]), loading=ref(false), addOpen=ref(false), rawOpen=ref(false)
 const form=ref({name:'',region:'',base_url:'',api_token:'',verify_tls:true,enabled:true})
 const raw=ref({node_ids:[],object:'clients',action:'edit',data:'{}',initUsers:null})
 const selected=ref([])
 const onlineCount=computed(()=>dashboard.value.nodes?.filter(x=>x.online).length||0)

 async function login(){
   try{let r=await api.post('/login',{username:user.value,password:pass.value}); localStorage.setItem('token',r.data.access_token); logged.value=true; await refresh()}
   catch(e){ElementPlus.ElMessage?.error?.('登录失败')}
 }
 function logout(){localStorage.removeItem('token');logged.value=false}
 async function refresh(){
   loading.value=true
   try{
    let [n,d,l]=await Promise.all([api.get('/nodes'),api.get('/dashboard'),api.get('/audit?limit=50')])
    nodes.value=n.data; dashboard.value=d.data; logs.value=l.data
   }catch(e){if(e.response?.status===401) logout()}
   finally{loading.value=false}
 }
 async function addNode(){await api.post('/nodes',form.value); addOpen.value=false; form.value={name:'',region:'',base_url:'',api_token:'',verify_tls:true,enabled:true}; await refresh()}
 async function testNode(id){let r=await api.post(`/nodes/${id}/test`); alert(r.data.ok?'连接成功':'连接失败：'+r.data.error); await refresh()}
 async function delNode(id){if(confirm('确定删除该节点？')){await api.delete(`/nodes/${id}`);await refresh()}}
 async function restartCore(){if(!selected.value.length)return alert('请选择节点'); await api.post('/actions/restart-core',{node_ids:selected.value}); await refresh()}
 async function rawSave(){
   let data; try{data=JSON.parse(raw.value.data)}catch{return alert('data 不是合法 JSON')}
   let payload={...raw.value,node_ids:selected.value,data}; if(!payload.node_ids.length)return alert('请选择节点')
   let r=await api.post('/actions/raw-save',payload); alert(JSON.stringify(r.data,null,2)); rawOpen.value=false; await refresh()
 }
 function shape(x){ if(x==null)return '-'; if(typeof x==='string'||typeof x==='number')return x; return JSON.stringify(x).slice(0,160)}
 return {logged,user,pass,nodes,dashboard,logs,loading,addOpen,rawOpen,form,raw,selected,onlineCount,
         login,logout,refresh,addNode,testNode,delNode,restartCore,rawSave,shape}
},
template:`
<div v-if="!logged" class="login"><el-card><h2>S-UI Manager</h2><el-input v-model="user" placeholder="用户名"/><el-input v-model="pass" type="password" placeholder="密码" @keyup.enter="login"/><el-button type="primary" @click="login">登录</el-button></el-card></div>
<div v-else class="layout">
 <aside><div class="brand">S-UI Manager <small>V1.0</small></div><div class="menu">Dashboard<br>节点管理<br>批量操作<br>审计日志</div><el-button text @click="logout">退出</el-button></aside>
 <main>
  <header><h2>统一控制台</h2><div><el-button @click="refresh">刷新</el-button><el-button type="primary" @click="addOpen=true">添加 VPS</el-button></div></header>
  <section class="cards">
   <el-card><div class="kpi">{{nodes.length}}</div><div>节点总数</div></el-card>
   <el-card><div class="kpi">{{onlineCount}}</div><div>在线节点</div></el-card>
   <el-card><div class="kpi">{{selected.length}}</div><div>已选节点</div></el-card>
  </section>
  <el-card>
   <template #header><div class="row"><b>节点</b><div><el-button @click="restartCore">批量重启 Core</el-button><el-button type="warning" @click="rawOpen=true">高级批量写入</el-button></div></div></template>
   <el-table :data="dashboard.nodes" v-loading="loading">
    <el-table-column width="55"><template #default="s"><el-checkbox :model-value="selected.includes(s.row.node.id)" @change="v=>v?selected.push(s.row.node.id):selected.splice(selected.indexOf(s.row.node.id),1)"/></template></el-table-column>
    <el-table-column label="节点" min-width="150"><template #default="s"><b>{{s.row.node.name}}</b><div class="muted">{{s.row.node.region}}</div></template></el-table-column>
    <el-table-column label="状态" width="95"><template #default="s"><el-tag :type="s.row.online?'success':'danger'">{{s.row.online?'在线':'离线'}}</el-tag></template></el-table-column>
    <el-table-column label="S-UI Status"><template #default="s"><span class="mono">{{shape(s.row.status?.obj||s.row.status)}}</span></template></el-table-column>
    <el-table-column label="操作" width="190"><template #default="s"><el-button size="small" @click="testNode(s.row.node.id)">测试</el-button><el-button size="small" type="danger" @click="delNode(s.row.node.id)">删除</el-button></template></el-table-column>
   </el-table>
  </el-card>
  <el-card style="margin-top:18px"><template #header><b>最近操作</b></template>
   <el-table :data="logs"><el-table-column prop="created_at" label="时间" width="180"/><el-table-column prop="action" label="动作" width="170"/><el-table-column prop="target" label="目标"/><el-table-column prop="actor" label="操作者" width="100"/></el-table>
  </el-card>
 </main>
 <el-dialog v-model="addOpen" title="添加 S-UI 节点" width="520px">
  <el-form label-width="100px">
   <el-form-item label="名称"><el-input v-model="form.name"/></el-form-item>
   <el-form-item label="地区"><el-input v-model="form.region"/></el-form-item>
   <el-form-item label="面板地址"><el-input v-model="form.base_url" placeholder="https://host.example.com/app"/></el-form-item>
   <el-form-item label="API Token"><el-input v-model="form.api_token" type="password"/></el-form-item>
   <el-form-item label="校验 TLS"><el-switch v-model="form.verify_tls"/></el-form-item>
  </el-form>
  <template #footer><el-button @click="addOpen=false">取消</el-button><el-button type="primary" @click="addNode">保存并测试</el-button></template>
 </el-dialog>
 <el-dialog v-model="rawOpen" title="高级批量写入（兼容模式）" width="650px">
  <el-alert title="会直接调用各节点 /apiv2/save，请先备份数据库并在单节点验证 payload。" type="warning" show-icon :closable="false"/>
  <el-form label-width="95px" style="margin-top:15px">
   <el-form-item label="对象"><el-select v-model="raw.object"><el-option v-for="x in ['clients','inbounds','outbounds','tls','services','endpoints','config','settings']" :key="x" :label="x" :value="x"/></el-select></el-form-item>
   <el-form-item label="动作"><el-input v-model="raw.action"/></el-form-item>
   <el-form-item label="data JSON"><el-input v-model="raw.data" type="textarea" :rows="12"/></el-form-item>
  </el-form>
  <template #footer><el-button @click="rawOpen=false">取消</el-button><el-button type="danger" @click="rawSave">执行批量写入</el-button></template>
 </el-dialog>
</div>`
}
createApp(App).use(ElementPlus).mount('#app')
