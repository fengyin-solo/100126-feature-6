import { defineStore } from 'pinia'

export const ROLES = ['调度', '处置人员', '值班员'] as const

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '调度' as string,
    shiftLabel: '白班 08:00-20:00',
    scope: '冷链物流运输管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isDispatch: (state) => state.role === '调度',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: string) {
      this.role = role
    },
  },
})
