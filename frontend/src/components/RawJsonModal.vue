<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm"
    @click.self="close"
  >
    <div class="relative max-w-2xl w-full bg-dark-900 border border-dark-700 rounded-2xl overflow-hidden flex flex-col max-h-[85vh] shadow-2xl">
      <div class="px-5 py-3.5 border-b border-dark-800 flex items-center justify-between text-sm">
        <span class="font-semibold text-white text-sm sm:text-base">Ответ API (JSON)</span>
        <div class="flex items-center gap-2.5">
          <button
            @click="copyJson"
            class="btn-secondary px-3.5 py-1.5 text-xs font-mono"
          >
            {{ copied ? '✓ Скопировано' : 'Копировать' }}
          </button>
          <button @click="close" class="btn-icon p-1.5 text-slate-400 hover:text-white" title="Закрыть">
            <X class="w-4.5 h-4.5" />
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-auto p-5 bg-dark-950">
        <pre class="font-mono text-xs sm:text-sm text-emerald-300 leading-relaxed whitespace-pre-wrap select-all">{{ formattedJson }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  isOpen: boolean
  jobId: string
  payload: any
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const copied = ref(false)

const formattedJson = computed(() => {
  if (!props.payload) return '{}'
  try {
    return JSON.stringify(props.payload, null, 2)
  } catch {
    return String(props.payload)
  }
})

function copyJson() {
  navigator.clipboard.writeText(formattedJson.value)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}

function close() {
  emit('close')
}
</script>
