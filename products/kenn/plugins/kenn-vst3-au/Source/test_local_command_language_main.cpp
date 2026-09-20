#include "LocalCommandLanguage.h"

#include "TestCheck.h"
#include <chrono>
#include <iostream>

int main()
{
    using kenn::parseLocalCommand;

    const auto mute = parseLocalCommand("Mute channel 2");
    KENN_TEST_CHECK(mute.recognized && mute.action == "set_mute" && mute.trackNumber == 2 && mute.value == 1.0);

    const auto pan = parseLocalCommand("Pan track 4 20% right");
    KENN_TEST_CHECK(pan.recognized && pan.action == "set_pan" && pan.trackNumber == 4 && pan.value == 0.2);

    const auto volume = parseLocalCommand("Set the volume on track 4 to -6 dB");
    KENN_TEST_CHECK(volume.recognized && volume.action == "set_volume" && volume.trackNumber == 4);
    KENN_TEST_CHECK(volume.value > 0.50 && volume.value < 0.51);

    const auto insert = parseLocalCommand("Add EQ on track 4");
    KENN_TEST_CHECK(insert.recognized && insert.action == "insert_device" && insert.deviceName == "EQ Eight" && insert.trackNumber == 4);

    const auto spokenTrack = parseLocalCommand("Add EQ Eight on track four");
    KENN_TEST_CHECK(spokenTrack.recognized && spokenTrack.action == "insert_device" && spokenTrack.deviceName == "EQ Eight" && spokenTrack.trackNumber == 4);

    const auto ordinalTrack = parseLocalCommand("Mute track fourth");
    KENN_TEST_CHECK(ordinalTrack.recognized && ordinalTrack.action == "set_mute" && ordinalTrack.trackNumber == 4);
    const auto ordinalBeforeTrack = parseLocalCommand("Mute the fourth track");
    KENN_TEST_CHECK(ordinalBeforeTrack.recognized && ordinalBeforeTrack.action == "set_mute" && ordinalBeforeTrack.trackNumber == 4);

    // Structural track creation is recognized for companion handoff only;
    // native C++ planning remains read-only and companion-owned.
    const auto midiTrack = parseLocalCommand("Create a new MIDI track named Hi Hats");
    KENN_TEST_CHECK(midiTrack.recognized && midiTrack.action == "create_midi_track"
                    && midiTrack.trackNumber == 0 && midiTrack.newTrackName == "hi hats");
    const auto audioTrack = parseLocalCommand("make audio track called Vox Print");
    KENN_TEST_CHECK(audioTrack.recognized && audioTrack.action == "create_audio_track"
                    && audioTrack.newTrackName == "vox print");

    // Compressor/Hybrid Reverb/Echo were qualified into
    // DEVICE_INSERTION_ALLOWLIST after this parser's device table was first
    // written; these prove the table was kept in sync, and that "glue
    // compressor" still resolves to the distinct device rather than being
    // shadowed by the newly-added bare "compressor" alternative.
    const auto insertCompressor = parseLocalCommand("Add Compressor on track 2");
    KENN_TEST_CHECK(insertCompressor.recognized && insertCompressor.deviceName == "Compressor" && insertCompressor.trackNumber == 2);

    const auto insertHybridReverb = parseLocalCommand("Add Hybrid Reverb on track 3");
    KENN_TEST_CHECK(insertHybridReverb.recognized && insertHybridReverb.deviceName == "Hybrid Reverb" && insertHybridReverb.trackNumber == 3);

    const auto insertEcho = parseLocalCommand("Add Echo on track 3");
    KENN_TEST_CHECK(insertEcho.recognized && insertEcho.deviceName == "Echo" && insertEcho.trackNumber == 3);

    const auto insertGlue = parseLocalCommand("Add Glue Compressor on track 4");
    KENN_TEST_CHECK(insertGlue.recognized && insertGlue.deviceName == "Glue Compressor" && insertGlue.trackNumber == 4);

    const auto named = parseLocalCommand("Mute the Vocal");
    KENN_TEST_CHECK(!named.recognized && !named.clarification.empty());

    const auto destructive = parseLocalCommand("Delete track 2");
    KENN_TEST_CHECK(!destructive.recognized && destructive.clarification.find("disabled") != std::string::npos);

    const auto started = std::chrono::steady_clock::now();
    for (int i = 0; i < 10000; ++i) (void) parseLocalCommand("Pan track 4 20% right");
    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - started).count();
    std::cout << "Local C++ parser: 15 contract cases passed; 10,000 parses in " << elapsed << " us\n";
    return 0;
}
