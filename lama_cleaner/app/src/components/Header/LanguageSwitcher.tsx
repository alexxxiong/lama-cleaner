import React, { useState, useRef, useEffect } from 'react'
import { useLanguage } from '../../hooks/useLanguage'
import './LanguageSwitcher.scss'

const LanguageSwitcher: React.FC = () => {
  const { language, changeLanguage, supportedLanguages } = useLanguage()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const currentLang = supportedLanguages.find(lang => lang.code === language)

  return (
    <div className="language-switcher-ui" ref={dropdownRef}>
      <div
        className="theme-btn"
        onClick={() => setIsOpen(!isOpen)}
        role="button"
        tabIndex={0}
        aria-hidden="true"
        title="Language"
      >
        <span style={{ fontSize: '14px', fontWeight: 500 }}>
          {currentLang?.code === 'zh-CN' ? '中' : 'EN'}
        </span>
      </div>
      {isOpen && (
        <div className="language-dropdown">
          {supportedLanguages.map(lang => (
            <div
              key={lang.code}
              className={`language-option ${
                lang.code === language ? 'active' : ''
              }`}
              onClick={() => {
                changeLanguage(lang.code)
                setIsOpen(false)
              }}
              role="button"
              tabIndex={0}
              aria-hidden="true"
            >
              {lang.name}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default LanguageSwitcher
