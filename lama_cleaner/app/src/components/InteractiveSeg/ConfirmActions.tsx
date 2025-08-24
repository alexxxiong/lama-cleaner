import React, { useEffect, useState } from 'react'
import { useRecoilState, useRecoilValue } from 'recoil'
import { useTranslation } from 'react-i18next'
import {
  interactiveSegClicksState,
  isInteractiveSegRunningState,
  isInteractiveSegState,
} from '../../store/Atoms'
import Button from '../shared/Button'

interface Props {
  onCancelClick: () => void
  onAcceptClick: () => void
}

const InteractiveSegConfirmActions = (props: Props) => {
  const { onCancelClick, onAcceptClick } = props
  const { t } = useTranslation('editor')

  const [isInteractiveSeg, setIsInteractiveSeg] = useRecoilState(
    isInteractiveSegState
  )
  const [isInteractiveSegRunning, setIsInteractiveSegRunning] = useRecoilState(
    isInteractiveSegRunningState
  )
  const [clicks, setClicks] = useRecoilState(interactiveSegClicksState)

  const clearState = () => {
    setIsInteractiveSeg(false)
    setIsInteractiveSegRunning(false)
    setClicks([])
  }

  return (
    <div
      className="interactive-seg-confirm-actions"
      style={{
        visibility: isInteractiveSeg ? 'visible' : 'hidden',
      }}
    >
      <div className="action-buttons">
        <Button
          onClick={() => {
            clearState()
            onCancelClick()
          }}
        >
          {t('interactiveSeg.cancel')}
        </Button>
        <Button
          border
          onClick={() => {
            clearState()
            onAcceptClick()
          }}
        >
          {t('interactiveSeg.accept')}
        </Button>
      </div>
    </div>
  )
}

export default InteractiveSegConfirmActions
