import React, { FormEvent } from 'react'
import { useRecoilState, useRecoilValue } from 'recoil'
import { useTranslation } from 'react-i18next'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import { useToggle } from 'react-use'
import {
  ControlNetMethod,
  isControlNetState,
  isInpaintingState,
  negativePropmtState,
  propmtState,
  SDSampler,
  settingState,
} from '../../store/Atoms'
import NumberInputSetting from '../Settings/NumberInputSetting'
import SettingBlock from '../Settings/SettingBlock'
import Selector from '../shared/Selector'
import { Switch, SwitchThumb } from '../shared/Switch'
import TextAreaInput from '../shared/Textarea'
import emitter, { EVENT_PROMPT } from '../../event'
import ImageResizeScale from './ImageResizeScale'

const INPUT_WIDTH = 30

const SidePanel = () => {
  const [open, toggleOpen] = useToggle(true)
  const [setting, setSettingState] = useRecoilState(settingState)
  const { t } = useTranslation('editor')
  const [negativePrompt, setNegativePrompt] =
    useRecoilState(negativePropmtState)
  const isInpainting = useRecoilValue(isInpaintingState)
  const prompt = useRecoilValue(propmtState)
  const isControlNet = useRecoilValue(isControlNetState)

  const handleOnInput = (evt: FormEvent<HTMLTextAreaElement>) => {
    evt.preventDefault()
    evt.stopPropagation()
    const target = evt.target as HTMLTextAreaElement
    setNegativePrompt(target.value)
  }

  const onKeyUp = (e: React.KeyboardEvent) => {
    if (
      e.key === 'Enter' &&
      (e.ctrlKey || e.metaKey) &&
      prompt.length !== 0 &&
      !isInpainting
    ) {
      emitter.emit(EVENT_PROMPT)
    }
  }

  const renderConterNetSetting = () => {
    return (
      <>
        <SettingBlock
          className="sub-setting-block"
          title={t('sidebar.controlNet') as string}
          input={
            <Selector
              width={80}
              value={setting.controlnetMethod as string}
              options={Object.values(ControlNetMethod)}
              onChange={val => {
                const method = val as ControlNetMethod
                setSettingState(old => {
                  return { ...old, controlnetMethod: method }
                })
              }}
            />
          }
        />

        <NumberInputSetting
          title={t('sidebar.controlNetWeight') as string}
          width={INPUT_WIDTH}
          allowFloat
          value={`${setting.controlnetConditioningScale}`}
          desc={t('sidebar.controlNetWeightDesc') as string}
          onValue={value => {
            const val = value.length === 0 ? 0 : parseFloat(value)
            setSettingState(old => {
              return { ...old, controlnetConditioningScale: val }
            })
          }}
        />
      </>
    )
  }

  return (
    <div className="side-panel">
      <PopoverPrimitive.Root open={open}>
        <PopoverPrimitive.Trigger
          className="btn-primary side-panel-trigger"
          onClick={() => toggleOpen()}
        >
          {t('sidebar.config')}
        </PopoverPrimitive.Trigger>
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content className="side-panel-content">
            {isControlNet && renderConterNetSetting()}

            <SettingBlock
              title={t('sidebar.croper') as string}
              input={
                <Switch
                  checked={setting.showCroper}
                  onCheckedChange={value => {
                    setSettingState(old => {
                      return { ...old, showCroper: value }
                    })
                  }}
                >
                  <SwitchThumb />
                </Switch>
              }
            />

            <ImageResizeScale />

            {/* 
            <NumberInputSetting
              title="Num Samples"
              width={INPUT_WIDTH}
              value={`${setting.sdNumSamples}`}
              desc=""
              onValue={value => {
                const val = value.length === 0 ? 0 : parseInt(value, 10)
                setSettingState(old => {
                  return { ...old, sdNumSamples: val }
                })
              }}
            /> */}

            <NumberInputSetting
              title={t('sidebar.steps') as string}
              width={INPUT_WIDTH}
              value={`${setting.sdSteps}`}
              desc={t('sidebar.stepsDesc') as string}
              onValue={value => {
                const val = value.length === 0 ? 0 : parseInt(value, 10)
                setSettingState(old => {
                  return { ...old, sdSteps: val }
                })
              }}
            />

            <NumberInputSetting
              title={t('sidebar.guidanceScale') as string}
              width={INPUT_WIDTH}
              allowFloat
              value={`${setting.sdGuidanceScale}`}
              desc={t('sidebar.guidanceScaleDesc') as string}
              onValue={value => {
                const val = value.length === 0 ? 0 : parseFloat(value)
                setSettingState(old => {
                  return { ...old, sdGuidanceScale: val }
                })
              }}
            />

            <NumberInputSetting
              title={t('sidebar.maskBlur') as string}
              width={INPUT_WIDTH}
              value={`${setting.sdMaskBlur}`}
              desc={t('sidebar.maskBlurDesc') as string}
              onValue={value => {
                const val = value.length === 0 ? 0 : parseInt(value, 10)
                setSettingState(old => {
                  return { ...old, sdMaskBlur: val }
                })
              }}
            />

            <SettingBlock
              title={t('sidebar.matchHistograms') as string}
              desc={t('sidebar.matchHistogramsDesc') as string}
              input={
                <Switch
                  checked={setting.sdMatchHistograms}
                  onCheckedChange={value => {
                    setSettingState(old => {
                      return { ...old, sdMatchHistograms: value }
                    })
                  }}
                >
                  <SwitchThumb />
                </Switch>
              }
            />

            <SettingBlock
              className="sub-setting-block"
              title={t('sidebar.sampler') as string}
              input={
                <Selector
                  width={80}
                  value={setting.sdSampler as string}
                  options={Object.values(SDSampler)}
                  onChange={val => {
                    const sampler = val as SDSampler
                    setSettingState(old => {
                      return { ...old, sdSampler: sampler }
                    })
                  }}
                />
              }
            />

            <SettingBlock
              title={t('sidebar.seed') as string}
              input={
                <div
                  style={{
                    display: 'flex',
                    gap: 0,
                    justifyContent: 'center',
                    alignItems: 'center',
                  }}
                >
                  {/* 每次会从服务器返回更新该值 */}
                  <NumberInputSetting
                    title=""
                    width={80}
                    value={`${setting.sdSeed}`}
                    desc=""
                    disable={!setting.sdSeedFixed}
                    onValue={value => {
                      const val = value.length === 0 ? 0 : parseInt(value, 10)
                      setSettingState(old => {
                        return { ...old, sdSeed: val }
                      })
                    }}
                  />
                  <Switch
                    checked={setting.sdSeedFixed}
                    onCheckedChange={value => {
                      setSettingState(old => {
                        return { ...old, sdSeedFixed: value }
                      })
                    }}
                    style={{ marginLeft: '8px' }}
                  >
                    <SwitchThumb />
                  </Switch>
                </div>
              }
            />

            <SettingBlock
              className="sub-setting-block"
              title={t('sidebar.negativePrompt') as string}
              layout="v"
              input={
                <TextAreaInput
                  className="negative-prompt"
                  value={negativePrompt}
                  onInput={handleOnInput}
                  onKeyUp={onKeyUp}
                  placeholder=""
                />
              }
            />
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    </div>
  )
}

export default SidePanel
