<template>
  <header class="border-b border-slate-800/80 bg-dark-950/90 backdrop-blur-md sticky top-0 z-40">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
      <!-- Название бренда Vizi -->
      <button
        @click="$emit('go-home')"
        class="text-2xl font-black tracking-tight text-white hover:text-emerald-300 transition flex items-center gap-2.5 focus:outline-none group"
      >
        <span class="bg-gradient-to-r from-white via-slate-100 to-slate-300 bg-clip-text text-transparent group-hover:from-white group-hover:to-emerald-300 transition">
          Vizi
        </span>
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_#00dc82] group-hover:scale-125 transition-transform"></span>
      </button>

      <!-- Правая часть: кнопка настроек -->
      <div class="flex items-center gap-3">
        <button
          @click="$emit('open-settings')"
          class="btn-icon p-2.5 rounded-xl text-slate-300 hover:text-emerald-300 hover:border-emerald-500/50 transition"
          title="Настройки подключения к API"
        >
          <Sliders class="w-5 h-5" />
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Sliders } from 'lucide-vue-next'

defineEmits<{
  (e: 'go-home'): void
  (e: 'open-settings'): void
}>()
</script>
