import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '../shared/Button'
import Modal from '../shared/Modal'

interface Props {
  show: boolean
  onClose: () => void
  onCleanClick: () => void
  onReplaceClick: () => void
}

const InteractiveSegReplaceModal = (props: Props) => {
  const { show, onClose, onCleanClick, onReplaceClick } = props
  const { t } = useTranslation('editor')

  return (
    <Modal
      onClose={onClose}
      title={t('interactiveSeg.maskExists') as string}
      className="modal-setting"
      show={show}
      showCloseIcon
    >
      <h4 style={{ lineHeight: '24px' }}>
        {t('interactiveSeg.maskExistsDesc')}
      </h4>
      <div
        style={{
          display: 'flex',
          width: '100%',
          justifyContent: 'flex-end',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        <Button
          onClick={() => {
            onClose()
            onCleanClick()
          }}
        >
          {t('interactiveSeg.remove')}
        </Button>
        <Button onClick={onReplaceClick} border>
          {t('interactiveSeg.createNew')}
        </Button>
      </div>
    </Modal>
  )
}

export default InteractiveSegReplaceModal
