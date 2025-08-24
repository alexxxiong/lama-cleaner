import React, { ReactNode } from 'react'
import { useRecoilState } from 'recoil'
import { useTranslation } from 'react-i18next'
import { shortcutsState } from '../../store/Atoms'
import Modal from '../shared/Modal'

interface Shortcut {
  content: string
  keys: string[]
}

function ShortCut(props: Shortcut) {
  const { content, keys } = props

  return (
    <div className="shortcut-option">
      <div className="shortcut-description">{content}</div>
      <div style={{ display: 'flex', justifySelf: 'end', gap: '8px' }}>
        {keys.map((k, index) => (
          <div className="shortcut-key" key={k}>
            {k}
          </div>
        ))}
      </div>
    </div>
  )
}

const isMac = (function () {
  return /macintosh|mac os x/i.test(navigator.userAgent)
})()

const isWindows = (function () {
  return /windows|win32/i.test(navigator.userAgent)
})()

const CmdOrCtrl = isMac ? 'Cmd' : 'Ctrl'

export default function ShortcutsModal() {
  const [shortcutsShow, setShortcutState] = useRecoilState(shortcutsState)
  const { t } = useTranslation('shortcuts')

  const shortcutStateHandler = () => {
    setShortcutState(false)
  }

  return (
    <Modal
      onClose={shortcutStateHandler}
      title={t('hotkeys') as string}
      className="modal-shortcuts"
      show={shortcutsShow}
    >
      <div className="shortcut-options">
        <div className="shortcut-options-column">
          <ShortCut content={t('shortcuts.pan')} keys={['Space + Drag']} />
          <ShortCut content={t('shortcuts.resetZoomPan')} keys={['Esc']} />
          <ShortCut content={t('shortcuts.decreaseBrushSize')} keys={['[']} />
          <ShortCut content={t('shortcuts.increaseBrushSize')} keys={[']']} />
          <ShortCut
            content={t('shortcuts.viewOriginalImage')}
            keys={['Hold Tab']}
          />
          <ShortCut
            content={t('shortcuts.multiStrokeDrawing')}
            keys={[`Hold ${CmdOrCtrl}`]}
          />
          <ShortCut content={t('shortcuts.cancelDrawing')} keys={['Esc']} />
        </div>

        <div className="shortcut-options-column">
          <ShortCut content={t('shortcuts.rerunLastMask')} keys={['R']} />
          <ShortCut content={t('shortcuts.undo')} keys={[CmdOrCtrl, 'Z']} />
          <ShortCut
            content={t('shortcuts.redo')}
            keys={[CmdOrCtrl, 'Shift', 'Z']}
          />
          <ShortCut
            content={t('shortcuts.copyResult')}
            keys={[CmdOrCtrl, 'C']}
          />
          <ShortCut
            content={t('shortcuts.pasteImage')}
            keys={[CmdOrCtrl, 'V']}
          />
          <ShortCut
            content={t('shortcuts.triggerManualInpainting')}
            keys={['Shift', 'R']}
          />
          <ShortCut
            content={t('shortcuts.triggerInteractiveSeg')}
            keys={['I']}
          />
        </div>

        <div className="shortcut-options-column">
          <ShortCut
            content={t('shortcuts.switchTheme')}
            keys={['Shift', 'D']}
          />
          <ShortCut content={t('shortcuts.toggleHotkeysDialog')} keys={['H']} />
          <ShortCut
            content={t('shortcuts.toggleSettingsDialog')}
            keys={['S']}
          />
          <ShortCut content={t('shortcuts.toggleFileManager')} keys={['F']} />
        </div>
      </div>
    </Modal>
  )
}
