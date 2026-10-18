<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-sm"
    @click.self="close"
  >
    <div class="panel max-w-md w-full rounded-2xl p-6 sm:p-7 space-y-6 shadow-2xl">
      <!-- Шапка модалки -->
      <div class="flex items-center justify-between pb-4 border-b border-slate-800">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400">
            <Sliders class="w-4 h-4" />
          </div>
          <h3 class="font-bold text-lg text-white">
            Настройки API
          </h3>
        </div>
        <button
          @click="close"
          class="btn-icon p-2 text-slate-400 hover:text-white"
          title="Закрыть"
        >
          <X class="w-4.5 h-4.5" />
        </button>
      </div>

      <!-- Поля формы -->
      <div class="space-y-4 text-sm">
        <div>
          <label class="block text-slate-200 font-semibold mb-1.5">
            Базовый адрес API (Backend)
          </label>
          <input
            v-model="apiUrl"
            type="text"
            placeholder="/api или http://localhost:8000/api"
            class="w-full px-3.5 py-2.5 rounded-xl bg-dark-950 border border-slate-800 text-slate-100 placeholder-slate-600 text-sm font-mono focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/20 focus:outline-none transition"
          />
        </div>

        <div>
          <label class="block text-slate-200 font-semibold mb-1.5">
            API-ключ (X-API-Key)
          </label>
          <input
            v-model="apiKey"
            type="password"
            placeholder="ANALYSIS_API_KEY из .env"
            class="w-full px-3.5 py-2.5 rounded-xl bg-dark-950 border border-slate-800 text-slate-100 placeholder-slate-600 text-sm font-mono focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/20 focus:outline-none transition"
          />
        </div>

        <!-- Информационная плашка портов -->
        <div class="p-3.5 rounded-xl bg-dark-950/80 border border-slate-800 text-xs sm:text-sm font-mono space-y-1.5 text-slate-300">
          <div class="flex items-center justify-between">
            <span class="text-slate-400">Адрес API:</span>
            <span class="text-emerald-400 font-bold">{{ apiUrl || '/api' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-slate-400">Авторизация:</span>
            <span class="text-emerald-400 font-bold">X-API-Key</span>
          </div>
        </div>
      </div>

      <!-- Кнопки действий -->
      <div class="pt-4 border-t border-slate-800 flex justify-between items-center">
        <button
          @click="resetDefaults"
          class="btn-secondary px-4 py-2 text-sm"
        >
          Сбросить
        </button>
        <button
          @click="save"
          class="btn-primary px-6 py-2.5 text-sm font-bold"
        >
          Сохранить
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Sliders, X } from 'lucide-vue-next'
import { apiConfig } from '@/lib/api'

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const apiUrl = ref(apiConfig.getBaseUrl())
const apiKey = ref(apiConfig.getApiKey())

watch(() => props.isOpen, (open) => {
  if (open) {
    apiUrl.value = apiConfig.getBaseUrl()
    apiKey.value = apiConfig.getApiKey()
  }
})

function resetDefaults() {
  apiUrl.value = '/api'
  apiKey.value = ''
}

function save() {
  apiConfig.setBaseUrl(apiUrl.value === '/api' ? null : apiUrl.value)
  apiConfig.setApiKey(apiKey.value.trim() || null)
  emit('saved')
  emit('close')
}

function close() {
  emit('close')
}
</script>
