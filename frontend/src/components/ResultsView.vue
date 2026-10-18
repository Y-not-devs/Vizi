<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-6">
    <!-- Верхняя панель навигации -->
    <div class="flex items-center justify-between pb-4 border-b border-dark-800">
      <button
        @click="$emit('back-to-upload')"
        class="btn-secondary px-4 py-2 text-sm font-medium"
      >
        <ArrowLeft class="w-4 h-4 text-emerald-400" />
        <span>Загрузить другое видео</span>
      </button>

      <div class="flex items-center gap-3">
        <button
          @click="showRawJson = true"
          class="btn-secondary px-3.5 py-2 text-xs font-mono"
        >
          <Code2 class="w-4 h-4 text-emerald-400" />
          <span>JSON API</span>
        </button>
      </div>
    </div>

    <!-- Вердикт (баннер) -->
    <div
      class="panel rounded-2xl p-6 sm:p-7 border transition"
      :class="isViolation
        ? 'border-rose-500/40 bg-rose-950/25 shadow-glow-rose-sm'
        : 'border-emerald-500/40 bg-emerald-950/20 shadow-[0_0_25px_-5px_rgba(0,220,130,0.25)]'"
    >
      <div class="flex items-center justify-between gap-4">
        <div class="space-y-1.5">
          <div class="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider font-semibold"
            :class="isViolation ? 'text-rose-400' : 'text-emerald-400'"
          >
            <span class="w-2 h-2 rounded-full" :class="isViolation ? 'bg-rose-500 shadow-glow-rose-sm' : 'bg-emerald-400 shadow-[0_0_8px_#00dc82]'"></span>
            <span>Вердикт анализа</span>
          </div>
          <h2
            class="text-2xl sm:text-3xl font-extrabold tracking-tight"
            :class="isViolation ? 'text-rose-400' : 'text-emerald-300'"
          >
            {{ verdictTitle }}
          </h2>
          <p class="text-sm sm:text-base text-slate-200">
            {{ isViolation ? `Зафиксировано нарушений: ${violationsCount}` : 'Нарушений кассовой дисциплины не зафиксировано.' }}
          </p>
        </div>

        <div v-if="result.job_id" class="text-right text-sm font-mono text-slate-400 hidden sm:block">
          <div class="px-3 py-1.5 rounded-lg bg-dark-950 border border-slate-800">
            ID: {{ result.job_id }}
          </div>
        </div>
      </div>
    </div>

    <!-- Сетка: Видеоплеер слева + Нарушения справа -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      <!-- Видеоплеер (5 из 12) -->
      <div class="lg:col-span-5 space-y-4 lg:sticky lg:top-20">
        <div class="panel rounded-2xl p-4 bg-black/60 space-y-3">
          <div class="rounded-xl overflow-hidden aspect-video bg-black border border-dark-800">
            <video
              ref="videoPlayerRef"
              :src="videoUrl"
              controls
              playsinline
              class="w-full h-full object-contain"
              @timeupdate="onVideoTimeUpdate"
            ></video>
          </div>

          <div v-if="violationsCount > 0" class="pt-1 flex flex-wrap gap-2">
            <button
              v-for="(violation, idx) in normalizedViolations"
              :key="idx"
              @click="seekToTimecode(violation.timecode_sec)"
              class="px-3 py-1.5 rounded-lg text-xs font-mono font-semibold border transition-all"
              :class="isCurrentTimeNear(violation.timecode_sec)
                ? 'bg-emerald-500 text-dark-950 border-emerald-400 shadow-[0_0_15px_rgba(0,220,130,0.5)] font-bold scale-105'
                : 'bg-dark-900 border-slate-700 text-slate-300 hover:border-emerald-400 hover:text-white hover:-translate-y-0.5'"
            >
              {{ formatTimecode(violation.timecode_sec) }}
            </button>
          </div>
        </div>
      </div>

      <!-- Список нарушений (7 из 12) -->
      <div class="lg:col-span-7 space-y-5">
        <!-- Если нарушений нет -->
        <div v-if="!isViolation || violationsCount === 0" class="panel rounded-2xl p-10 text-center border border-emerald-500/30 space-y-3 shadow-[0_0_30px_-8px_rgba(0,220,130,0.2)]">
          <div class="w-16 h-16 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center mx-auto text-emerald-400 shadow-[0_0_20px_rgba(0,220,130,0.3)]">
            <CheckCircle2 class="w-8 h-8" />
          </div>
          <p class="text-xl font-bold text-white">
            Нарушений не обнаружено
          </p>
          <p class="text-sm text-slate-300 max-w-md mx-auto">
            Все регламентные требования кассовой дисциплины (Постановление № 231 НБ РК) соблюдены.
          </p>
        </div>

        <!-- Если есть нарушения -->
        <div v-else class="space-y-5">
          <div
            v-for="(violation, index) in normalizedViolations"
            :key="index"
            class="panel rounded-2xl p-6 border border-dark-700 space-y-5 hover:border-slate-600 transition-all hover:shadow-[0_8px_30px_rgba(0,0,0,0.6)]"
          >
            <!-- Шапка события -->
            <div class="flex items-start justify-between gap-3 pb-4 border-b border-dark-800">
              <div>
                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono font-semibold">
                  Событие #{{ index + 1 }}
                </span>
                <h4 class="text-lg sm:text-xl font-bold text-white mt-1.5">
                  {{ violation.type }}
                </h4>
              </div>

              <!-- Кнопка перехода к таймкоду -->
              <button
                @click="seekToTimecode(violation.timecode_sec)"
                class="btn-secondary px-3.5 py-1.5 text-xs font-mono font-semibold text-emerald-400 hover:text-white hover:border-emerald-400 hover:bg-emerald-500/20"
                title="Перейти к моменту на видео"
              >
                <span>{{ formatTimecode(violation.timecode_sec) }}</span>
              </button>
            </div>

            <!-- Описание -->
            <div class="space-y-1.5">
              <span class="text-xs sm:text-sm font-semibold text-slate-300">Что видно на видео:</span>
              <p class="text-sm sm:text-base text-slate-100 leading-relaxed bg-dark-950/80 p-4 rounded-xl border border-dark-800">
                {{ violation.description }}
              </p>
            </div>

            <!-- Нормативное правило -->
            <div class="space-y-1.5">
              <span class="text-xs sm:text-sm font-semibold text-slate-300">Правило и нормативный источник:</span>
              <div class="p-4 rounded-xl bg-dark-950/80 border border-dark-800 space-y-1.5">
                <div class="font-bold text-emerald-400 text-sm sm:text-base">
                  {{ violation.rule }}
                </div>
                <div class="text-xs sm:text-sm text-slate-300">
                  {{ violation.normative_source }}
                </div>
              </div>
            </div>

            <!-- Кадры-доказательства -->
            <div v-if="violation.evidence_frames && violation.evidence_frames.length > 0" class="space-y-2 pt-1">
              <span class="text-xs sm:text-sm font-semibold text-slate-300">Кадры-доказательства:</span>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div
                  v-for="(frame, fIdx) in violation.evidence_frames"
                  :key="fIdx"
                  @click="openEvidenceModal(frame.image_base64, frame.timestamp_sec, violation.type)"
                  class="relative rounded-xl overflow-hidden border border-dark-700 bg-black aspect-video cursor-pointer hover:border-emerald-400 hover:shadow-[0_0_20px_-2px_rgba(0,220,130,0.35)] transition-all group hover:scale-[1.02]"
                >
                  <img
                    :src="frame.image_base64"
                    :alt="`Кадр ${fIdx + 1}`"
                    class="w-full h-full object-cover group-hover:scale-105 transition duration-200"
                    loading="lazy"
                  />
                  <span class="absolute bottom-1.5 right-1.5 px-2 py-0.5 rounded bg-black/85 text-xs font-mono text-emerald-300 border border-white/10">
                    {{ formatTimecode(frame.timestamp_sec) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Модалка кадра -->
    <EvidenceModal
      :is-open="isEvidenceModalOpen"
      :image-src="activeEvidenceImage"
      :timestamp="activeEvidenceTimestamp"
      :violation-type="activeEvidenceType"
      @close="isEvidenceModalOpen = false"
    />

    <!-- Модалка сырого JSON -->
    <RawJsonModal
      :is-open="showRawJson"
      :job-id="result.job_id"
      :payload="result.raw_response || result"
      @close="showRawJson = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, CheckCircle2, Code2 } from 'lucide-vue-next'
import EvidenceModal from './EvidenceModal.vue'
import RawJsonModal from './RawJsonModal.vue'
import { formatTimecode } from '@/lib/format'
import type { AnalysisResponse, Violation } from '@/types'

const props = defineProps<{
  result: AnalysisResponse
  videoFile?: File | null
  videoUrl?: string
}>()

defineEmits<{
  (e: 'back-to-upload'): void
}>()

const videoPlayerRef = ref<HTMLVideoElement | null>(null)
const currentVideoTime = ref(0)

const isEvidenceModalOpen = ref(false)
const activeEvidenceImage = ref('')
const activeEvidenceTimestamp = ref<number | undefined>(undefined)
const activeEvidenceType = ref('')

const showRawJson = ref(false)

const normalizedViolations = computed<Violation[]>(() => {
  return props.result.violations || []
})

const violationsCount = computed(() => {
  return normalizedViolations.value.length
})

const isViolation = computed(() => {
  if (props.result.verdict === 'violation') return true
  if (props.result.verdict === 'no_violation') return false
  return violationsCount.value > 0
})

const verdictTitle = computed(() => {
  return isViolation.value
    ? 'Обнаружены признаки возможных нарушений'
    : 'Нарушение не обнаружено'
})

function onVideoTimeUpdate() {
  if (videoPlayerRef.value) {
    currentVideoTime.value = videoPlayerRef.value.currentTime
  }
}

function seekToTimecode(seconds: number) {
  if (videoPlayerRef.value) {
    videoPlayerRef.value.currentTime = Math.max(0, seconds - 0.5)
    videoPlayerRef.value.play().catch(() => {})
  }
}

function isCurrentTimeNear(seconds: number): boolean {
  return Math.abs(currentVideoTime.value - seconds) < 1.5
}

function openEvidenceModal(imageSrc: string, timestamp?: number, type?: string) {
  activeEvidenceImage.value = imageSrc
  activeEvidenceTimestamp.value = timestamp
  activeEvidenceType.value = type || ''
  isEvidenceModalOpen.value = true
}
</script>
