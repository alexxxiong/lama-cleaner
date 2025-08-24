import { useCallback } from 'react'
import { useRecoilState, useSetRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { languageState, toastState } from '../store/Atoms'

export const supportedLanguages = [
  { code: 'en', name: 'English' },
  { code: 'zh-CN', name: '简体中文' },
]

export function useLanguage() {
  const [language, setLanguage] = useRecoilState(languageState)
  const setToastState = useSetRecoilState(toastState)
  const { i18n } = useTranslation()

  const changeLanguage = useCallback(
    async (lng: string) => {
      try {
        await i18n.changeLanguage(lng)
        setLanguage(lng)
        localStorage.setItem('preferred-language', lng)
      } catch (error) {
        // eslint-disable-next-line no-console
        console.error('Language change failed:', error)
        setToastState({
          open: true,
          desc: 'Failed to change language',
          state: 'error',
          duration: 3000,
        })
      }
    },
    [i18n, setLanguage, setToastState]
  )

  return {
    language,
    changeLanguage,
    supportedLanguages,
  }
}
