import { defineStore } from "pinia";
import { LOCALE_KEY } from "../utils/keys";
import type { Locale } from "../utils/types";
import { i18n } from "../locales";

/**
 * 多语言 store
 * 默认语言：英文（en-US）
 */
export const useLocaleStore = defineStore(LOCALE_KEY, {
    state: () => ({
        // 默认英文
        locale: 'en-US' as Locale,
    }),
    actions: {
        // 切换语言并同步 i18n
        setLocale(locale: Locale) {
            this.locale = locale;
            i18n.global.locale.value = locale;
        },

        // 中英文切换
        toggleLocale() {
            this.setLocale(this.locale === 'zh-CN' ? 'en-US' : 'zh-CN');
        },

        // 启动时同步 i18n
        initLocale() {
            i18n.global.locale.value = this.locale;
        },
    },
    persist: {
        pick: ["locale"]
    }
});
