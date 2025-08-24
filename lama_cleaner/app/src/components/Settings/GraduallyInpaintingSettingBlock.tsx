import React from 'react'
import { useRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { settingState } from '../../store/Atoms'
import { Switch, SwitchThumb } from '../shared/Switch'
import SettingBlock from './SettingBlock'

const GraduallyInpaintingSettingBlock: React.FC = () => {
  const [setting, setSettingState] = useRecoilState(settingState)
  const { t } = useTranslation('settings')

  const onCheckChange = (checked: boolean) => {
    setSettingState(old => {
      return { ...old, graduallyInpainting: checked }
    })
  }

  return (
    <SettingBlock
      title={t('advanced.graduallyInpainting') as string}
      desc={t('advanced.graduallyInpaintingDesc') as string}
      input={
        <Switch
          checked={setting.graduallyInpainting}
          onCheckedChange={onCheckChange}
        >
          <SwitchThumb />
        </Switch>
      }
    />
  )
}

export default GraduallyInpaintingSettingBlock
