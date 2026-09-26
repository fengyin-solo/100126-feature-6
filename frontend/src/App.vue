<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">冷链物流运输管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向冷链运输全程温控、车辆调度、门到门配送、温度异常处置、签收回单与运力结算的冷链运输管理后台。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.role }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "车辆档案", path: "/fleet" }, { label: "司机管理", path: "/driver" }, { label: "运输委托", path: "/order" }, { label: "运力调度", path: "/dispatch3" }, { label: "温控监测", path: "/temp" }, { label: "门到门配送", path: "/door" }, { label: "回单管理", path: "/returntrip" }, { label: "异常处置", path: "/abnormal2" }, { label: "续运中转", path: "/renew" }, { label: "制冷机组", path: "/refriger" }, { label: "温控箱体", path: "/box" }, { label: "运输路线", path: "/route" }, { label: "温感器管理", path: "/sensor" }, { label: "运输费用", path: "/cost" }, { label: "委托方管理", path: "/client2" }, { label: "出车检查", path: "/checkin" }, { label: "事故记录", path: "/accident" }, { label: "途中核查", path: "/roadcheck" }, { label: "车厢清洗", path: "/clean2" }, { label: "合作合同", path: "/contract2" }]
</script>
