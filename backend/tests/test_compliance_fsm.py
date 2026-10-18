"""Тесты нормативного сценарного автомата BankComplianceFSM (Правила № 231 НБ РК)."""

from app.features.ai.compliance_fsm import (
    BankComplianceFSM,
    BankDeskZones,
    FrameDetections,
    SessionType,
    VLMComplianceJudge,
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
