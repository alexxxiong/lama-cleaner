import React, { ReactNode } from 'react'
import { useRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { hdSettingsState, settingState } from '../../store/Atoms'
import Selector from '../shared/Selector'
import NumberInputSetting from './NumberInputSetting'
import SettingBlock from './SettingBlock'

export enum HDStrategy {
  ORIGINAL = 'Original',
  RESIZE = 'Resize',
  CROP = 'Crop',
}

export enum LDMSampler {
  ddim = 'ddim',
  plms = 'plms',
}

function HDSettingBlock() {
  const [hdSettings, setHDSettings] = useRecoilState(hdSettingsState)
  const { t } = useTranslation('settings')
  if (!hdSettings?.enabled) {
    return <></>
  }

  const getStrategyDisplayValue = () => {
    switch (hdSettings.hdStrategy) {
      case HDStrategy.ORIGINAL:
        return t('hd.strategies.original')
      case HDStrategy.RESIZE:
        return t('hd.strategies.resize')
      case HDStrategy.CROP:
        return t('hd.strategies.crop')
      default:
        return t('hd.strategies.original')
    }
  }

  const onStrategyChange = (value: HDStrategy) => {
    setHDSettings({ hdStrategy: value })
  }

  const onResizeLimitChange = (value: string) => {
    const val = value.length === 0 ? 0 : parseInt(value, 10)
    setHDSettings({ hdStrategyResizeLimit: val })
  }

  const onCropTriggerSizeChange = (value: string) => {
    const val = value.length === 0 ? 0 : parseInt(value, 10)
    setHDSettings({ hdStrategyCropTrigerSize: val })
  }

  const onCropMarginChange = (value: string) => {
    const val = value.length === 0 ? 0 : parseInt(value, 10)
    setHDSettings({ hdStrategyCropMargin: val })
  }

  const renderOriginalOptionDesc = () => {
    return (
      <div>
        {t('hd.originalDesc')}{' '}
        <div
          tabIndex={0}
          role="button"
          className="inline-tip"
          onClick={() => onStrategyChange(HDStrategy.RESIZE)}
        >
          {t('hd.strategies.resize')}
        </div>{' '}
        {t('hd.originalDescOr')}{' '}
        <div
          tabIndex={0}
          role="button"
          className="inline-tip"
          onClick={() => onStrategyChange(HDStrategy.CROP)}
        >
          {t('hd.strategies.crop')}
        </div>{' '}
        {t('hd.originalDescEnd')}
      </div>
    )
  }

  const renderResizeOptionDesc = () => {
    return (
      <>
        <div>{t('hd.resizeDesc')}</div>
        <NumberInputSetting
          title={t('hd.sizeLimit') as string}
          value={`${hdSettings.hdStrategyResizeLimit}`}
          suffix={t('hd.pixel') as string}
          onValue={onResizeLimitChange}
        />
      </>
    )
  }

  const renderCropOptionDesc = () => {
    return (
      <>
        <div>{t('hd.cropDesc')}</div>
        <NumberInputSetting
          title={t('hd.triggerSize') as string}
          value={`${hdSettings.hdStrategyCropTrigerSize}`}
          suffix={t('hd.pixel') as string}
          onValue={onCropTriggerSizeChange}
        />
        <NumberInputSetting
          title={t('hd.cropMargin') as string}
          value={`${hdSettings.hdStrategyCropMargin}`}
          suffix={t('hd.pixel') as string}
          onValue={onCropMarginChange}
        />
      </>
    )
  }

  const renderHDStrategyOptionDesc = (): ReactNode => {
    switch (hdSettings.hdStrategy) {
      case HDStrategy.ORIGINAL:
        return renderOriginalOptionDesc()
      case HDStrategy.CROP:
        return renderCropOptionDesc()
      case HDStrategy.RESIZE:
        return renderResizeOptionDesc()
      default:
        return renderOriginalOptionDesc()
    }
  }

  return (
    <SettingBlock
      className="hd-setting-block"
      title={t('hd.strategy') as string}
      input={
        <Selector
          width={80}
          value={getStrategyDisplayValue()}
          options={[
            t('hd.strategies.original'),
            t('hd.strategies.resize'),
            t('hd.strategies.crop'),
          ]}
          onChange={val => {
            if (val === t('hd.strategies.original')) {
              onStrategyChange(HDStrategy.ORIGINAL)
            } else if (val === t('hd.strategies.resize')) {
              onStrategyChange(HDStrategy.RESIZE)
            } else if (val === t('hd.strategies.crop')) {
              onStrategyChange(HDStrategy.CROP)
            }
          }}
        />
      }
      optionDesc={renderHDStrategyOptionDesc()}
    />
  )
}

export default HDSettingBlock
