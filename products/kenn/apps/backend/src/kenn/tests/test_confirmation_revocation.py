from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, Lock, current_thread

import pytest

from kenn.core import confirmation
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_recipe import LiveRecipeService


@pytest.fixture(autouse=True)
def isolated_confirmation_tokens(monkeypatch):
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {}, raising=False)
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set(), raising=False)


def _issue(session_id="owner", service_id="ableton_action", ttl_seconds=300):
    binding = {"session_id": session_id, "service_id": service_id, "text": "transport_play"}
    token, record = confirmation.issue_confirmation(**binding, ttl_seconds=ttl_seconds)
    return token, record, binding


def test_dismissed_token_fails_preview_and_cannot_be_consumed():
    # Dismiss used to hide the card while its signed token remained executable.
    token, _, binding = _issue()
    assert confirmation.verify_confirmation(token, **binding)

    assert confirmation.revoke_confirmation(token, session_id="owner")
    assert not confirmation.verify_confirmation(token, **binding)
    assert not confirmation.consume_confirmation(token, **binding)
    assert not confirmation.revoke_confirmation(token, session_id="owner")


@pytest.mark.parametrize("session_id", ["other", "", " owner", "owner "])
def test_dismiss_requires_the_exact_issuing_chat(session_id):
    token, _, binding = _issue()

    assert not confirmation.revoke_confirmation(token, session_id=session_id)
    assert confirmation.verify_confirmation(token, **binding)
    assert confirmation.consume_confirmation(token, **binding)


@pytest.mark.parametrize("token", ["", "not-a-token", "v1.ffffffff.nonce.invalid", None, 4])
def test_unknown_or_malformed_tokens_cannot_be_dismissed(token):
    assert not confirmation.revoke_confirmation(token, session_id="owner")


def test_expired_token_is_not_reported_as_cancelled(monkeypatch):
    monkeypatch.setattr(confirmation.time, "time", lambda: 100)
    token, record, binding = _issue(ttl_seconds=1)

    assert not confirmation.revoke_confirmation(token, session_id="owner", now=record["expires_at"])
    assert not confirmation.consume_confirmation(token, **binding, now=record["expires_at"])
    assert token not in confirmation._ISSUED_TOKENS


def test_used_confirmation_keeps_preview_semantics_but_cannot_be_cancelled():
    token, _, binding = _issue()
    assert confirmation.consume_confirmation(token, **binding)

    assert confirmation.verify_confirmation(token, **binding)
    assert not confirmation.revoke_confirmation(token, session_id="owner")
    assert confirmation.revoke_session_confirmations(session_id="owner") == 0
    assert not confirmation.consume_confirmation(token, **binding)


def test_session_cancel_covers_all_services_without_affecting_another_chat():
    own = [_issue(service_id=name) for name in ("ableton_action", "ableton_recipe", "ableton_control", "midi_clip")]
    other, _, other_binding = _issue(session_id="other")
    used, _, used_binding = _issue()
    assert confirmation.consume_confirmation(used, **used_binding)

    assert confirmation.revoke_session_confirmations(session_id="owner") == len(own)
    assert confirmation.revoke_session_confirmations(session_id="owner") == 0
    for token, _, binding in own:
        assert not confirmation.verify_confirmation(token, **binding)
        assert not confirmation.consume_confirmation(token, **binding)
    assert confirmation.consume_confirmation(other, **other_binding)


@pytest.mark.parametrize("session_id", ["", " owner", "owner ", None])
def test_session_cancel_does_not_guess_a_chat_owner(session_id):
    token, _, binding = _issue()

    assert confirmation.revoke_session_confirmations(session_id=session_id) == 0
    assert confirmation.consume_confirmation(token, **binding)


@pytest.mark.parametrize("session_id", ["", " ", None])
def test_unbound_session_cancel_never_revokes_anonymous_confirmations(session_id):
    anonymous, _, anonymous_binding = _issue(session_id="")
    owned, _, owned_binding = _issue()

    assert confirmation.revoke_session_confirmations(session_id=session_id) == 0
    assert confirmation.consume_confirmation(anonymous, **anonymous_binding)
    assert confirmation.consume_confirmation(owned, **owned_binding)


def test_later_proposal_is_not_revoked_by_an_earlier_cancel():
    first, _, first_binding = _issue()
    assert confirmation.revoke_session_confirmations(session_id="owner") == 1
    later, _, later_binding = _issue()

    assert not confirmation.consume_confirmation(first, **first_binding)
    assert confirmation.consume_confirmation(later, **later_binding)


def test_pending_count_tracks_dismiss_consumption_expiry_and_exact_owner(monkeypatch):
    # A historical "pending" exchange outlives the token; current UI state must use the registry.
    monkeypatch.setattr(confirmation.time, "time", lambda: 100)
    dismissed, _, _ = _issue()
    consumed, _, binding = _issue(service_id="midi_clip")
    expired, _, _ = _issue(service_id="ableton_recipe", ttl_seconds=1)
    other, _, _ = _issue(session_id="other")

    assert confirmation.pending_confirmation_count(session_id="owner") == 3
    assert confirmation.pending_confirmation_count(session_id="other") == 1
    assert confirmation.revoke_confirmation(dismissed, session_id="owner")
    assert confirmation.pending_confirmation_count(session_id="owner") == 2
    assert confirmation.consume_confirmation(consumed, **binding)
    assert confirmation.pending_confirmation_count(session_id="owner") == 1
    assert confirmation.pending_confirmation_count(session_id="owner", now=101) == 0
    assert expired not in confirmation._ISSUED_TOKENS
    assert confirmation.pending_confirmation_count(session_id="other", now=101) == 1
    assert other in confirmation._ISSUED_TOKENS


@pytest.mark.parametrize("session_id", ["", " ", " owner", "owner ", None])
def test_pending_count_does_not_offer_another_or_unbound_chat(session_id):
    _issue()
    _issue(session_id="")

    assert confirmation.pending_confirmation_count(session_id=session_id) == 0


def test_revocation_records_fail_closed_at_capacity_until_expiry(monkeypatch):
    monkeypatch.setattr(confirmation.time, "time", lambda: 100)
    monkeypatch.setattr(confirmation, "MAX_ISSUED_TOKENS", 2, raising=False)
    first, _, binding = _issue(ttl_seconds=1)
    second, _, _ = _issue(ttl_seconds=1)
    assert confirmation.revoke_confirmation(first, session_id="owner")

    with pytest.raises(ValueError, match="confirmation"):
        _issue()
    assert not confirmation.consume_confirmation(first, **binding)
    assert confirmation.verify_confirmation(second, **binding)

    monkeypatch.setattr(confirmation.time, "time", lambda: 101)
    fresh, _, _ = _issue()
    assert set(confirmation._ISSUED_TOKENS) == {fresh}
    assert not confirmation._REVOKED_TOKENS
    assert confirmation.consume_confirmation(fresh, **binding)


def test_consuming_a_token_releases_its_pending_owner_record(monkeypatch):
    monkeypatch.setattr(confirmation, "MAX_ISSUED_TOKENS", 1, raising=False)
    token, _, binding = _issue()
    assert confirmation.consume_confirmation(token, **binding)

    fresh, _, _ = _issue()
    assert set(confirmation._ISSUED_TOKENS) == {fresh}
    assert not confirmation.consume_confirmation(token, **binding)


@pytest.mark.parametrize("expire", [False, True])
def test_revocation_or_expiry_wins_after_preview_but_before_consumption(monkeypatch, expire):
    clock = [100]
    monkeypatch.setattr(confirmation.time, "time", lambda: clock[0])
    token, record, binding = _issue()
    apply_waiting = Event()
    allow_apply = Event()
    lock = Lock()

    class DelayedApplyLock:
        apply_entries = 0

        def __enter__(self):
            if current_thread().name.startswith("confirmation-apply"):
                self.apply_entries += 1
                if self.apply_entries == 2:
                    apply_waiting.set()
                    assert allow_apply.wait(2)
            lock.acquire()

        def __exit__(self, *_):
            lock.release()

    monkeypatch.setattr(confirmation, "_TOKEN_LOCK", DelayedApplyLock())
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="confirmation-apply") as pool:
        applied = pool.submit(confirmation.consume_confirmation, token, **binding)
        try:
            assert apply_waiting.wait(2)
            if expire:
                clock[0] = record["expires_at"]
            else:
                assert confirmation.revoke_confirmation(token, session_id="owner")
        finally:
            allow_apply.set()
        assert not applied.result(timeout=2)


def test_dismiss_waits_for_confirmation_consumption_to_finish(monkeypatch):
    token, _, binding = _issue()
    consuming = Event()
    finish_consume = Event()
    revoke_waiting = Event()
    lock = Lock()

    class PausedConsumptionSet(set):
        def add(self, value):
            consuming.set()
            assert finish_consume.wait(2)
            super().add(value)

    class TrackedLock:
        def __enter__(self):
            if current_thread().name.startswith("confirmation-revoke"):
                revoke_waiting.set()
            lock.acquire()

        def __exit__(self, *_):
            lock.release()

    monkeypatch.setattr(confirmation, "_TOKEN_LOCK", TrackedLock())
    monkeypatch.setattr(confirmation, "_USED_TOKENS", PausedConsumptionSet())
    with ThreadPoolExecutor(max_workers=1) as apply_pool, ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="confirmation-revoke",
    ) as revoke_pool:
        applied = apply_pool.submit(confirmation.consume_confirmation, token, **binding)
        try:
            assert consuming.wait(2)
            revoked = revoke_pool.submit(confirmation.revoke_confirmation, token, session_id="owner")
            assert revoke_waiting.wait(2)
            assert not revoked.done()
        finally:
            finish_consume.set()
        assert applied.result(timeout=2)
        assert not revoked.result(timeout=2)


def test_pending_count_waits_for_confirmation_consumption_to_finish(monkeypatch):
    token, _, binding = _issue()
    consuming = Event()
    finish_consume = Event()
    observing = Event()
    lock = Lock()

    class PausedConsumptionSet(set):
        def add(self, value):
            consuming.set()
            assert finish_consume.wait(2)
            super().add(value)

    class TrackedLock:
        def __enter__(self):
            if current_thread().name.startswith("confirmation-observe"):
                observing.set()
            lock.acquire()

        def __exit__(self, *_):
            lock.release()

    monkeypatch.setattr(confirmation, "_TOKEN_LOCK", TrackedLock())
    monkeypatch.setattr(confirmation, "_USED_TOKENS", PausedConsumptionSet())
    with ThreadPoolExecutor(max_workers=1) as apply_pool, ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="confirmation-observe",
    ) as observe_pool:
        applied = apply_pool.submit(confirmation.consume_confirmation, token, **binding)
        try:
            assert consuming.wait(2)
            pending = observe_pool.submit(confirmation.pending_confirmation_count, session_id="owner")
            assert observing.wait(2)
            assert not pending.done()
        finally:
            finish_consume.set()
        assert applied.result(timeout=2)
        assert pending.result(timeout=2) == 0


@pytest.mark.parametrize("cancel_session", [False, True])
def test_held_transport_proposal_cannot_write_after_revocation(monkeypatch, cancel_session):
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    held = deepcopy(service.propose_transport_action("transport_play", session_id="owner")["proposal"])
    token = held["confirmation_token"]
    writes = []
    monkeypatch.setattr(fake, "start_playback", lambda: writes.append("transport_play") or True)
    before = fake.query_session_state()

    if cancel_session:
        assert confirmation.revoke_session_confirmations(session_id="owner") == 1
    else:
        assert confirmation.revoke_confirmation(token, session_id="owner")
    assert service.proposal_for_token(token) is not None
    result = service.execute(held, confirm_token=token, session_id="owner")

    assert not result["ok"]
    assert "confirmation token" in result["error"]
    assert writes == []
    assert fake.writes == []
    assert fake.query_session_state() == before


def test_held_recipe_and_its_child_tokens_cannot_write_after_session_cancel():
    fake = FakeLiveBackend()
    service = LiveRecipeService(LiveActionService(fake))
    held = deepcopy(service.propose_recipe([
        {"action": "set_pan", "track_index": 5, "value": -1.0},
        {"action": "set_mute", "track_index": 5, "value": True},
    ], session_id="owner", reason="Producer requested pan and mute.")["proposal"])
    before = fake.query_session_state()

    assert confirmation.revoke_session_confirmations(session_id="owner") == 1
    result = service.execute_recipe(held, confirm_token=held["confirmation_token"], session_id="owner")

    assert not result["ok"]
    assert "confirmation token" in result["error"]
    assert fake.writes == []
    assert fake.query_session_state() == before


@pytest.mark.parametrize("dismiss", [True, False])
def test_recipe_has_one_pending_confirmation_and_retires_hidden_child_tokens(monkeypatch, dismiss):
    # Recipe construction strips child signatures; they must not leave invisible pending actions.
    fake = FakeLiveBackend()
    actions = LiveActionService(fake)
    ordinary = deepcopy(actions.propose_track_action("set_mute", track_index=4, value=True, session_id="ordinary")["proposal"])
    children = []
    propose = actions.propose_track_action

    def capture_child(*args, **kwargs):
        result = propose(*args, **kwargs)
        children.append(deepcopy(result["proposal"]))
        return result

    monkeypatch.setattr(actions, "propose_track_action", capture_child)
    recipes = LiveRecipeService(actions)
    recipe = deepcopy(recipes.propose_recipe([
        {"action": "set_pan", "track_index": 5, "value": -1.0},
        {"action": "set_mute", "track_index": 5, "value": True},
    ], session_id="owner", reason="Producer requested pan and mute.")["proposal"])
    assert confirmation.pending_confirmation_count(session_id="owner") == 1
    assert confirmation.pending_confirmation_count(session_id="ordinary") == 1
    before = fake.query_session_state()
    for child in children:
        result = actions.execute(child, confirm_token=child["confirmation_token"], session_id="owner")
        assert not result["ok"]
    assert fake.writes == []
    assert fake.query_session_state() == before

    if dismiss:
        assert confirmation.revoke_confirmation(recipe["confirmation_token"], session_id="owner")
    result = recipes.execute_recipe(recipe, confirm_token=recipe["confirmation_token"], session_id="owner")
    assert result["ok"] is not dismiss
    assert confirmation.pending_confirmation_count(session_id="owner") == 0
    assert confirmation.pending_confirmation_count(session_id="ordinary") == 1
    if dismiss:
        assert fake.writes == []
        assert fake.query_session_state() == before

    assert actions.execute(ordinary, confirm_token=ordinary["confirmation_token"], session_id="ordinary")["ok"]
    assert confirmation.pending_confirmation_count(session_id="ordinary") == 0


def test_dismiss_does_not_claim_to_stop_an_action_that_consumed_its_token(monkeypatch):
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    proposal = service.propose_transport_action("transport_play", session_id="owner")["proposal"]
    token = proposal["confirmation_token"]
    write_started = Event()
    finish_write = Event()
    start_playback = fake.start_playback

    def blocked_write():
        write_started.set()
        assert finish_write.wait(2)
        return start_playback()

    monkeypatch.setattr(fake, "start_playback", blocked_write)
    with ThreadPoolExecutor(max_workers=1) as pool:
        applied = pool.submit(service.execute, proposal, confirm_token=token, session_id="owner")
        try:
            assert write_started.wait(2)
            assert not confirmation.revoke_confirmation(token, session_id="owner")
            assert confirmation.revoke_session_confirmations(session_id="owner") == 0
        finally:
            finish_write.set()
        assert applied.result(timeout=2)["ok"]
    assert fake.query_session_state()["is_playing"] is True
