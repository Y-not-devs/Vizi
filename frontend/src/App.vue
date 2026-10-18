<template>
  <div class="min-h-screen flex flex-col bg-dark-950 text-slate-100 selection:bg-neon selection:text-dark-950 relative">
    <!-- Тонкий фоновый градиент для глубины -->
    <div class="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-15%,rgba(0,220,130,0.06),transparent_75%)]"></div>

    <!-- Шапка -->
    <Navbar
      @go-home="goToUpload"
      @open-settings="isSettingsOpen = true"
    />

    <!-- Контент -->
    <main class="flex-1 relative z-10">
      <transition name="fade" mode="out-in">
        <UploadView
          v-if="currentView === 'upload'"
          @analysis-complete="onAnalysisComplete"
        />

        <ResultsView
          v-else-if="currentView === 'results' && analysisResult"
          :result="analysisResult"
          :video-file="uploadedVideoFile"
          :video-url="uploadedVideoUrl"
          @back-to-upload="goToUpload"
        />
      </transition>
    </main>

    <!-- Минималистичный подвал -->
    <footer class="border-t border-dark-800/80 py-5 text-center text-sm text-slate-400 font-mono relative z-10">
      <span>Vizi • AI-контроль кассовой дисциплины</span>
    </footer>

    <!-- Настройки API -->
    <SettingsModal
      :is-open="isSettingsOpen"
      @close="isSettingsOpen = false"
      @saved="runHealthCheck"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Navbar from './components/Navbar.vue'
import ResultsView from './components/ResultsView.vue'
import SettingsModal from './components/SettingsModal.vue'
import UploadView from './components/UploadView.vue'
import { checkBackendHealth } from './lib/api'
import type { AnalysisResponse } from './types'

type ViewMode = 'upload' | 'results'

const currentView = ref<ViewMode>('upload')
const analysisResult = ref<AnalysisResponse | null>(null)
const uploadedVideoFile = ref<File | null>(null)
const uploadedVideoUrl = ref<string>('')

const isSettingsOpen = ref(false)
const backendStatus = ref<{ online: boolean; message: string }>({
  online: false,
  message: '',
})

async function runHealthCheck() {
  const status = await checkBackendHealth()
  backendStatus.value = status
}

function onAnalysisComplete(payload: {
  result: AnalysisResponse
  videoFile: File
  previewUrl: string
}) {
  analysisResult.value = payload.result
  uploadedVideoFile.value = payload.videoFile
  uploadedVideoUrl.value = payload.previewUrl
  currentView.value = 'results'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function goToUpload() {
  currentView.value = 'upload'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  runHealthCheck()
  setInterval(runHealthCheck, 15000)
})
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
