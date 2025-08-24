import React from 'react'
import { useRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { settingState } from '../../store/Atoms'
import { Switch, SwitchThumb } from '../shared/Switch'
import SettingBlock from './SettingBlock'

const DownloadMaskSettingBlock: React.FC = () => {
  const [setting, setSettingState] = useRecoilState(settingState)
  const { t } = useTranslation('settings')

  const onCheckChange = (checked: boolean) => {
    setSettingState(old => {
      return { ...old, downloadMask: checked }
    })
  }

  return (
    <SettingBlock
      title={t('advanced.downloadMask') as string}
      desc={t('advanced.downloadMaskDesc') as string}
      input={
        <Switch checked={setting.downloadMask} onCheckedChange={onCheckChange}>
          <SwitchThumb />
        </Switch>
      }
    />
  )
}

export default DownloadMaskSettingBlock
