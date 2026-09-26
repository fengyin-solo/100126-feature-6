<template>
  <!-- 监测列表与预警弹窗统一使用该组件，保证同一条记录两处状态显示完全一致 -->
  <span class="badge" :class="tone">{{ status || '—' }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status?: string }>()

const TONES: Record<string, string> = {
  在控: 'ok',
  预警: 'warn',
  挂起: 'hold',
  已处置: 'done',
}

const tone = computed(() => TONES[props.status ?? ''] ?? 'done')
</script>
