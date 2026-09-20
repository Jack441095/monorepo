"""Tests for Thursday Phase 2: In-Process Event Bus & Focus Mode Deferral Guard."""



from thursday.events import Event, EventBus, EventPriority, FocusMode, get_event_bus
from thursday.user_profile import get_focus_mode, set_focus_mode


def test_event_bus_singleton():
    bus1 = get_event_bus()
    bus2 = get_event_bus()
    assert bus1 is bus2


def test_event_bus_pub_sub():
    bus = EventBus()
    received = []

    def handler(evt: Event):
        received.append(evt)

    bus.subscribe("TEST_EVENT", handler)

    evt1 = Event(event_type="TEST_EVENT", payload={"msg": "hello"})
    bus.publish(evt1)

    assert len(received) == 1
    assert received[0].payload["msg"] == "hello"


def test_event_bus_topic_subscription():
    bus = EventBus()
    received = []

    bus.subscribe_topic("monitor", lambda evt: received.append(evt))

    evt = Event(event_type="PROACTIVE_ALERT", topic="monitor", payload={"id": "123"})
    bus.publish(evt)

    assert len(received) == 1
    assert received[0].payload["id"] == "123"


def test_focus_mode_deferral_guard():
    bus = EventBus()
    received = []

    bus.subscribe_all(lambda evt: received.append(evt))
    bus.set_focus_mode(FocusMode.FOCUS_MIXING)

    # Normal priority event should be deferred
    norm_evt = Event(event_type="ALERT", priority=EventPriority.NORMAL, payload={"test": 1})
    dispatched = bus.publish(norm_evt)

    assert dispatched is False
    assert len(received) == 0
    assert len(bus.get_deferred_events()) == 1

    # Critical event should bypass focus mode deferral
    crit_evt = Event(event_type="ALERT", priority=EventPriority.CRITICAL, payload={"test": 2})
    dispatched_crit = bus.publish(crit_evt)

    assert dispatched_crit is True
    assert len(received) == 1

    # Transitioning back to AVAILABLE flushes deferred events
    flushed = bus.set_focus_mode(FocusMode.AVAILABLE)

    assert len(flushed) == 1
    assert len(received) == 2
    assert len(bus.get_deferred_events()) == 0


def test_user_profile_focus_mode_integration():
    profile = set_focus_mode("focus_mixing", profile_id="test_profile_events")
    assert profile["preferences"]["focus_mode"] == "focus_mixing"
    assert get_focus_mode("test_profile_events") == "focus_mixing"

    # Reset
    set_focus_mode("available", profile_id="test_profile_events")
    assert get_focus_mode("test_profile_events") == "available"
