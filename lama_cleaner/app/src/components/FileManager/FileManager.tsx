import React, {
  SyntheticEvent,
  useEffect,
  useState,
  useCallback,
  useRef,
  FormEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import _ from 'lodash'
import * as Tabs from '@radix-ui/react-tabs'
import { useRecoilState, useSetRecoilState } from 'recoil'
import PhotoAlbum from 'react-photo-album'
import { BarsArrowDownIcon, BarsArrowUpIcon } from '@heroicons/react/24/outline'
import {
  MagnifyingGlassIcon,
  ViewHorizontalIcon,
  ViewGridIcon,
} from '@radix-ui/react-icons'
import { useDebounce } from 'react-use'
import { Id, Index, IndexSearchResult } from 'flexsearch'
import * as ScrollArea from '@radix-ui/react-scroll-area'
import Modal from '../shared/Modal'
import Flex from '../shared/Layout'
import {
  fileManagerLayout,
  fileManagerSearchText,
  fileManagerSortBy,
  fileManagerSortOrder,
  SortBy,
  SortOrder,
  toastState,
} from '../../store/Atoms'
import { getMedias } from '../../adapters/inpainting'
import Selector from '../shared/Selector'
import Button from '../shared/Button'
import TextInput from '../shared/Input'

interface Photo {
  src: string
  height: number
  width: number
  name: string
}

interface Filename {
  name: string
  height: number
  width: number
  ctime: number
  mtime: number
}

const IMAGE_TAB = 'image'
const OUTPUT_TAB = 'output'

const getSortByLabel = (sortBy: SortBy, t: any) => {
  switch (sortBy) {
    case SortBy.NAME:
      return t('fileManager.sortBy.name')
    case SortBy.CTIME:
      return t('fileManager.sortBy.createdTime')
    case SortBy.MTIME:
      return t('fileManager.sortBy.modifiedTime')
    default:
      return t('fileManager.sortBy.name')
  }
}

interface Props {
  show: boolean
  onClose: () => void
  onPhotoClick(tab: string, filename: string): void
  photoWidth: number
}

export default function FileManager(props: Props) {
  const { show, onClose, onPhotoClick, photoWidth } = props
  const { t } = useTranslation('common')
  const [scrollTop, setScrollTop] = useState(0)
  const [closeScrollTop, setCloseScrollTop] = useState(0)
  const setToastState = useSetRecoilState(toastState)

  const [sortBy, setSortBy] = useRecoilState<SortBy>(fileManagerSortBy)
  const [sortOrder, setSortOrder] = useRecoilState(fileManagerSortOrder)
  const [layout, setLayout] = useRecoilState(fileManagerLayout)
  const [debouncedSearchText, setDebouncedSearchText] = useRecoilState(
    fileManagerSearchText
  )
  const ref = useRef(null)
  const [searchText, setSearchText] = useState(debouncedSearchText)
  const [tab, setTab] = useState(IMAGE_TAB)
  const [photos, setPhotos] = useState<Photo[]>([])

  const [, cancel] = useDebounce(
    () => {
      setDebouncedSearchText(searchText)
    },
    500,
    [searchText]
  )

  useEffect(() => {
    if (!show) {
      setCloseScrollTop(scrollTop)
    }
  }, [show, scrollTop])

  const onRefChange = useCallback(
    (node: HTMLDivElement) => {
      if (node !== null) {
        if (show) {
          setTimeout(() => {
            // TODO: without timeout, scrollTo not work, why?
            node.scrollTo({ top: closeScrollTop, left: 0 })
          }, 100)
        }
      }
    },
    [show, closeScrollTop]
  )

  useEffect(() => {
    if (!show) {
      return
    }
    const fetchData = async () => {
      try {
        const filenames = await getMedias(tab)
        let filteredFilenames = filenames
        if (debouncedSearchText) {
          const index = new Index()
          filenames.forEach((filename: Filename, id: number) =>
            index.add(id, filename.name)
          )
          const results: IndexSearchResult = index.search(debouncedSearchText)
          filteredFilenames = results.map((id: Id) => filenames[id as number])
        }

        filteredFilenames = _.orderBy(filteredFilenames, sortBy, sortOrder)

        const newPhotos = filteredFilenames.map((filename: Filename) => {
          const width = photoWidth
          const height = filename.height * (width / filename.width)
          const src = `/media_thumbnail/${tab}/${filename.name}?width=${width}&height=${height}`
          return { src, height, width, name: filename.name }
        })
        setPhotos(newPhotos)
      } catch (e: any) {
        setToastState({
          open: true,
          desc: e.message ? e.message : e.toString(),
          state: 'error',
          duration: 2000,
        })
      }
    }
    fetchData()
  }, [
    setToastState,
    tab,
    debouncedSearchText,
    sortBy,
    sortOrder,
    photoWidth,
    show,
  ])

  const onScroll = (event: SyntheticEvent) => {
    setScrollTop(event.currentTarget.scrollTop)
  }

  const onClick = ({ index }: { index: number }) => {
    onPhotoClick(tab, photos[index].name)
  }

  const renderTitle = () => {
    return (
      <Flex
        style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 12 }}
      >
        <div>{`${t('fileManager.imagesCount')} (${photos.length})`}</div>
        <Flex>
          <Button
            icon={<ViewHorizontalIcon />}
            toolTip={t('fileManager.rowsLayout') as string}
            onClick={() => {
              setLayout('rows')
            }}
            className={layout !== 'rows' ? 'sort-btn-inactive' : ''}
          />
          <Button
            icon={<ViewGridIcon />}
            toolTip={t('fileManager.gridLayout') as string}
            onClick={() => {
              setLayout('masonry')
            }}
            className={layout !== 'masonry' ? 'sort-btn-inactive' : ''}
          />
        </Flex>
      </Flex>
    )
  }

  return (
    <Modal
      onClose={onClose}
      // TODO：layout switch 放到标题中
      title={renderTitle()}
      className="file-manager-modal"
      show={show}
    >
      <Flex style={{ justifyContent: 'space-between', gap: 8 }}>
        <Tabs.Root
          className="TabsRoot"
          defaultValue={tab}
          onValueChange={val => setTab(val)}
        >
          <Tabs.List className="TabsList" aria-label="Manage your account">
            <Tabs.Trigger className="TabsTrigger" value={IMAGE_TAB}>
              {t('fileManager.imageDirectory')}
            </Tabs.Trigger>
            <Tabs.Trigger className="TabsTrigger" value={OUTPUT_TAB}>
              {t('fileManager.outputDirectory')}
            </Tabs.Trigger>
          </Tabs.List>
        </Tabs.Root>
        <Flex style={{ gap: 8 }}>
          <Flex
            style={{
              position: 'relative',
              justifyContent: 'start',
            }}
          >
            <MagnifyingGlassIcon style={{ position: 'absolute', left: 8 }} />
            <TextInput
              ref={ref}
              value={searchText}
              className="file-search-input"
              tabIndex={-1}
              onInput={(evt: FormEvent<HTMLInputElement>) => {
                evt.preventDefault()
                evt.stopPropagation()
                const target = evt.target as HTMLInputElement
                setSearchText(target.value)
              }}
              placeholder={t('fileManager.searchPlaceholder') as string}
            />
          </Flex>
          <Flex style={{ gap: 8 }}>
            <Selector
              width={140}
              value={getSortByLabel(sortBy, t)}
              options={[
                t('fileManager.sortBy.name'),
                t('fileManager.sortBy.createdTime'),
                t('fileManager.sortBy.modifiedTime'),
              ]}
              onChange={val => {
                if (val === t('fileManager.sortBy.name')) {
                  setSortBy(SortBy.NAME)
                } else if (val === t('fileManager.sortBy.createdTime')) {
                  setSortBy(SortBy.CTIME)
                } else if (val === t('fileManager.sortBy.modifiedTime')) {
                  setSortBy(SortBy.MTIME)
                }
              }}
              chevronDirection="down"
            />
            <Button
              icon={<BarsArrowDownIcon />}
              toolTip={t('fileManager.descendingOrder') as string}
              onClick={() => {
                setSortOrder(SortOrder.DESCENDING)
              }}
              className={
                sortOrder !== SortOrder.DESCENDING ? 'sort-btn-inactive' : ''
              }
            />
            <Button
              icon={<BarsArrowUpIcon />}
              toolTip={t('fileManager.ascendingOrder') as string}
              onClick={() => {
                setSortOrder(SortOrder.ASCENDING)
              }}
              className={
                sortOrder !== SortOrder.ASCENDING ? 'sort-btn-inactive' : ''
              }
            />
          </Flex>
        </Flex>
      </Flex>
      <ScrollArea.Root className="ScrollAreaRoot">
        <ScrollArea.Viewport
          className="ScrollAreaViewport"
          onScroll={onScroll}
          ref={onRefChange}
        >
          <PhotoAlbum
            layout={layout}
            photos={photos}
            spacing={8}
            padding={0}
            onClick={onClick}
          />
        </ScrollArea.Viewport>
        <ScrollArea.Scrollbar
          className="ScrollAreaScrollbar"
          orientation="vertical"
        >
          <ScrollArea.Thumb className="ScrollAreaThumb" />
        </ScrollArea.Scrollbar>
        {/* <ScrollArea.Scrollbar
          className="ScrollAreaScrollbar"
          orientation="horizontal"
        >
          <ScrollArea.Thumb className="ScrollAreaThumb" />
        </ScrollArea.Scrollbar> */}
        <ScrollArea.Corner className="ScrollAreaCorner" />
      </ScrollArea.Root>
    </Modal>
  )
}
