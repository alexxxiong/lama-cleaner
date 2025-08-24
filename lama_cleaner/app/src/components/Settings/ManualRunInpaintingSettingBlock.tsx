import React from 'react'
import { useRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { settingState } from '../../store/Atoms'
import { Switch, SwitchThumb } from '../shared/Switch'
import SettingBlock from './SettingBlock'

const ManualRunInpaintingSettingBlock: React.FC = () => {
  const [setting, setSettingState] = useRecoilState(settingState)
  const { t } = useTranslation('settings')

  const onCheckChange = (checked: boolean) => {
    setSettingState(old => {
      return { ...old, runInpaintingManually: checked }
    })
  }

  return (
    <SettingBlock
      title={t('advanced.manualInpaintingMode') as string}
      input={
        <Switch
          checked={setting.runInpaintingManually}
          onCheckedChange={onCheckChange}
        >
          <SwitchThumb />
        </Switch>
      }
    />
  )
}

export default ManualRunInpaintingSettingBlock
