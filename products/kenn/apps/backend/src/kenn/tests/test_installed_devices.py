"""Advice can name the devices the producer actually has, read from disk and the last session snapshot."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from kenn.core import chat_context, installed_devices


def make_mac(tmp_path):
    apps = tmp_path / "Applications"
    resources = apps / "Ableton Live 12 Suite.app" / "Contents" / "App-Resources"
    for name in ("EQ Eight.adv", "Channel EQ.adv", "Compressor.adv", "Glue Compressor.adv", "Limiter.adv", "Hybrid Reverb.amxd",
                 "Echo.amxd", "Saturator.adv", "Ableton Folder Info", "Max LFO.amxd"):
        path = resources / "Builtin" / "Devices" / "Audio Effects" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    home = tmp_path / "home"
    prefs = home / "Library" / "Preferences" / "Ableton" / "Live 12.1.1"
    prefs.mkdir(parents=True)
    library_root = tmp_path / "Music" / "Ableton"
    root = ET.Element("Ableton")
    ET.SubElement(root, "ProjectPath", Value=str(library_root))
    ET.ElementTree(root).write(prefs / "Library.cfg")
    racks = library_root / "User Library" / "Presets" / "Audio Effects" / "Audio Effect Rack"
    racks.mkdir(parents=True)
    (racks / "Vocal EQ Chain.adg").touch()
    (racks / "Wide Pad.adg").touch()
    (library_root / "Factory Packs" / "Drum Booth").mkdir(parents=True)
    plugins = tmp_path / "Library" / "Audio" / "Plug-Ins" / "VST3"
    plugins.mkdir(parents=True)
    (plugins / "FabFilter Pro-Q 3.vst3").mkdir()
    (plugins / "Valhalla Room.vst3").mkdir()
    (plugins / "Serum.vst3").mkdir()
    au = home / "Library" / "Audio" / "Plug-Ins" / "Components"
    au.mkdir(parents=True)
    (au / "Soothe2.component").mkdir()
    return {"applications": apps, "home": home, "system_root": tmp_path}


def test_the_scan_reads_builtins_racks_packs_and_plugins_by_name(tmp_path) -> None:
    found = installed_devices.scan(**make_mac(tmp_path))
    assert found["live"] == "Ableton Live 12 Suite"
    assert "EQ Eight" in found["builtin"] and "Max LFO" not in found["builtin"] and "Ableton Folder Info" not in found["builtin"]
    assert found["racks"] == ["Vocal EQ Chain", "Wide Pad"]
    assert found["packs"] == ["Drum Booth"]
    assert {(p["name"], p["format"]) for p in found["plugins"]} == {
        ("FabFilter Pro-Q 3", "VST3"), ("Valhalla Room", "VST3"), ("Serum", "VST3"), ("Soothe2", "Audio Unit")}


def test_a_mac_without_live_gives_an_empty_inventory_and_no_line(tmp_path) -> None:
    found = installed_devices.scan(applications=tmp_path / "none", home=tmp_path / "h", system_root=tmp_path / "root")
    assert found["builtin"] == [] and found["plugins"] == []
    assert installed_devices.your_set_note("how do I EQ a vocal?", found) is None


def test_an_eq_question_names_the_eqs_the_producer_has(tmp_path) -> None:
    installed = installed_devices.scan(**make_mac(tmp_path))
    session = {"tracks": [{"name": "Bass", "devices": [{"name": "EQ Eight"}]}, {"name": "Kick", "devices": [{"name": "Compressor"}]}]}
    note = installed_devices.your_set_note("How do I EQ the bass?", installed, session)
    assert note["categories"] == ["eq"] and note["evidence_class"] == "observed_session_fact"
    assert note["line"] == ("In your Live, built into Ableton Live 12 Suite: Channel EQ, EQ Eight; "
                            "plug-ins whose names match: FabFilter Pro-Q 3 (VST3); your saved racks: Vocal EQ Chain; "
                            "already on your tracks: EQ Eight on Bass.")


def test_a_question_about_no_device_family_gets_no_line(tmp_path) -> None:
    installed = installed_devices.scan(**make_mac(tmp_path))
    assert installed_devices.your_set_note("What is a good tempo for house?", installed) is None
    assert installed_devices.your_set_note("How loud should a kick be?", installed) is None


def test_two_families_in_one_question_name_both(tmp_path) -> None:
    installed = installed_devices.scan(**make_mac(tmp_path))
    note = installed_devices.your_set_note("Compressor then reverb on vocals?", installed)
    assert note["categories"] == ["compressor", "reverb"]
    assert "Compressor" in note["builtin"] and "Hybrid Reverb" in note["builtin"] and "Valhalla Room (VST3)" in note["plugins"]


def test_a_long_list_is_capped() -> None:
    installed = {"live": "Live", "builtin": [], "plugins": [{"name": f"Comp {n}", "format": "VST3"} for n in range(9)]}
    assert "and 3 more" in installed_devices.your_set_note("compressor?", installed)["line"]


def test_the_answer_gets_the_line_only_when_it_found_a_source(tmp_path, monkeypatch) -> None:
    installed = installed_devices.scan(**make_mac(tmp_path))
    monkeypatch.setattr(installed_devices, "inventory", lambda **_: installed)
    monkeypatch.setattr("kenn.mixing_doctor.get_latest_session_state", lambda: {"status": "unknown", "tracks": []})
    found = chat_context.attach_your_set({"found": True, "answer": "Use a high-pass."}, "EQ the bass?")
    assert found["answer"].startswith("Use a high-pass.\n\nIn your Live, built into") and found["your_set"]["categories"] == ["eq"]
    unchanged = {"found": False, "answer": "I don't know."}
    assert chat_context.attach_your_set(unchanged, "EQ the bass?") == unchanged


def test_a_failing_scan_never_costs_the_answer(monkeypatch) -> None:
    def boom(**_):
        raise OSError("permission denied")

    monkeypatch.setattr(installed_devices, "inventory", boom)
    result = {"found": True, "answer": "Use a high-pass."}
    assert chat_context.attach_your_set(result, "EQ the bass?") == result
