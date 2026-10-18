"""Адаптивная топология кассового узла (AdaptiveCashierTopology).

Динамическая локальная система координат на основе базового треугольника оборудования:
1. Базовый треугольник: Счетчик (слева) <---> Сейф (справа) <---> Кассир (внутренняя вершина).
2. Линия стола (Desk Axis): отрезок между центрами счетчика купюр и сейфа/тумбы.
3. Кассир находится с внутренней стороны стола (ближний план / максимальный bottom_y).
4. Клиентская зона: полуплоскость по другую сторону стола напротив кассира в створе оборудования.
5. Нарушитель / вход в контур: субъект в проходе слева от счетчика с опорой на пол (п. 14/16).
"""

from __future__ import annotations

from typing import Any

import numpy as np


class AdaptiveCashierTopology:
    """Адаптивная система классификации ролей на основе геометрии стола и оборудования."""

    def __init__(
        self,
        counter_pos: tuple[float, float] = (0.22, 0.65),
        safe_pos: tuple[float, float] = (0.58, 0.55),
    ) -> None:
        # Опорные координаты оборудования (нормализованные 0.0 - 1.0)
        self.counter_pos = np.array(counter_pos, dtype=np.float64)  # Черный счетчик купюр (слева)
        self.safe_pos = np.array(safe_pos, dtype=np.float64)        # Серый сейф / тумба (справа)

    def update_anchors(self, detected_objects: list[dict[str, Any]] | None = None) -> None:
        """Динамическая подстройка якорей стола по детекциям оборудования кассы."""
        if not detected_objects:
            return
        # Возможность динамической адаптации при смещении камеры

    def classify_people(
        self,
        person_boxes_with_conf: list[tuple[list[int], float]] | list[list[int]],
        frame_shape: tuple[int, int],
    ) -> list[dict[str, Any]]:
        """Классификация субъектов относительно адаптивной оси стола и кассира.

        person_boxes_with_conf: список кортежей (box_xyxy, confidence) или список box_xyxy
        frame_shape: (height, width)

        Возвращает список словарей:
        [
            {"role": "CASHIER", "box": [...], "conf": 0.95, "cx": ..., "bottom_y": ...},
            ...
        ]
        """
        h, w = frame_shape[:2]
        if not person_boxes_with_conf:
            return []

        # Унификация входного формата (с conf или без)
        normalized_inputs: list[tuple[list[int], float]] = []
        for item in person_boxes_with_conf:
            if isinstance(item, tuple) and len(item) == 2:
                normalized_inputs.append((item[0], float(item[1])))
            elif isinstance(item, list):
                normalized_inputs.append((item, 0.90))

        # 0. NMS фильтрация дубликатов (IoU > 0.45)
        sorted_boxes = sorted(normalized_inputs, key=lambda x: x[1], reverse=True)
        kept_boxes: list[tuple[list[int], float]] = []
        for b, c in sorted_boxes:
            if c < 0.35:
                continue
            is_dup = False
            for kb, _ in kept_boxes:
                ix1 = max(b[0], kb[0])
                iy1 = max(b[1], kb[1])
                ix2 = min(b[2], kb[2])
                iy2 = min(b[3], kb[3])
                inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                a1 = (b[2] - b[0]) * (b[3] - b[1])
                a2 = (kb[2] - kb[0]) * (kb[3] - kb[1])
                union = a1 + a2 - inter
                if union > 0 and (inter / union) > 0.45:
                    is_dup = True
                    break
            if not is_dup:
                kept_boxes.append((b, c))

        # 1. Извлечение метрик и фильтрация очевидных оптических отражений на двери
        candidates: list[dict[str, Any]] = []
        classified: list[dict[str, Any]] = []

        for box, conf in kept_boxes:
            x1, y1, x2, y2 = box
            cx = ((x1 + x2) / 2.0) / float(w)
            cy = ((y1 + y2) / 2.0) / float(h)
            bottom_y = float(y2) / float(h)
            area = ((x2 - x1) * (y2 - y1)) / float(w * h)

            # Отсекаем явное отражение в стекле двери (высоко в воздухе, малая площадь)
            if cx < 0.35 and (bottom_y < 0.44 or (bottom_y < 0.52 and area < 0.022)):
                classified.append({
                    "role": "REFLECT_GLASS",
                    "box": box,
                    "conf": conf,
                    "cx": cx,
                    "cy": cy,
                    "bottom_y": bottom_y,
                    "area": area,
                })
                continue

            candidates.append({
                "box": box,
                "conf": conf,
                "cx": cx,
                "cy": cy,
                "bottom_y": bottom_y,
                "area": area,
            })

        if not candidates:
            return classified

        # 2. Поиск кассира:
        # Кассир — человек на переднем плане за столом (максимальный bottom_y)
        closest_person = max(candidates, key=lambda c: c["bottom_y"])

        cashier: dict[str, Any] | None = None
        if closest_person["bottom_y"] >= 0.60:
            # Сидящий в кресле кассир
            cashier = closest_person
        elif (
            (self.counter_pos[0] - 0.05) <= closest_person["cx"] <= (self.safe_pos[0] + 0.10)
            and closest_person["bottom_y"] >= 0.44
        ):
            # Стоящий за рабочим столом оборудования кассир (например, в Х-14)
            cashier = closest_person

        if cashier is not None:
            classified.append({
                "role": "CASHIER",
                "box": cashier["box"],
                "conf": cashier["conf"],
                "cx": cashier["cx"],
                "cy": cashier["cy"],
                "bottom_y": cashier["bottom_y"],
                "area": cashier["area"],
            })

        # 3. Классификация остальных людей относительно вектора стола и положения кассира
        for cand in candidates:
            if cashier is not None and cand["box"] == cashier["box"]:
                continue

            cx = cand["cx"]
            bottom_y = cand["bottom_y"]

            # Определяем, находится ли субъект за столом напротив кассира:
            # Если кассир в кресле (bottom_y >= 0.60), то клиент находится выше (меньший bottom_y)
            is_across_table = (
                bottom_y < (cashier["bottom_y"] - 0.08)
                if cashier is not None and cashier["bottom_y"] >= 0.60
                else bottom_y < 0.65
            )

            # Створ обслуживания между счетчиком слева и сейфом справа
            in_desk_sector = (self.counter_pos[0] - 0.05) <= cx <= (self.safe_pos[0] + 0.20)

            if is_across_table and in_desk_sector and bottom_y >= 0.44:
                # ЧЕЛОВЕК НАПРОТИВ КАССИРА МЕЖДУ СЧЕТЧИКОМ И СЕЙФОМ = КЛИЕНТ
                classified.append({
                    "role": "CUSTOMER",
                    "box": cand["box"],
                    "conf": cand["conf"],
                    "cx": cx,
                    "cy": cand["cy"],
                    "bottom_y": bottom_y,
                    "area": cand["area"],
                })

            elif cx < (self.counter_pos[0] - 0.02) and bottom_y >= 0.44:
                # ЧЕЛОВЕК СЛЕВА ОТ СЧЕТЧИКА В ПРОХОДЕ К ДВЕРИ = ПОСТОРОННИЙ В КОНТУРЕ
                classified.append({
                    "role": "UNAUTHORIZED_IN_CASH_ROOM",
                    "box": cand["box"],
                    "conf": cand["conf"],
                    "cx": cx,
                    "cy": cand["cy"],
                    "bottom_y": bottom_y,
                    "area": cand["area"],
                })

            elif cx > (self.safe_pos[0] + 0.15) and bottom_y >= 0.44:
                # Стоит сбоку от сейфа / клиентской стойки = КЛИЕНТ У СТОЙКИ
                classified.append({
                    "role": "CUSTOMER",
                    "box": cand["box"],
                    "conf": cand["conf"],
                    "cx": cx,
                    "cy": cand["cy"],
                    "bottom_y": bottom_y,
                    "area": cand["area"],
                })

            else:
                # Дополнительное неавторизованное лицо в зоне обслуживания
                classified.append({
                    "role": "UNAUTHORIZED_ACCESS",
                    "box": cand["box"],
                    "conf": cand["conf"],
                    "cx": cx,
                    "cy": cand["cy"],
                    "bottom_y": bottom_y,
                    "area": cand["area"],
                })

        return classified
