<template>
  <div class="max-w-3xl mx-auto px-4 py-10 sm:py-14">
    <!-- Шапка страницы с зеленым акцентным бейджем -->
    <div class="text-center mb-8 space-y-3">
      <h1 class="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
        Анализ видеозаписи
      </h1>
      <p class="text-base text-slate-300 max-w-lg mx-auto">
        Загрузите видео с камеры кассового узла для автоматического выявления нарушений
      </p>
    </div>

    <!-- Основная карточка загрузки -->
    <div class="panel rounded-2xl p-6 sm:p-9 shadow-2xl">
      <!-- Состояние 1: Выбор видео -->
      <div v-if="!isAnalyzing" class="space-y-6">
        <!-- Зона Drag & Drop (когда файл еще НЕ выбран) -->
        <div
          v-if="!selectedFile"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
          @click="triggerFileInput"
          class="rounded-2xl border-2 border-dashed p-10 sm:p-14 text-center transition-all duration-200 cursor-pointer group"
          :class="isDragging
            ? 'border-emerald-400 bg-emerald-500/10 shadow-[0_0_30px_rgba(0,220,130,0.25)]'
            : 'border-slate-700/80 hover:border-emerald-200/80 bg-dark-950/70 hover:bg-dark-900/90 hover:shadow-[0_0_35px_-6px_rgba(0,220,130,0.2)]'"
        >
          <input
            ref="fileInputRef"
            type="file"
            accept="video/*,.mov,.mp4,.avi,.mkv,.webm"
            class="hidden"
            @change="handleFileChange"
          />

          <div class="space-y-4">
            <div class="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center mx-auto text-emerald-400 group-hover:bg-emerald-200/20 group-hover:border-emerald-200/50 transition-all duration-300 shadow-[0_0_20px_-4px_rgba(0,220,130,0.3)]">
              <UploadCloud class="w-8 h-8" />
            </div>

            <div class="space-y-1.5">
              <p class="text-lg font-bold text-white  transition-colors">
                Перетащите видеофайл сюда
              </p>
              <p class="text-sm text-slate-400">
                или нажмите, чтобы выбрать файл на компьютере
              </p>
            </div>

            <div class="pt-2">
              <span class="btn-secondary px-5 py-2.5 text-sm pointer-events-none group-hover:text-white">
                <Film class="w-4 h-4 text-emerald-400" />
                <span>Выбрать видео (до 200 МБ)</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Карточка выбранного файла (когда файл выбран) -->
        <div v-else class="space-y-5">
          <!-- Верхняя плашка файла -->
          <div class="flex items-center justify-between p-4 sm:p-5 rounded-xl bg-dark-950 border border-slate-800">
            <div class="flex items-center gap-3.5 min-w-0 pr-3">
              <div class="w-11 h-11 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0 shadow-[0_0_12px_rgba(0,220,130,0.2)]">
                <Film class="w-5 h-5" />
              </div>
              <div class="min-w-0">
                <p class="text-base font-bold text-white truncate" :title="selectedFile.name">
                  {{ selectedFile.name }}
                </p>
                <div class="flex items-center gap-2 text-xs text-slate-400 font-mono mt-0.5">
                  <span>{{ formatBytes(selectedFile.size) }}</span>
                  <span class="text-emerald-400 font-semibold">• Готов к проверке</span>
                </div>
              </div>
            </div>

            <!-- Кнопка удаления файла с hover-эффектом -->
            <button
              @click="removeSelectedFile"
              class="btn-danger px-3.5 py-2 text-xs font-semibold"
              title="Удалить выбранный файл"
            >
              <Trash2 class="w-4 h-4" />
              <span class="hidden sm:inline">Удалить</span>
            </button>
          </div>

          <!-- Видеоплеер предпросмотра -->
          <div v-if="videoPreviewUrl" class="rounded-xl overflow-hidden bg-black aspect-video border border-slate-800 shadow-2xl">
            <video
              :src="videoPreviewUrl"
              controls
              class="w-full h-full object-contain"
            ></video>
          </div>
        </div>

        <!-- Сообщение об ошибке запроса -->
        <div v-if="errorMessage" class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-sm text-rose-300 flex items-start gap-3 shadow-lg">
          <AlertCircle class="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div class="flex-1 space-y-1">
            <p class="font-bold text-rose-200">{{ errorMessage }}</p>
            <p class="text-slate-300 text-xs">
              Проверьте, запущен ли бэкенд на порту 8040, или настройте базовый адрес в правом верхнем углу.
            </p>
          </div>
          <button @click="errorMessage = ''" class="btn-icon p-1.5 text-slate-400 hover:text-white" title="Закрыть">
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Кнопка запуска с зеленым акцентным стилем и hover -->
        <button
          @click="startAnalysis"
          :disabled="!selectedFile"
          class="btn-primary w-full py-4 px-6 text-base"
        >
          <Sparkles class="w-5 h-5" />
          <span>{{ selectedFile ? 'Запустить AI-анализ' : 'Выберите видео для анализа' }}</span>
        </button>
      </div>

      <!-- Состояние 2: Обработка нейросетью -->
      <div v-else class="py-8 space-y-7 text-center">
        <div class="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto text-emerald-400 shadow-[0_0_25px_rgba(0,220,130,0.35)] animate-pulse">
          <Sparkles class="w-8 h-8" />
        </div>

        <div class="space-y-2">
          <h3 class="text-2xl font-bold text-white">
            {{ uploadProgress < 100 ? 'Загрузка видео на сервер...' : 'Анализ видеозаписи нейросетью...' }}
          </h3>
          <p class="text-sm text-slate-300 font-mono">
            {{ elapsedSeconds }} сек • Поиск нарушений регламента
          </p>
        </div>

        <!-- Линия прогресса с изумрудным градиентом -->
        <div class="max-w-md mx-auto space-y-2.5">
          <div class="w-full h-2.5 rounded-full bg-dark-950 border border-slate-800 overflow-hidden p-0.5">
            <div
              v-if="uploadProgress < 100"
              class="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-300 transition-all duration-200 shadow-[0_0_12px_#00dc82]"
              :style="{ width: `${uploadProgress}%` }"
            ></div>
            <div
              v-else
              class="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-300 animate-pulse w-full shadow-[0_0_12px_#00dc82]"
            ></div>
          </div>
          <div class="flex justify-between text-xs text-slate-400 font-mono">
            <span class="text-emerald-400 font-semibold">{{ uploadProgress < 100 ? `${uploadProgress}%` : 'Обработка моделью' }}</span>
            <span v-if="activeJobId">Job: {{ activeJobId }}</span>
          </div>
        </div>

        <button
          @click="cancelAnalysis"
          class="btn-secondary px-6 py-2.5 text-sm"
        >
          Отменить анализ
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { AlertCircle, Film, Sparkles, Trash2, UploadCloud, X } from 'lucide-vue-next'
import { pollJobUntilComplete, uploadVideoForAnalysis } from '@/lib/api'
import { formatBytes } from '@/lib/format'
import type { AnalysisResponse } from '@/types'

const emit = defineEmits<{
  (e: 'analysis-complete', payload: { result: AnalysisResponse; videoFile: File; previewUrl: string }): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const videoPreviewUrl = ref<string>('')
const isDragging = ref(false)

const isAnalyzing = ref(false)
const uploadProgress = ref(0)
const activeJobId = ref<string>('')
const elapsedSeconds = ref(0)
const errorMessage = ref('')

let timerInterval: any = null
let abortFlag = false

function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    setFile(target.files[0])
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer && e.dataTransfer.files.length > 0) {
    setFile(e.dataTransfer.files[0])
  }
}

function setFile(file: File) {
  errorMessage.value = ''
  selectedFile.value = file

  if (videoPreviewUrl.value) {
    URL.revokeObjectURL(videoPreviewUrl.value)
  }
  videoPreviewUrl.value = URL.createObjectURL(file)
}

function removeSelectedFile() {
  selectedFile.value = null
  if (videoPreviewUrl.value) {
    URL.revokeObjectURL(videoPreviewUrl.value)
    videoPreviewUrl.value = ''
  }
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

async function startAnalysis() {
  if (!selectedFile.value) return

  errorMessage.value = ''
  isAnalyzing.value = true
  uploadProgress.value = 0
  elapsedSeconds.value = 0
  abortFlag = false

  timerInterval = setInterval(() => {
    elapsedSeconds.value++
  }, 1000)

  try {
    const uploadRes = await uploadVideoForAnalysis(selectedFile.value, (pct) => {
      uploadProgress.value = pct
    })

    if (abortFlag) return

    uploadProgress.value = 100
    activeJobId.value = uploadRes.job_id

    let finalResult: AnalysisResponse

    if (uploadRes.immediateResult) {
      finalResult = uploadRes.immediateResult
    } else {
      finalResult = await pollJobUntilComplete(uploadRes.job_id)
    }

    if (abortFlag) return

    stopTimers()
    emit('analysis-complete', {
      result: finalResult,
      videoFile: selectedFile.value,
      previewUrl: videoPreviewUrl.value,
    })
  } catch (err: any) {
    stopTimers()
    isAnalyzing.value = false
    errorMessage.value = err.message || 'Ошибка отправки запроса к бэкенду.'
  }
}

function cancelAnalysis() {
  abortFlag = true
  stopTimers()
  isAnalyzing.value = false
}

function stopTimers() {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
}

onUnmounted(() => {
  stopTimers()
  if (videoPreviewUrl.value) {
    URL.revokeObjectURL(videoPreviewUrl.value)
  }
})
</script>
