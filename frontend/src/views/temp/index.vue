<template>
  <section class="page" data-module="temp">
    <header class="page-head">
      <div>
        <h2>温控监测管理</h2>
        <p class="page-desc">温度记录围绕记录编号、关联调度、温区编号登记；超限后按「在控 → 预警 → 已处置」流转，可挂起恢复，已处置记录由调度退回。</p>
      </div>
      <div class="page-actions">
        <button class="btn warn" type="button" @click="openAlerts">
          超限预警（{{ alertRows.length }}）
        </button>
        <button class="btn primary" type="button" @click="openCreate">登记温度记录</button>
        <button class="btn" type="button" @click="exportRows">导出温控监测清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent>
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>处置状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>我的岗位</span>
        <select v-model="store.role">
          <option v-for="role in ROLES" :key="role" :value="role">{{ role }}</option>
        </select>
      </label>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>处置状态</th>
          <th>处置人员</th>
          <th>上一步操作</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in filteredRows" :key="row.id">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td><StatusBadge :status="row.status" /></td>
          <td>{{ row.处置人员 || '—' }}</td>
          <td class="cell-note">
            <template v-if="lastTrail(row)">
              <div>{{ lastTrail(row)?.操作 }} · {{ lastTrail(row)?.操作人 }}</div>
              <div class="muted-note">{{ lastTrail(row)?.时间 }}</div>
              <div class="muted-note">{{ lastTrail(row)?.备注 }}</div>
            </template>
            <span v-else>—</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              :disabled="action === '调度退回' && !store.isDispatch"
              :title="action === '调度退回' && !store.isDispatch ? '只有调度岗位可以退回已处置记录' : ''"
              @click="openAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="trailRow = row">轨迹</button>
          </td>
        </tr>
        <tr v-if="!filteredRows.length">
          <td :colspan="columns.length + 4" class="empty-state">暂无符合条件的温控监测记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条温控监测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 超限预警弹窗：与列表共用 allRows 数据源和 StatusBadge，状态必然一致 -->
    <div v-if="showAlerts" class="modal-mask" @click.self="showAlerts = false">
      <div class="modal-card modal-wide">
        <div class="modal-head">
          <h3>超限预警（{{ alertRows.length }} 条待跟进）</h3>
          <button class="link" type="button" @click="showAlerts = false">关闭</button>
        </div>
        <p class="page-desc">只列出「预警 / 挂起」记录；挂起记录请走「恢复处置」回到预警后再闭环。</p>
        <div v-for="row in alertRows" :key="row.id" class="alert-item">
          <div class="alert-top">
            <strong>{{ row.记录编号 }} · {{ row.温区编号 }}</strong>
            <StatusBadge :status="row.status" />
          </div>
          <div class="alert-meta">
            设定 {{ row.设定温度 ?? '—' }}℃ / 实际 {{ row.实际温度 ?? '—' }}℃
            <span v-if="row.偏离值 != null">· 偏离 {{ row.偏离值 }}℃</span>
            · 处置人员：{{ row.处置人员 || '未指派' }}
          </div>
          <div class="muted-note">
            上一步：{{ lastTrail(row)?.时间 }} {{ lastTrail(row)?.操作 }}（{{ lastTrail(row)?.操作人 }}）— {{ lastTrail(row)?.备注 }}
          </div>
          <div class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="openAction(action, row); showAlerts = false"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="trailRow = row; showAlerts = false">轨迹</button>
          </div>
        </div>
        <div v-if="!alertRows.length" class="empty-state">当前没有待处置的超限预警</div>
      </div>
    </div>

    <!-- 动作对话框 -->
    <div v-if="actionDialog" class="modal-mask" @click.self="closeAction">
      <div class="modal-card">
        <div class="modal-head">
          <h3>{{ actionDialog.action }} · {{ actionDialog.row.记录编号 }}</h3>
          <button class="link" type="button" @click="closeAction">取消</button>
        </div>
        <p class="page-desc">
          当前状态 <StatusBadge :status="actionDialog.row.status" />
          ｜设定 {{ actionDialog.row.设定温度 ?? '—' }}℃ / 实际 {{ actionDialog.row.实际温度 ?? '—' }}℃
          ｜阈值 {{ actionDialog.row.温度阈值 ?? 2 }}℃
        </p>
        <div class="form-grid">
          <label class="form-item">
            <span>操作人</span>
            <input v-model="actionForm.操作人" />
          </label>
          <label class="form-item">
            <span>岗位（调度退回限“调度”）</span>
            <input :value="store.role" disabled />
          </label>
          <label v-for="field in ACTION_FIELDS[actionDialog.action]" :key="field.key" class="form-item">
            <span>{{ field.label }}<em v-if="field.required" class="required">*</em></span>
            <textarea
              v-if="field.kind === 'textarea'"
              v-model="actionForm[field.key]"
              rows="3"
            ></textarea>
            <input
              v-else
              :type="field.kind === 'number' ? 'number' : 'text'"
              v-model="actionForm[field.key]"
            />
          </label>
        </div>
        <p v-if="actionError" class="error-text">{{ actionError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="closeAction">取消</button>
          <button class="btn primary" type="button" :disabled="actionBusy" @click="submitAction">
            确认{{ actionDialog.action }}
          </button>
        </div>
      </div>
    </div>

    <!-- 登记对话框 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal-card">
        <div class="modal-head">
          <h3>登记温度记录</h3>
          <button class="link" type="button" @click="showCreate = false">取消</button>
        </div>
        <p class="page-desc">登记读数若偏离设定温度超过阈值，将自动转为预警，此时处置人员为必填。</p>
        <div class="form-grid">
          <label v-for="field in createFields" :key="field.key" class="form-item">
            <span>{{ field.label }}<em v-if="field.required" class="required">*</em></span>
            <input
              v-model="createForm[field.key]"
              :type="field.kind === 'number' ? 'number' : 'text'"
              :placeholder="field.placeholder ?? ''"
            />
          </label>
        </div>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" type="button" :disabled="createBusy" @click="submitCreate">确认登记</button>
        </div>
      </div>
    </div>

    <!-- 处置轨迹：交班核对用 -->
    <div v-if="trailRow" class="modal-mask" @click.self="trailRow = null">
      <div class="modal-card modal-wide">
        <div class="modal-head">
          <h3>处置轨迹 · {{ trailRow.记录编号 }}（温区 {{ trailRow.温区编号 }}）</h3>
          <button class="link" type="button" @click="trailRow = null">关闭</button>
        </div>
        <p class="page-desc">每一步流转的时间、操作人与备注均留痕；调度退回只推翻处置结论，温区编号与记录时间保持不变。</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作</th>
              <th>操作人 / 岗位</th>
              <th>备注</th>
              <th>结果状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in trailRow.处置轨迹 ?? []" :key="index">
              <td>{{ item.时间 }}</td>
              <td>{{ item.操作 }}</td>
              <td>{{ item.操作人 }} / {{ item.岗位 }}</td>
              <td>{{ item.备注 }}</td>
              <td><StatusBadge :status="item.结果状态" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { ROLES, useSessionStore } from '@/stores/session'

interface TrailItem {
  时间: string
  操作: string
  操作人: string
  岗位: string
  备注: string
  结果状态: string
}

interface TempRow {
  id: number
  status: string
  记录编号?: string
  关联调度?: string
  温区编号?: string
  设定温度?: number | string
  实际温度?: number | string
  温度阈值?: number
  记录时间?: string
  传感器编号?: string
  处置人员?: string
  偏离值?: number
  处置轨迹?: TrailItem[]
}

interface FieldDef {
  key: string
  label: string
  required?: boolean
  kind?: 'textarea' | 'number'
  placeholder?: string
}

interface ActionResultPayload {
  ok: boolean
  message?: string
}

const ENDPOINT = '/api/temp'
const store = useSessionStore()

const columns = [
  '记录编号',
  '关联调度',
  '温区编号',
  '设定温度',
  '实际温度',
  '温度阈值',
  '记录时间',
  '传感器编号',
] as const
const statuses = ['在控', '预警', '挂起', '已处置']

// 动作表单字段：必填项由后端再次校验，前端先拦一道给出即时提示。
const ACTION_FIELDS: Record<string, FieldDef[]> = {
  转预警: [
    { key: '处置人员', label: '处置人员', required: true },
    { key: '实际温度', label: '实际温度（℃，留空沿用当前读数）', kind: 'number' },
    { key: '备注', label: '备注' },
  ],
  处置完成: [
    { key: '处置措施', label: '处置措施（完成后才能标记已处置）', required: true, kind: 'textarea' },
    { key: '备注', label: '备注' },
  ],
  挂起: [{ key: '挂起原因', label: '挂起原因', required: true }],
  恢复处置: [{ key: '备注', label: '备注' }],
  调度退回: [{ key: '退回原因', label: '退回原因', required: true }],
}
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  在控: ['转预警'],
  预警: ['处置完成', '挂起'],
  挂起: ['恢复处置'],
  已处置: ['调度退回'],
}
const createFields: FieldDef[] = [
  { key: '记录编号', label: '记录编号', required: true, placeholder: '如 TEMP-0010' },
  { key: '关联调度', label: '关联调度', required: true, placeholder: '调度编号' },
  { key: '温区编号', label: '温区编号', required: true },
  { key: '设定温度', label: '设定温度（℃）', kind: 'number' },
  { key: '实际温度', label: '实际温度（℃）', kind: 'number' },
  { key: '温度阈值', label: '温度阈值（℃，默认 2）', kind: 'number' },
  { key: '记录时间', label: '记录时间', placeholder: 'YYYY-MM-DD HH:mm:ss' },
  { key: '传感器编号', label: '传感器编号' },
  { key: '处置人员', label: '处置人员（超限登记时必填）' },
]

const allRows = ref<TempRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const showAlerts = ref(false)
const showCreate = ref(false)
const trailRow = ref<TempRow | null>(null)
const actionDialog = ref<{ action: string; row: TempRow } | null>(null)
const actionForm = ref<Record<string, string>>({})
const actionError = ref('')
const actionBusy = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')
const createBusy = ref(false)

const filteredRows = computed(() =>
  allRows.value.filter((row) => {
    const word = keyword.value.trim()
    const hitKeyword = !word || String(row.记录编号 ?? '').includes(word)
    const hitStatus = !statusFilter.value || row.status === statusFilter.value
    return hitKeyword && hitStatus
  }),
)
// 预警弹窗只筛选不另取数据：列表与弹窗看到的状态永远是同一份。
const alertRows = computed(() =>
  allRows.value.filter((row) => row.status === '预警' || row.status === '挂起'),
)
const stats = computed(() =>
  statuses.map((status) => ({
    label: status === '已处置' ? '已处置' : `${status}${status === '在控' ? '温区' : ''}`,
    value: allRows.value.filter((row) => row.status === status).length,
  })),
)

function lastTrail(row: TempRow): TrailItem | undefined {
  return row.处置轨迹?.[row.处置轨迹.length - 1]
}

function actionsFor(row: TempRow): string[] {
  return ACTIONS_BY_STATUS[row.status] ?? []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    if (!response.ok) {
      throw new Error('温度记录列表读取失败')
    }
    const payload = (await response.json()) as { items?: TempRow[]; total?: number }
    allRows.value = payload.items ?? []
    total.value = payload.total ?? allRows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温控监测列表读取失败'
  }
}

async function openAlerts() {
  await reload()
  showAlerts.value = true
}

function openCreate() {
  createError.value = ''
  createForm.value = { 温度阈值: '2' }
  showCreate.value = true
}

function openAction(action: string, row: TempRow) {
  actionError.value = ''
  actionForm.value = { 操作人: store.operator, 备注: '' }
  if (action === '转预警' && row.处置人员) {
    actionForm.value.处置人员 = String(row.处置人员)
  }
  actionDialog.value = { action, row }
}

function closeAction() {
  actionDialog.value = null
  actionError.value = ''
}

async function submitAction() {
  const dialog = actionDialog.value
  if (!dialog) {
    return
  }
  const unfilled = ACTION_FIELDS[dialog.action]
    .filter((field) => field.required)
    .filter((field) => !String(actionForm.value[field.key] ?? '').trim())
  if (unfilled.length) {
    actionError.value = `请填写：${unfilled.map((field) => field.label).join('、')}`
    return
  }
  actionBusy.value = true
  actionError.value = ''
  try {
    const values: Record<string, string> = {
      action: dialog.action,
      岗位: store.role,
      ...actionForm.value,
    }
    const response = await request(`${ENDPOINT}/${dialog.row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const result = (await response.json()) as ActionResultPayload
    if (!response.ok || !result.ok) {
      actionError.value = result.message || '操作未生效，请稍后重试'
      return
    }
    closeAction()
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '温控监测操作失败'
  } finally {
    actionBusy.value = false
  }
}

async function submitCreate() {
  const unfilled = createFields
    .filter((field) => field.required)
    .filter((field) => !String(createForm.value[field.key] ?? '').trim())
  if (unfilled.length) {
    createError.value = `请填写：${unfilled.map((field) => field.label).join('、')}`
    return
  }
  createBusy.value = true
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: { ...createForm.value, 操作人: store.operator, 岗位: store.role },
      }),
    })
    const result = (await response.json()) as ActionResultPayload
    if (!response.ok || !result.ok) {
      createError.value = result.message || '登记未生效，请稍后重试'
      return
    }
    showCreate.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '温度记录登记失败'
  } finally {
    createBusy.value = false
  }
}

onMounted(reload)
</script>
