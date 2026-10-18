"""Тесты нормативного сценарного автомата BankComplianceFSM (Правила № 231 НБ РК)."""

from app.features.ai.compliance_fsm import (
    LAW_UNAUTHORIZED_ACCESS_ROOM,
    BankComplianceFSM,
    BankDeskZones,
    FrameDetections,
    SessionType,
    VLMComplianceJudge,
    classify_person_strict,
    filter_reflection_and_assign_roles,
    is_machine_counting,
    is_real_phone_violation,
    should_trigger_id_verification,
)


def test_unauthorized_access_violation() -> None:
    """Проверка п. 14: более одного посетителя в зоне обслуживания."""
    fsm = BankComplianceFSM()
    detections = FrameDetections(
        timecode=1.0,
        cashier_present=True,
        customer_count=2,  # 2 клиента одновременно
        tray_motion_score=500.0,
        detected_objects=[],
    )
    violations = fsm.evaluate_frame(detections)
    assert len(violations) == 1
    assert violations[0].type == "UNAUTHORIZED_ACCESS"
    assert "Пункт 14" in violations[0].law


def test_cashier_absent_violation() -> None:
    """Проверка п. 22: оставление кассиром рабочего места >= 3 сек."""
    fsm = BankComplianceFSM()

    # Кассир только что ушел (0 сек)
    v0 = fsm.evaluate_frame(
        FrameDetections(
            timecode=1.0,
            cashier_present=False,
            customer_count=1,
            tray_motion_score=0.0,
            detected_objects=[],
        )
    )
    assert len(v0) == 0

    # Прошло 2 секунды (еще нет нарушения)
    v1 = fsm.evaluate_frame(
        FrameDetections(
            timecode=3.0,
            cashier_present=False,
            customer_count=1,
            tray_motion_score=0.0,
            detected_objects=[],
        )
    )
    assert len(v1) == 0

    # Прошло 3.5 секунды -> триггер нарушения
    v2 = fsm.evaluate_frame(
        FrameDetections(
            timecode=4.5,
            cashier_present=False,
            customer_count=1,
            tray_motion_score=0.0,
            detected_objects=[],
        )
    )
    assert len(v2) == 1
    assert v2[0].type == "CASHIER_ABSENT"
    assert "Пункт 22" in v2[0].law

    # Кассир вернулся -> таймер сбрасывается
    v3 = fsm.evaluate_frame(
        FrameDetections(
            timecode=5.0,
            cashier_present=True,
            customer_count=1,
            tray_motion_score=0.0,
            detected_objects=[],
        )
    )
    assert len(v3) == 0
    assert fsm.cashier_left_time is None


def test_counting_without_client_violation() -> None:
    """Проверка п. 20: пересчет денег в отсутствие клиента в рамках CUSTOMER_SESSION."""
    fsm = BankComplianceFSM()

    # 1. Клиент подошел к стойке (началась клиентская сессия)
    fsm.evaluate_frame(
        FrameDetections(
            timecode=1.0,
            cashier_present=True,
            customer_count=1,
            tray_motion_score=0.0,
            detected_objects=[],
        )
    )
    assert fsm.session_mode == SessionType.CUSTOMER_SESSION

    # 2. Клиент ушел во время операции, но в лотке активность (0 сек)
    v0 = fsm.evaluate_frame(
        FrameDetections(
            timecode=10.0,
            cashier_present=True,
            customer_count=0,
            tray_motion_score=4500.0,
            detected_objects=[],
        )
    )
    assert len(v0) == 0

    # 3. Прошло 2.5 сек активности в лотке без клиента -> CRITICAL нарушение п. 20
    v1 = fsm.evaluate_frame(
        FrameDetections(
            timecode=12.5,
            cashier_present=True,
            customer_count=0,
            tray_motion_score=4800.0,
            detected_objects=[],
        )
    )
    assert len(v1) == 1
    assert v1[0].type == "COUNTING_WITHOUT_CLIENT"
    assert "Пункт 20" in v1[0].law
    assert v1[0].severity == "CRITICAL"


def test_internal_operation_mode_suppression() -> None:
    """Проверка режима INTERNAL_OPERATION: инкассация/ревизия без клиента не дает ложных алертов."""
    fsm = BankComplianceFSM()

    # Клиента нет с самого начала (t=0..15 сек), кассир пересчитывает ценности/инкассацию
    for t in [1.0, 3.5, 7.0, 10.0, 15.0]:
        violations = fsm.evaluate_frame(
            FrameDetections(
                timecode=t,
                cashier_present=True,
                customer_count=0,
                tray_motion_score=6000.0,
                detected_objects=[],
            )
        )
        # В режиме инкассации п. 20 заблокирован
        assert len(violations) == 0

    assert fsm.session_mode == SessionType.INTERNAL_OPERATION


def test_prohibited_items_violation() -> None:
    """Проверка п. 12: запрещенные личные вещи на кассе."""
    fsm = BankComplianceFSM()
    detections = FrameDetections(
        timecode=1.0,
        cashier_present=True,
        customer_count=1,
        tray_motion_score=100.0,
        detected_objects=["cell phone", "cup"],
    )
    violations = fsm.evaluate_frame(detections)
    assert len(violations) == 1
    assert violations[0].type == "PROHIBITED_ITEMS"
    assert "cell phone" in violations[0].desc
    assert "cup" in violations[0].desc
    assert "Пункт 12" in violations[0].law


def test_zone_definitions() -> None:
    """Проверка работы полигонов зон кассового узла (Equipment Anchor Framework)."""
    zones = BankDeskZones()

    # Центр кассы и сектор наклона к сейфу (0.20 <= cx <= 0.68)
    assert zones.cashier_zone.contains_point(0.50, 0.60)
    assert not zones.customer_zone.contains_point(0.50, 0.60)
    assert zones.cashier_zone.contains_point(0.62, 0.65)  # Наклон к сейфу справа

    # Клиентская сторона перед стойкой / за перегородкой справа (cx >= 0.68)
    assert zones.customer_zone.contains_point(0.75, 0.40)
    assert not zones.cashier_zone.contains_point(0.75, 0.40)


def test_anti_reflection_solutions() -> None:
    """Проверка всех 3 решений фильтрации отражений в стекле двери."""
    zones = BankDeskZones()

    # 1. Решение 1 (Маска исключения): точка в створе стеклянной двери
    assert zones.is_glass_reflection(0.15, 0.30, box_h_ratio=0.45)
    assert not zones.is_valid_customer(0.15, 0.30, box_h_ratio=0.45)

    # 2. Решение 3 (Фильтр высоты): мелкий объект вдалеке слева
    assert zones.is_glass_reflection(0.25, 0.25, box_h_ratio=0.15)
    assert not zones.is_valid_customer(0.25, 0.25, box_h_ratio=0.15)

    # 3. Решение 2 (Суженная клиентская зона): реальный посетитель перед кассовым окном
    # Высота достаточная (0.45), координаты перед лотком/справа (0.75, 0.45)
    assert not zones.is_glass_reflection(0.75, 0.45, box_h_ratio=0.45)
    assert zones.is_valid_customer(0.75, 0.45, box_h_ratio=0.45)


def test_vlm_judge_fallback() -> None:
    """Проверка работы VLM-судьи при отсутствии внешнего API."""
    judge = VLMComplianceJudge(base_url="http://non-existent-host:11434")
    res = judge.verify_id_presentation(crop_base64="mock_b64", timecode=2.0)
    assert "id_presented" in res
    assert "confidence" in res
    assert isinstance(res["id_presented"], bool)


def test_should_trigger_id_verification() -> None:
    """Проверка оптимизации FSM: опрос VLM строго при наличии пары кассир + клиент."""
    # 1. Нет кассира
    assert not should_trigger_id_verification(
        cashier_present=False,
        customer_present=True,
        tray_motion_score=5000.0,
        id_already_verified=False,
    )

    # 2. Нет клиента (кассир одна считает деньги / перекладывает бумаги)
    assert not should_trigger_id_verification(
        cashier_present=True,
        customer_present=False,
        tray_motion_score=8000.0,
        id_already_verified=False,
    )

    # 3. Оба есть, но нет контакта с лотком (score ниже порога)
    assert not should_trigger_id_verification(
        cashier_present=True,
        customer_present=True,
        tray_motion_score=2000.0,
        id_already_verified=False,
    )

    # 4. Оба есть, контакт есть, но проверка уже пройдена в сессии
    assert not should_trigger_id_verification(
        cashier_present=True,
        customer_present=True,
        tray_motion_score=5000.0,
        id_already_verified=True,
    )

    # 5. Идеальные условия транзакции: оба на месте + контакт с лотком
    assert should_trigger_id_verification(
        cashier_present=True,
        customer_present=True,
        tray_motion_score=5000.0,
        id_already_verified=False,
    )


def test_motion_gated_phone_filter() -> None:
    """Проверка фильтрации стационарной техники на кассовом столе (Motion-Gated)."""
    # 1. Сканер штрих-кода слева внизу при низкой динамике
    # (cx = 0.30, cy = 0.70)
    assert not is_real_phone_violation(
        phone_box=[100, 550, 180, 640],
        frame_shape=(848, 464),
        motion_crop_score=1500.0,
        cashier_box=[160, 240, 240, 420],
    )

    # 2. Стационарный телефон / трубка справа при низкой динамике
    # (cx = 0.75, cy = 0.60)
    assert not is_real_phone_violation(
        phone_box=[320, 470, 380, 550],
        frame_shape=(848, 464),
        motion_crop_score=1200.0,
        cashier_box=[160, 240, 240, 420],
    )

    # 3. Реальный смартфон кассира: высокая динамика и нахождение в рабочей зоне
    assert is_real_phone_violation(
        phone_box=[180, 320, 220, 390],
        frame_shape=(848, 464),
        motion_crop_score=5500.0,
        cashier_box=[160, 240, 240, 420],
    )


def test_machine_counting_detection() -> None:
    """Проверка детекции активности купюросчетной машины через микро-ROI."""
    import numpy as np

    # Пустой diff (машинка выключена)
    static_diff = np.zeros((848, 464), dtype=np.uint8)
    assert not is_machine_counting(static_diff, (848, 464))

    # Активный diff в зоне счетной машинки (x1=0.12*464=55, y1=0.48*848=407, x2=176, y2=695)
    active_diff = np.zeros((848, 464), dtype=np.uint8)
    active_diff[450:550, 70:150] = 255  # 100x80 = 8000 активных пикселей
    assert is_machine_counting(active_diff, (848, 464), energy_threshold=500)


def test_classify_person_strict() -> None:
    """Проверка точечной строгой классификации ролей и фильтрации отражений."""
    frame_shape = (848, 464)

    # 1. Отражение в стекле двери (висит высоко, малая площадь)
    # cx ~ 0.06, bot_y = 290/848 = 0.342, area = 53*69/(464*848) = 0.0093
    reflect_box = [0, 221, 53, 290]
    assert classify_person_strict(reflect_box, frame_shape) == "REFLECT_GLASS"

    # 2. Реальный человек, вошедший через левую дверь (Ground Contact / Footprint)
    # cx ~ 0.16, bot_y = 414/848 = 0.488, area = 74*206/(464*848) = 0.0387
    visitor_door_box = [36, 208, 110, 414]
    assert classify_person_strict(visitor_door_box, frame_shape) == "VISITOR_IN_CASH_ROOM"

    # 3. Кассир в кресле перед столом (нижняя опора глубоко на полу перед камерой)
    # cx ~ 0.50, bot_y = 570/848 = 0.672
    cashier_box = [185, 388, 284, 570]
    assert classify_person_strict(cashier_box, frame_shape) == "CASHIER"

    # 4. Посетитель с внешней клиентской стороны (cx >= 0.45)
    customer_box = [320, 250, 400, 500]
    assert classify_person_strict(customer_box, frame_shape) == "CUSTOMER"

    # 5. Комплексное распределение ролей в кадре через filter_reflection_and_assign_roles
    boxes_with_conf = [
        (reflect_box, 0.65),
        (visitor_door_box, 0.85),
        (cashier_box, 0.75),
    ]
    persons = filter_reflection_and_assign_roles(boxes_with_conf, frame_shape)
    assert len(persons) == 3
    assert any(p.role == "CASHIER" for p in persons)
    assert any(p.role == "VISITOR_IN_CASH_ROOM" for p in persons)
    assert any(p.role in ("REFLECT_GLASS", "REFLECTION") for p in persons)


def test_ground_contact_no_reflection() -> None:
    """Проверка правила: если основание BBox на полу (bottom_y > 0.55), это НЕ отражение."""
    frame_shape = (848, 464)
    # y2 = 500 / 848 = 0.59 > 0.55
    standing_person = [30, 200, 110, 500]
    role = classify_person_strict(standing_person, frame_shape)
    assert role != "REFLECT_GLASS"
    assert role == "VISITOR_IN_CASH_ROOM"


def test_unauthorized_room_access_violation() -> None:
    """Проверка п. 16 Правил № 14 / п. 14 Правил № 231 (Второй человек в помещении кассы)."""
    fsm = BankComplianceFSM()

    # В служебной зоне обнаружен посетитель/инкассатор (до проверки ID)
    d = FrameDetections(
        timecode=3.0,
        cashier_present=True,
        customer_count=0,
        visitor_in_room_count=1,
        tray_motion_score=8000.0,
        detected_objects=[],
    )
    violations = fsm.evaluate_frame(d)
    assert len(violations) == 1
    assert violations[0].type == "UNAUTHORIZED_ACCESS"
    assert violations[0].law == LAW_UNAUTHORIZED_ACCESS_ROOM
    assert "Пункт 16" in violations[0].law
    assert "Пункт 14" in violations[0].law
    assert violations[0].severity == "CRITICAL"

    # После успешной проверки документов VLM статус авторизуется
    fsm.id_verified = True
    d_verified = FrameDetections(
        timecode=7.5,
        cashier_present=True,
        customer_count=0,
        visitor_in_room_count=1,
        tray_motion_score=8000.0,
        detected_objects=[],
    )
    violations_after = fsm.evaluate_frame(d_verified)
    assert len(violations_after) == 0

