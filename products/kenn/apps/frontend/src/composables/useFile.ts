/** 文件选择 Pinia Store：管理已选文件与全页拖拽状态 */
import { defineStore } from 'pinia'
import { FILE_KEY } from '../utils/keys'
import type { AddFilesOptions, UploadFileItem } from '../utils/file'
import { isAcceptedFile } from '../utils/file'

let fileId = 0
const createId = () => String(++fileId)

export const useFileStore = defineStore(FILE_KEY, {
  state: () => ({
    files: [] as UploadFileItem[],
    isDragOverlayActive: false,
    isDragHover: false,
    uploadError: '',
  }),
  actions: {
    addFiles(fileList: File[], options?: AddFilesOptions) {
      this.uploadError = ''
      const validFiles: UploadFileItem[] = []

      for (const file of fileList) {
        if (options?.accept && !isAcceptedFile(file, options.accept)) {
          if (options.typeError) this.uploadError = options.typeError
          continue
        }
        if (options?.maxSize && file.size > options.maxSize) {
          if (options.sizeError) this.uploadError = options.sizeError
          continue
        }
        validFiles.push({ id: createId(), file })
      }

      if (validFiles.length) {
        this.files.push(...validFiles)
      }
    },

    removeFile(id: string) {
      this.files = this.files.filter((item) => item.id !== id)
      if (!this.files.length) this.uploadError = ''
    },

    clearFiles() {
      this.files = []
      this.uploadError = ''
    },

    openDragOverlay() {
      this.isDragOverlayActive = true
    },

    closeDragOverlay() {
      this.isDragOverlayActive = false
      this.isDragHover = false
    },

    setDragHover(value: boolean) {
      this.isDragHover = value
    },
  },
})
