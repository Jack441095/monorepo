// i18n 入口
import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'
import { LOCALE_KEY } from '../utils/keys'
import type { Locale } from '../utils/types'

// 获取默认语言
const getDefaultLocale = (): Locale => {
    try {
        const stored = localStorage.getItem(LOCALE_KEY)
        if (stored) {
            const parsed = JSON.parse(stored) as { locale?: Locale }
            if (parsed.locale === 'zh-CN' || parsed.locale === 'en-US') return parsed.locale
        }
    } catch {
        // 本地缓存损坏时忽略，走默认语言
    }
    return 'en-US'
}

export const i18n = createI18n({
    legacy: false,           // Vue 3 组合式 API 用 false
    locale: getDefaultLocale(),
    fallbackLocale: 'en-US',
    messages: {
      'zh-CN': zhCN,
      'en-US': enUS,
    },
  })