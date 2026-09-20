/// <reference types="vite/client" />
/// <reference types="pinia-plugin-persistedstate" />

declare const API_URL: string

interface ImportMetaEnv {
  readonly VITE_MIX_REVIEW_MOCK?: string
  readonly VITE_MIX_REVIEW_API_PREFIX?: string
  /** Jack Dashboard 密码；留空表示不自动登录 */
  readonly VITE_MIX_REVIEW_DASHBOARD_PASSWORD?: string
  readonly VITE_SLO_CLASSIFICATION_MOCK?: string
  readonly VITE_SLO_CLASSIFICATION_MOCK_SCENARIO?: 'ready' | 'empty' | 'offline' | 'error' | 'malformed'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
