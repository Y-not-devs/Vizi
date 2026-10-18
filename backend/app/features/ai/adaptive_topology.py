"""Адаптивная топология кассового узла (AdaptiveCashierTopology).

Динамическая локальная система координат на основе базового треугольника оборудования:
1. Базовый треугольник: Счетчик (слева) <---> Сейф (справа) <---> Кассир (внутренняя вершина).
2. Линия стола (Desk Axis): отрезок между центрами счетчика купюр и сейфа/тумбы.
3. Кассир находится с внутренней стороны стола (ближний план / максимальный bottom_y).
4. Клиентская зона: полуплоскость по другую сторону стола напротив кассира в створе оборудования.
5. Нарушитель / вход в контур: субъект в проходе слева от счетчика с опорой на пол (п. 14/16).
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np

# Цветовая схема Bounding Box в BGR:
COLOR_CASHIER: Final[tuple[int, int, int]] = (0, 220, 0)            # Зеленый
COLOR_CLIENT_VERIFIED: Final[tuple[int, int, int]] = (0, 200, 100)   # Изумрудный / Зеленый
COLOR_PENDING: Final[tuple[int, int, int]] = (0, 215, 255)           # Желтый / Оранжевый
COLOR_VIOLATION: Final[tuple[int, int, int]] = (0, 0, 255)           # Красный (нарушение)
COLOR_REFLECTION: Final[tuple[int, int, int]] = (130, 130, 130)      # Приглушенный серый


def is_customer_at_desk(
    person_box: list[int] | tuple[int, int, int, int],
    frame_shape: tuple[int, int] | list[int],
    min_bottom_y: float = 0.45,
) -> bool:
    """Проверяет, находится ли клиент в секторе обслуживания за столом (п. 20).

    Человек считается присутствующим клиентом (customer_present = True)
    только пока он находится в секторе взаимодействия за столом:
    - Зона выхода / коридора: ушел влево к стеклянной двери (cx < 0.35) -> False
    - Зона в глубине коридора (bottom_y < min_bottom_y) -> False
    - Зона за столом напротив кассира или сбоку (cx >= 0.35, bottom_y >= min_bottom_y) -> True
    """
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = person_box
    cx = ((x1 + x2) / 2.0) / float(w)
    bottom_y = float(y2) / float(h)

    # Зона выхода / коридора: ушел влево к стеклянной двери
    if cx < 0.35:
        return False  # Клиент покинул рабочее место кассира

    # Зона за столом напротив кассира или сбоку
    return bottom_y >= min_bottom_y


def get_person_display_attributes(
    role: str,
    session_context: dict[str, Any],
    confidence: float | None = None,
    person_box: list[int] | tuple[int, int, int, int] | None = None,
    frame_shape: tuple[int, int] | list[int] | None = None,
) -> tuple[str, tuple[int, int, int]]:
    """Возвращает текст метки и цвет рамки (Dynamic State Promotion).

    Архитектурное правило Dynamic State Promotion:
    1. Секунда 0–3: Человек только подошел -> [PENDING: VISITOR] (желтый/янтарный).
    2. Взаимодействие в лотке: [CLIENT: IDENTIFYING...] (желтый/янтарный).
    3. Секунда 4+: Документы верифицированы VLM -> [CLIENT: VERIFIED] (зеленый).
    4. Красный цвет остается для нарушений:
       - customer_count > 1 (второй клиент при уже обслуживаемом клиенте, п. 14).
       - клиент покинул рабочее место до закрытия операции -> [!] CLIENT LEFT PREMISES.
    """
    is_id_verified = session_context.get("id_verified", False)
    is_operation_active = session_context.get("operation_active", False)
    client_left_premises = (
        session_context.get("client_left_premises", False)
        or (role == "CLIENT_LEFT")
    )

    at_desk = True
    if person_box is not None and frame_shape is not None:
        at_desk = is_customer_at_desk(person_box, frame_shape)
    elif role == "CLIENT_LEFT":
        at_desk = False

    if role == "CASHIER":
        label, color = "[CASHIER]", COLOR_CASHIER
    elif role in (
        "CUSTOMER",
        "CLIENT_LEFT",
        "VISITOR_IN_CASH_ROOM",
        "UNAUTHORIZED_ACCESS",
        "UNAUTHORIZED_IN_CASH_ROOM",
    ):
        # 1. Если клиент ушел от стола в коридор/к двери во время активной сессии:
        if not at_desk and (
            client_left_premises or session_context.get("client_left_time") is not None
        ):
            label, color = "[!] CLIENT LEFT PREMISES", COLOR_VIOLATION
        # Если человек действительно чужой (например, второй клиент при первом активном):
        elif session_context.get("customer_count", 0) > 1 and at_desk:
            label, color = "[!] UNAUTHORIZED PERSON", COLOR_VIOLATION
        # Если документы проверены ИЛИ сессия обслуживания штатно открыта, и клиент за столом:
        elif at_desk and (is_id_verified or is_operation_active):
            label, color = "[CLIENT: VERIFIED]", COLOR_CLIENT_VERIFIED
        # Клиент ушел из клиентской зоны (не за столом)
        elif not at_desk:
            label, color = "[!] CLIENT LEFT PREMISES", COLOR_VIOLATION
        # Если операция еще не подтверждена, но идет взаимодействие:
        elif session_context.get("tray_active", False):
            label, color = "[CLIENT: IDENTIFYING...]", COLOR_PENDING
        # Человек только подошел или зашел сбоку до верификации
        elif (
            role in ("VISITOR_IN_CASH_ROOM", "UNAUTHORIZED_IN_CASH_ROOM")
            or session_context.get("pending", False)
        ):
            label, color = "[PENDING: VISITOR]", COLOR_PENDING
        # Дефолтный статус посетителя у стойки до начала операции
        else:
            label, color = "[CLIENT]", COLOR_CLIENT_VERIFIED
    elif role in ("REFLECT_GLASS", "REFLECTION"):
        label, color = "[REFLECT: GLASS]", COLOR_REFLECTION
    else:
        label, color = "[UNKNOWN]", (180, 180, 180)

    if confidence is not None:
        label = f"{label} {confidence:.2f}"

    return label, color


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
            at_desk = is_customer_at_desk(cand["box"], frame_shape)

            if is_across_table and in_desk_sector and at_desk:
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

            elif cx < 0.35 and bottom_y >= 0.44:
                # ЧЕЛОВЕК СЛЕВА В ПРОХОДЕ К ДВЕРИ = ПОСТОРОННИЙ В КОНТУРЕ
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


__all__ = [
    "COLOR_CASHIER",
    "COLOR_CLIENT_VERIFIED",
    "COLOR_PENDING",
    "COLOR_VIOLATION",
    "COLOR_REFLECTION",
    "AdaptiveCashierTopology",
    "get_person_display_attributes",
    "is_customer_at_desk",
]
