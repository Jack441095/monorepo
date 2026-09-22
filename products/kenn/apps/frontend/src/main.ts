import './utils/rem'
import './styles/index.less'
import { createApp } from 'vue'
import router from './router'
import App from './App.vue'
import { i18n } from './locales'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import { useLocaleStore } from './composables/useLocale.ts'

// The studio surface defaults to a projector-friendly Ableton-style theme.
document.documentElement.dataset.theme ||= 'dark'

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

const app = createApp(App)
app.use(pinia)
useLocaleStore().initLocale()
app.use(router).use(i18n).mount('#app')
