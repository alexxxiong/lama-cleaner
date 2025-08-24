import React from 'react'
import { useSetRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { fileState } from '../../store/Atoms'
import FileSelect from '../FileSelect/FileSelect'

const LandingPage = () => {
  const setFile = useSetRecoilState(fileState)
  const { t } = useTranslation('common')

  return (
    <div className="landing-page">
      <h1>
        {t('landingPage.title')} 🦙
        <a href="https://github.com/saic-mdal/lama">LaMa</a>
      </h1>
      <div className="landing-file-selector">
        <FileSelect
          onSelection={async f => {
            setFile(f)
          }}
        />
      </div>
    </div>
  )
}

export default LandingPage
