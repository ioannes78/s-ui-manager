import { createApp } from 'vue'
import {
  ElAlert, ElButton, ElCard, ElCheckbox, ElDatePicker, ElDialog, ElDrawer, ElEmpty,
  ElForm, ElFormItem, ElInput, ElInputNumber, ElLoading, ElOption, ElProgress,
  ElRadioButton, ElRadioGroup, ElSelect, ElSwitch, ElTable, ElTableColumn, ElTabPane,
  ElTabs, ElTag,
} from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import { router } from './router'

const application = createApp(App)
const elementComponents = [
  ElAlert, ElButton, ElCard, ElCheckbox, ElDatePicker, ElDialog, ElDrawer, ElEmpty,
  ElForm, ElFormItem, ElInput, ElInputNumber, ElLoading, ElOption, ElProgress,
  ElRadioButton, ElRadioGroup, ElSelect, ElSwitch, ElTable, ElTableColumn, ElTabPane,
  ElTabs, ElTag,
]
elementComponents.forEach((component) => application.use(component))
application.use(router).mount('#app')
