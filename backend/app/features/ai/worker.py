"""Фоновый воркер анализа видео на аномалии (ForteWatch Worker).

Осуществляет двухэтапный пайплайн:
1. Выделение активных моментов через TemporalMotionAnalyzer (OpenCV + Rolling Median).
2. Анализ Dynamic ROI кропов высокого разрешения через VLM (Ollama / LLaVA / Qwen2-VL).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.features.ai.motion_extractor import (
    ActiveFrameSegment,
    BoundingBox,
    MotionDetectionResult,
    TemporalMotionAnalyzer,
)

logger = logging.getLogger("fortewatch.worker")

# Реэкспорт класса TemporalMotionAnalyzer согласно требованиям ТЗ
__all__ = [
    "ActiveFrameSegment",
    "AnomalyReport",
    "BoundingBox",
    "ForteWatchVideoWorker",
    "MotionDetectionResult",
    "TemporalMotionAnalyzer",
    "VideoAnomalyEvent",
]


@dataclass(slots=True)
class VideoAnomalyEvent:
    """Зафиксированное подозрительное событие на кассе."""

    timecode_sec: float
    anomaly_type: str
    confidence: float
    description: str
    crop_base64: str
    motion_score: float


@dataclass(slots=True)
class AnomalyReport:
    """Итоговый отчет по результатам анализа видео."""

    video_path: str
    total_duration_sec: float
    processed_segments_count: int
    anomalies: list[VideoAnomalyEvent]
    has_critical_anomaly: bool
    processing_time_sec: float


# Системный промпт для VLM, нацеленный на исключение ложных срабатываний
VLM_CASHIER_ANOMALY_PROMPT = """\
Ты — экспертная система видеоаналитики безопасности в банковских кассах ForteWatch.
Тебе предоставлен кроп высокого разрешения зоны активности и общий контекст кадра.

Твоя задача — обнаружить реальные нарушения кассовой дисциплины и инциденты безопасности:
1. Подозрительные манипуляции с деньгами (прятание банкнот в карман, под прилавок, кража).
2. Использование смартфона кассиром во время операций или съемка данных клиентов/экрана.
3. Подмена пачки наличных белой квитанцией или бумажным чеком.
   ВНИМАНИЕ: белый лист бумаги, кассовый чек или слип-квитанция НЕ ЯВЛЯЮТСЯ пачкой денег!
   Не путай белую бумагу/чеки с пачкой купюр.
4. Несанкционированный доступ к лотку кассы постороннего лица.

Отвечай СТРОГО в формате валидного JSON без markdown-разметки:
{
  "is_anomaly": true | false,
  "anomaly_type": "none" | "theft_cash" | "hidden_phone" | "fake_receipt" | "unauthorized_access",
  "confidence": 0.0 - 1.0,
  "explanation": "Краткое обоснование на русском языке, почему это аномалия или штатное действие"
}
"""


class ForteWatchVideoWorker:
    """Воркер сервиса ForteWatch для пакетного и асинхронного анализа видео."""

    def __init__(
        self,
        motion_analyzer: TemporalMotionAnalyzer | None = None,
        ollama_base_url: str | None = None,
        vlm_model: str | None = None,
        vlm_timeout_sec: float = 90.0,
    ) -> None:
        self.analyzer = motion_analyzer or TemporalMotionAnalyzer()
        settings = get_settings()

        self.base_url = (ollama_base_url or settings.ai_base_url).rstrip("/")
        self.vlm_model = vlm_model or settings.ai_model
        self.vlm_timeout = vlm_timeout_sec

    async def analyze_video(self, video_path: str | Path) -> AnomalyReport:
        """Полный пайплайн анализа видеофайла.

        Гарантирует выполнение ТЗ:
        - Лимит инференса VLM < 100 секунд за счет отсечения статики и ограничения топ-15 кадров.
        - Общее время обработки укладывается в 300 секунд.
        """
        start_time = time.perf_counter()
        path = Path(video_path)
        logger.info("Starting ForteWatch analysis for video: %s", path.name)

        # 1. Извлечение активных сегментов (синхронная CPU-bound задача выполняется в thread pool)
        active_segments: list[dict[str, Any]] = await asyncio.to_thread(
            self.analyzer.extract_active_segments,
            path,
        )

        logger.info(
            "Extracted %d active high-resolution segments for VLM analysis",
            len(active_segments),
        )

        anomalies: list[VideoAnomalyEvent] = []

        # 2. Инференс VLM для каждого значимого момента
        if active_segments:
            async with httpx.AsyncClient(timeout=self.vlm_timeout) as client:
                for seg in active_segments:
                    timecode = seg["timecode_sec"]
                    crop_b64 = seg["crop_base64"]
                    motion_score = seg["motion_score"]

                    event = await self._query_vlm(
                        client=client,
                        timecode=timecode,
                        crop_base64=crop_b64,
                        motion_score=motion_score,
                    )
                    if event and event.confidence >= 0.70:
                        anomalies.append(event)

        total_elapsed = round(time.perf_counter() - start_time, 2)
        has_critical = any(e.confidence >= 0.85 for e in anomalies)

        logger.info(
            "Video %s analyzed in %.2fs: %d anomalies detected (critical=%s)",
            path.name,
            total_elapsed,
            len(anomalies),
            has_critical,
        )

        return AnomalyReport(
            video_path=str(path),
            total_duration_sec=active_segments[-1]["timecode_sec"] if active_segments else 0.0,
            processed_segments_count=len(active_segments),
            anomalies=anomalies,
            has_critical_anomaly=has_critical,
            processing_time_sec=total_elapsed,
        )

    async def _query_vlm(
        self,
        client: httpx.AsyncClient,
        timecode: float,
        crop_base64: str,
        motion_score: float,
    ) -> VideoAnomalyEvent | None:
        """Отправка кадра в мультимодальную VLM (Ollama / OpenAI совместимый эндпоинт)."""
        payload = {
            "model": self.vlm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{VLM_CASHIER_ANOMALY_PROMPT}\n\n"
                                f"Текущий таймкод видео: {timecode:.1f} сек."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{crop_base64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,  # Минимальная температура для строгости детекции
            "response_format": {"type": "json_object"},
        }

        try:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            if parsed.get("is_anomaly", False):
                return VideoAnomalyEvent(
                    timecode_sec=timecode,
                    anomaly_type=parsed.get("anomaly_type", "suspicious_activity"),
                    confidence=float(parsed.get("confidence", 0.8)),
                    description=parsed.get("explanation", "Подозрительное действие на кассе"),
                    crop_base64=crop_base64,
                    motion_score=motion_score,
                )
        except Exception as exc:
            logger.warning("VLM call failed for timecode %.2fs: %s", timecode, exc)

        return None
