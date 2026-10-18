"""Тесты нормативного сценарного автомата BankComplianceFSM (Правила № 231 НБ РК)."""

from app.features.ai.compliance_fsm import (
    BankComplianceFSM,
    BankDeskZones,
    FrameDetections,
    VLMComplianceJudge,
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
    """Проверка п. 20: пересчет денег в отсутствие клиента."""
    fsm = BankComplianceFSM()

    # Клиент ушел, но в лотке активность (0 сек)
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

    # Прошло 2.5 сек активности в лотке без клиента -> CRITICAL нарушение
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
    """Проверка работы полигонов зон кассового узла."""
    zones = BankDeskZones()

    # Центр кассы (кассир)
    assert zones.cashier_zone.contains_point(0.50, 0.60)
    assert not zones.customer_zone.contains_point(0.50, 0.60)

    # Клиентская сторона перед стойкой
    assert zones.customer_zone.contains_point(0.60, 0.40)
    assert not zones.cashier_zone.contains_point(0.60, 0.40)


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
    # Высота достаточная (0.45), координаты перед лотком (0.65, 0.45)
    assert not zones.is_glass_reflection(0.65, 0.45, box_h_ratio=0.45)
    assert zones.is_valid_customer(0.65, 0.45, box_h_ratio=0.45)


def test_vlm_judge_fallback() -> None:
    """Проверка работы VLM-судьи при отсутствии внешнего API."""
    judge = VLMComplianceJudge(base_url="http://non-existent-host:11434")
    res = judge.verify_id_presentation(crop_base64="mock_b64", timecode=2.0)
    assert "id_presented" in res
    assert "confidence" in res
    assert isinstance(res["id_presented"], bool)
