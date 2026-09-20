import { computed, ref } from 'vue'
import { useFileStore } from './useFile'
import { buildAcceptInput, type AddFilesOptions } from '../utils/file'

/** 无 UI 的文件选择：配合隐藏 input，由业务按钮触发 */
export function useFilePicker(defaultOptions?: AddFilesOptions) {
  const fileStore = useFileStore()
  const inputRef = ref<HTMLInputElement | null>(null)
  const options = ref<AddFilesOptions>(defaultOptions ?? {})

  const acceptInput = computed(() => buildAcceptInput(options.value.accept))

  const open = (override?: AddFilesOptions) => {
    if (override) options.value = { ...options.value, ...override }
    inputRef.value?.click()
  }

  const onChange = (event: Event) => {
    const input = event.target as HTMLInputElement
    if (input.files?.length) {
      fileStore.addFiles(Array.from(input.files), options.value)
    }
    input.value = ''
  }

  return { fileStore, inputRef, acceptInput, options, open, onChange }
}
