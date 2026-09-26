<template>
  <section class="page" data-module="temp">
    <header class="page-head">
      <div>
        <h2>温控监测管理</h2>
        <p class="page-desc">
          温度记录按 在控 → 预警 → 已处置 流转：超限自动转预警并派给处置人员，
          处置可挂起/恢复，已处置结论只能由调度退回到预警。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记温度记录</button>
        <button class="btn" type="button" @click="exportRows">导出温控监测清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card stat-clickable" @click="filterStatus(item.status)">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.cls">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="option in statusOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>处置人员</th>
          <th>操作时间线</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '温度状态'" class="status-badge" :class="badgeClass(row.display_status)">
              {{ row[column] ?? '—' }}
            </span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td>{{ row['处置人员'] ?? '—' }}</td>
          <td>
            <button class="link" type="button" @click="openTimeline(row)">
              {{ (row.history ?? []).length }} 步
            </button>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action.name"
              class="link"
              :class="action.cls"
              type="button"
              @click="openAction(action.name, row)"
            >
              {{ action.name }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">暂无温控监测数据，可先登记温度记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条温控监测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 预警/处置弹窗：状态直接取接口返回，和列表行是同一条数据口径 -->
    <div v-if="dialog.visible" class="modal-mask" @click.self="closeDialog">
      <div class="modal-card">
        <header class="modal-head">
          <h3>{{ dialog.title }}</h3>
          <button class="link" type="button" @click="closeDialog">关闭</button>
        </header>

        <div v-if="dialog.loading" class="modal-body">正在读取最新记录…</div>

        <div v-else-if="dialog.entry" class="modal-body">
          <div class="detail-grid">
            <div><span class="detail-label">记录编号</span>{{ dialog.entry['记录编号'] }}</div>
            <div><span class="detail-label">温区编号</span>{{ dialog.entry['温区编号'] }}</div>
            <div><span class="detail-label">关联调度</span>{{ dialog.entry['关联调度'] }}</div>
            <div><span class="detail-label">传感器编号</span>{{ dialog.entry['传感器编号'] ?? '—' }}</div>
            <div><span class="detail-label">设定温度</span>{{ dialog.entry['设定温度'] }} ℃</div>
            <div><span class="detail-label">实际温度</span>{{ dialog.entry['实际温度'] }} ℃</div>
            <div><span class="detail-label">偏离值</span>{{ dialog.entry['偏离值'] ?? '—' }} ℃</div>
            <div><span class="detail-label">阈值</span>{{ dialog.entry['偏差阈值'] ?? 2 }} ℃</div>
            <div><span class="detail-label">记录时间</span>{{ dialog.entry['记录时间'] }}</div>
            <div>
              <span class="detail-label">当前状态</span>
              <span class="status-badge" :class="badgeClass(dialog.entry.display_status)">
                {{ dialog.entry.display_status }}
              </span>
            </div>
            <div><span class="detail-label">处置人员</span>{{ dialog.entry['处置人员'] ?? '—' }}</div>
            <div><span class="detail-label">预警时间</span>{{ dialog.entry['预警时间'] ?? '—' }}</div>
            <div><span class="detail-label">处置时间</span>{{ dialog.entry['处置时间'] ?? '—' }}</div>
            <div class="detail-wide">
              <span class="detail-label">处置措施</span>{{ dialog.entry['处置措施'] ?? '—' }}
            </div>
            <div v-if="dialog.entry['退回原因']" class="detail-wide">
              <span class="detail-label">退回原因</span>{{ dialog.entry['退回原因'] }}
            </div>
          </div>

          <!-- 交班留痕：上一步的操作时间、操作人与备注 -->
          <section class="timeline">
            <h4>处置留痕（交班可见）</h4>
            <ol v-if="(dialog.entry.history ?? []).length">
              <li v-for="(item, index) in dialog.entry.history" :key="index">
                <span class="timeline-time">{{ item['操作时间'] }}</span>
                <span class="timeline-action">{{ item['动作'] }}</span>
                <span class="timeline-operator">{{ item['操作人'] }}</span>
                <span v-if="item['备注']" class="timeline-remark">{{ item['备注'] }}</span>
              </li>
            </ol>
            <p v-else class="muted-text">暂无处置动作记录</p>
          </section>

          <!-- 动作表单：按当前可执行动作渲染，后端再做一次强校验 -->
          <form v-if="dialog.action" class="action-form" @submit.prevent="submitAction">
            <template v-if="dialog.action === '转预警派单'">
              <label class="form-row">
                <span>上报实际温度（℃）</span>
                <input v-model="form.actual" type="number" step="0.1" :placeholder="String(dialog.entry['实际温度'] ?? '')" />
              </label>
              <label class="form-row">
                <span>派给处置人员<i>*</i></span>
                <input v-model="form.handler" placeholder="必须指定具体处置人员" />
              </label>
            </template>
            <label v-if="dialog.action === '挂起' || dialog.action === '恢复处置'" class="form-row">
              <span>备注</span>
              <textarea v-model="form.remark" :placeholder="dialog.action === '挂起' ? '为什么挂起，恢复条件是什么' : '恢复处置的说明'"></textarea>
            </label>
            <template v-if="dialog.action === '处置完成'">
              <label class="form-row">
                <span>处置措施<i>*</i></span>
                <textarea v-model="form.measure" placeholder="不填措施视为处置未完成，不能标记已处置"></textarea>
              </label>
            </template>
            <template v-if="dialog.action === '调度退回'">
              <label class="form-row">
                <span>操作角色<i>*</i></span>
                <select v-model="form.role">
                  <option value="">请选择身份</option>
                  <option value="调度">调度（仅调度可退回）</option>
                  <option value="处置人员">处置人员（无权退回）</option>
                </select>
              </label>
              <label class="form-row">
                <span>退回原因<i>*</i></span>
                <textarea v-model="form.returnReason" placeholder="退回后记录回到预警，温区编号与记录时间不变"></textarea>
              </label>
            </template>
            <label class="form-row">
              <span>操作人</span>
              <input v-model="form.operator" placeholder="默认取当前值班人" />
            </label>

            <p v-if="dialog.error" class="error-text">{{ dialog.error }}</p>
            <div class="modal-actions">
              <button class="btn" type="button" @click="closeDialog">取消</button>
              <button class="btn primary" type="submit" :disabled="dialog.submitting">
                {{ dialog.submitting ? '提交中…' : `确认${dialog.action}` }}
              </button>
            </div>
          </form>
          <div v-else class="modal-actions">
            <button class="btn" type="button" @click="closeDialog">关闭</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 登记温度记录 -->
    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal-card">
        <header class="modal-head">
          <h3>登记温度记录</h3>
          <button class="link" type="button" @click="createVisible = false">关闭</button>
        </header>
        <form class="modal-body" @submit.prevent="submitCreate">
          <label class="form-row"><span>记录编号<i>*</i></span><input v-model="createForm.code" /></label>
          <label class="form-row"><span>关联调度<i>*</i></span><input v-model="createForm.dispatch" /></label>
          <label class="form-row"><span>温区编号<i>*</i></span><input v-model="createForm.zone" /></label>
          <label class="form-row"><span>设定温度（℃）</span><input v-model="createForm.target" type="number" step="0.1" /></label>
          <label class="form-row"><span>实际温度（℃）</span><input v-model="createForm.actual" type="number" step="0.1" /></label>
          <label class="form-row"><span>偏差阈值（℃，默认 2）</span><input v-model="createForm.threshold" type="number" step="0.1" /></label>
          <label class="form-row"><span>传感器编号</span><input v-model="createForm.sensor" /></label>
          <label class="form-row">
            <span>处置人员（登记即超限时必填）</span>
            <input v-model="createForm.handler" placeholder="超过阈值时必须当场派单" />
          </label>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="createVisible = false">取消</button>
            <button class="btn primary" type="submit" :disabled="creating">{{ creating ? '提交中…' : '保存登记' }}</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type HistoryItem = { 动作: string; 操作人: string; 备注: string; 操作时间: string }
type Row = Record<string, string | number | null> & {
  id: number
  display_status: string
  history?: HistoryItem[]
  suspended?: boolean
}

type PageResult = { items: Row[]; total: number }
type ActionResult = { ok: boolean; message: string; entry?: Row }

const ENDPOINT = '/api/temp'
const columns = ['记录编号', '关联调度', '温区编号', '设定温度', '实际温度', '记录时间', '传感器编号', '温度状态']
const statusOptions = ['在控', '预警', '挂起中', '已处置']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const stats = ref([
  { label: '在控温区', value: 0, status: '在控', cls: 'text-ok' },
  { label: '预警待处置', value: 0, status: '预警', cls: 'text-warn' },
  { label: '挂起中', value: 0, status: '挂起中', cls: 'text-suspended' },
  { label: '已处置', value: 0, status: '已处置', cls: 'text-done' },
])

const emptyForm = () => ({
  actual: '',
  handler: '',
  remark: '',
  measure: '',
  returnReason: '',
  role: '',
  operator: '',
})

const dialog = reactive({
  visible: false,
  loading: false,
  submitting: false,
  title: '',
  action: '' as string,
  entry: null as Row | null,
  error: '',
})
const form = reactive(emptyForm())

function resetDialog() {
  dialog.visible = false
  dialog.loading = false
  dialog.submitting = false
  dialog.title = ''
  dialog.action = ''
  dialog.entry = null
  dialog.error = ''
  Object.assign(form, emptyForm())
}

function closeDialog() {
  resetDialog()
}

function badgeClass(status: string): string {
  if (status === '预警') return 'badge-warn'
  if (status === '挂起中') return 'badge-suspended'
  if (status === '已处置') return 'badge-done'
  return 'badge-ok'
}

/** 动作权限跟着后端状态机走：页面只暴露当前状态允许的动作。 */
function availableActions(row: Row): { name: string; cls?: string }[] {
  switch (row.display_status) {
    case '在控':
      return [{ name: '转预警派单', cls: 'danger-link' }]
    case '预警':
      return [
        { name: '挂起' },
        { name: '处置完成', cls: 'success-link' },
      ]
    case '挂起中':
      return [
        { name: '恢复处置', cls: 'success-link' },
      ]
    case '已处置':
      return [{ name: '调度退回' }]
    default:
      return []
  }
}

function filterStatus(status: string) {
  statusFilter.value = statusFilter.value === status ? '' : status
  void reload()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function openTimeline(row: Row) {
  await openDialog(row, '')
}

async function openAction(action: string, row: Row) {
  await openDialog(row, action)
}

/** 每次操作都重新拉一次详情：列表页与弹窗永远显示同一条最新记录。 */
async function openDialog(row: Row, action: string) {
  resetDialog()
  dialog.visible = true
  dialog.loading = true
  dialog.action = action
  dialog.title = action ? `${row['记录编号']} · ${action}` : `${row['记录编号']} · 超限处置`
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('记录明细读取失败')
    }
    dialog.entry = (await response.json()) as Row
    form.handler = String(dialog.entry['处置人员'] ?? '')
  } catch (error) {
    dialog.error = error instanceof Error ? error.message : '记录明细读取失败'
  } finally {
    dialog.loading = false
  }
}

function buildPayload(): Record<string, unknown> {
  const values: Record<string, unknown> = { action: dialog.action }
  if (dialog.action === '转预警派单') {
    if (form.actual !== '') values['实际温度'] = Number(form.actual)
    values['处置人员'] = form.handler
    values['备注'] = form.remark
  } else if (dialog.action === '挂起' || dialog.action === '恢复处置') {
    values['备注'] = form.remark
  } else if (dialog.action === '处置完成') {
    values['处置措施'] = form.measure
  } else if (dialog.action === '调度退回') {
    values['操作角色'] = form.role
    values['退回原因'] = form.returnReason
  }
  if (form.operator) values['操作人'] = form.operator
  return { values }
}

async function submitAction() {
  if (!dialog.entry) return
  dialog.error = ''
  dialog.submitting = true
  try {
    const response = await request(`${ENDPOINT}/${dialog.entry.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(buildPayload()),
    })
    const payload = (await response.json()) as ActionResult
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '温控监测动作未生效，请稍后重试')
    }
    resetDialog()
    await reload()
  } catch (error) {
    dialog.error = error instanceof Error ? error.message : '温控监测操作失败'
  } finally {
    dialog.submitting = false
  }
}

// ---- 登记 ----------------------------------------------------------------

const createVisible = ref(false)
const creating = ref(false)
const createError = ref('')
const createForm = reactive({
  code: '',
  dispatch: '',
  zone: '',
  target: '',
  actual: '',
  threshold: '',
  sensor: '',
  handler: '',
})

function openCreate() {
  createError.value = ''
  createVisible.value = true
}

async function submitCreate() {
  createError.value = ''
  const values: Record<string, unknown> = {
    记录编号: createForm.code,
    关联调度: createForm.dispatch,
    温区编号: createForm.zone,
    设定温度: createForm.target,
    实际温度: createForm.actual,
    传感器编号: createForm.sensor,
    处置人员: createForm.handler,
  }
  if (createForm.threshold !== '') values['偏差阈值'] = Number(createForm.threshold)
  creating.value = true
  try {
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = (await response.json()) as ActionResult
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '温度记录登记失败')
    }
    createVisible.value = false
    Object.assign(createForm, { code: '', dispatch: '', zone: '', target: '', actual: '', threshold: '', sensor: '', handler: '' })
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '温度记录登记失败'
  } finally {
    creating.value = false
  }
}

// ---- 列表与统计 ----------------------------------------------------------

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) params.set('keyword', keyword.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('温度记录列表读取失败')
    }
    const payload = (await response.json()) as PageResult
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 统计卡不受状态筛选影响，单独拉全量，保证四个数字口径固定。
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温控监测列表读取失败'
  }
}

async function reloadStats() {
  try {
    const [inControl, warning, suspended, handled] = await Promise.all(
      statusOptions.map((status) =>
        request(`${ENDPOINT}?status=${encodeURIComponent(status)}&size=1`).then((res) =>
          res.ok ? res.json() : Promise.resolve({ total: 0 }),
        ),
      ),
    )
    stats.value[0].value = inControl.total ?? 0
    stats.value[1].value = warning.total ?? 0
    stats.value[2].value = suspended.total ?? 0
    stats.value[3].value = handled.total ?? 0
  } catch {
    // 统计失败不阻塞列表，卡片保持 0，列表页脚会提示接口错误。
  }
}

onMounted(reload)
</script>

<style scoped>
.text-ok { color: #067647; }
.text-warn { color: #b54708; }
.text-suspended { color: #b42318; }
.text-done { color: #1f6feb; }
.stat-clickable { cursor: pointer; }

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 18px;
}
.badge-ok { background: #ecfdf3; color: #067647; border: 1px solid #abefc6; }
.badge-warn { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }
.badge-suspended { background: #fef3f2; color: #b42318; border: 1px solid #fda29b; }
.badge-done { background: #eff8ff; color: #1f6feb; border: 1px solid #b2ddff; }

.link.danger-link { color: #b42318; }
.link.success-link { color: #067647; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 16px;
  z-index: 100;
  overflow-y: auto;
}
.modal-card {
  background: #fff;
  border-radius: 10px;
  width: min(760px, 100%);
  box-shadow: 0 12px 32px rgba(16, 24, 40, 0.2);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
.modal-head h3 { margin: 0; font-size: 15px; }
.modal-body { padding: 16px 18px; }

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 14px;
  font-size: 13px;
}
.detail-wide { grid-column: 1 / -1; }
.detail-label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 2px;
}

.timeline { margin-top: 16px; }
.timeline h4 { margin: 0 0 8px; font-size: 13px; }
.timeline ol { margin: 0; padding-left: 18px; }
.timeline li {
  font-size: 12px;
  margin-bottom: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.timeline-time { color: var(--muted); }
.timeline-action { font-weight: 600; }
.timeline-operator { color: #1f6feb; }
.timeline-remark { flex-basis: 100%; color: #475569; }
.muted-text { color: var(--muted); font-size: 12px; }

.action-form {
  margin-top: 16px;
  border-top: 1px dashed var(--border);
  padding-top: 14px;
}
.form-row { display: block; margin-bottom: 10px; font-size: 13px; }
.form-row > span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-row i { color: #b42318; font-style: normal; }
.form-row input,
.form-row textarea,
.form-row select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font: inherit;
}
.form-row textarea { min-height: 60px; resize: vertical; }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>
