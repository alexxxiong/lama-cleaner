/* eslint-disable global-require */
/* eslint-disable no-console */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Import translation resources directly
const resources = {
  en: {
    common: require('./resources/en/common.json'),
    editor: require('./resources/en/editor.json'),
    settings: require('./resources/en/settings.json'),
    errors: require('./resources/en/errors.json'),
    shortcuts: require('./resources/en/shortcuts.json'),
  },
  'zh-CN': {
    common: require('./resources/zh-CN/common.json'),
    editor: require('./resources/zh-CN/editor.json'),
    settings: require('./resources/zh-CN/settings.json'),
    errors: require('./resources/zh-CN/errors.json'),
    shortcuts: require('./resources/zh-CN/shortcuts.json'),
  },
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: ['common', 'editor', 'settings', 'errors', 'shortcuts'],

    debug: process.env.NODE_ENV === 'development',

    interpolation: {
      escapeValue: false, // React already escapes values
    },

    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
      lookupLocalStorage: 'preferred-language',
    },

    react: {
      useSuspense: false, // Disable suspense to avoid loading states
    },

    saveMissing: process.env.NODE_ENV === 'development',
    missingKeyHandler: (lng: readonly string[], ns: string, key: string) => {
      if (process.env.NODE_ENV === 'development') {
        console.warn(`Missing translation: ${lng.join(', ')}/${ns}/${key}`)
      }
    },
  })

export default i18n
