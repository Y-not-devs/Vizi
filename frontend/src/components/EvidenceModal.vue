<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm"
    @click.self="close"
  >
    <div class="relative max-w-4xl w-full bg-dark-900 border border-dark-700 rounded-2xl overflow-hidden flex flex-col max-h-[90vh] shadow-2xl">
      <div class="px-5 py-3.5 border-b border-dark-800 flex items-center justify-between">
        <div class="flex items-center gap-2.5 text-sm">
          <span class="font-bold text-white">Кадр-доказательство</span>
          <span v-if="timestamp !== undefined" class="font-mono text-emerald-400 font-semibold px-2.5 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/25 text-xs">
            {{ formatTimecode(timestamp) }} ({{ timestamp.toFixed(1) }} сек)
          </span>
        </div>
        <div class="flex items-center gap-2">
          <a
            :href="imageSrc"
            :download="`evidence_${timestamp || 0}s.jpg`"
            class="btn-icon p-2 text-slate-300 hover:text-emerald-400"
            title="Скачать кадр"
          >
            <Download class="w-4.5 h-4.5" />
          </a>
          <button @click="close" class="btn-icon p-2 text-slate-300 hover:text-white" title="Закрыть">
            <X class="w-4.5 h-4.5" />
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-auto p-4 flex items-center justify-center bg-black min-h-[300px]">
        <img
          :src="imageSrc"
          alt="Кадр-доказательство"
          class="max-w-full max-h-[70vh] rounded-lg object-contain"
        />
      </div>

      <div v-if="violationType" class="px-5 py-3 border-t border-dark-800 text-sm text-slate-300 font-medium">
        {{ violationType }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, X } from 'lucide-vue-next'
import { formatTimecode } from '@/lib/format'

defineProps<{
  isOpen: boolean
  imageSrc: string
  timestamp?: number
  violationType?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

function close() {
  emit('close')
}
</script>
