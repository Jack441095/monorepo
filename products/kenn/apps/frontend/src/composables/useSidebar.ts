import { defineStore } from 'pinia'
import { SIDEBAR_KEY } from '../utils/keys'

export const useSidebarStore = defineStore(SIDEBAR_KEY, {
  state: () => ({
    collapsed: false,
  }),
  actions: {
    toggle() {
      this.collapsed = !this.collapsed
    },
    collapse() {
      this.collapsed = true
    },
    expand() {
      this.collapsed = false
    },
  },
  persist: {
    pick: ['collapsed'],
  },
})
