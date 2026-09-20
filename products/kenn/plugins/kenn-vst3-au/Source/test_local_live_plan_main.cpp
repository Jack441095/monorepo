#include "LocalLivePlan.h"

#include "TestCheck.h"
#include <iostream>

int main()
{
    kenn::LocalLiveTopology topology;
    topology.connected = true;
    topology.tracks = {
        { 0, "1-MIDI", {} },
        { 1, "2-MIDI", {} },
        { 2, "3-Audio", {} },
        { 3, "4-Audio", { { 0, "Glue Compressor" }, { 1, "Saturator" } } },
    };

    const auto insert = kenn::makeLocalLivePlan(kenn::parseLocalCommand("Add EQ on track 4"), topology);
    KENN_TEST_CHECK(insert.ready);
    KENN_TEST_CHECK(insert.action == "insert_device");
    KENN_TEST_CHECK(insert.trackIndex == 3 && insert.trackName == "4-Audio");
    KENN_TEST_CHECK(insert.deviceName == "EQ Eight" && insert.insertionIndex == 2);
    KENN_TEST_CHECK(insert.beforeDevices.size() == 2 && insert.afterDevices.size() == 3);
    KENN_TEST_CHECK(insert.beforeDeviceFingerprint.size() == 64);

    const auto duplicate = kenn::makeLocalLivePlan(kenn::parseLocalCommand("Add saturator on track 4"), topology);
    KENN_TEST_CHECK(!duplicate.ready && duplicate.clarification.find("already contains") != std::string::npos);

    const auto unsupported = kenn::makeLocalLivePlan(kenn::parseLocalCommand("Mute track 4"), topology);
    KENN_TEST_CHECK(!unsupported.ready && unsupported.clarification.find("companion-owned") != std::string::npos);

    // Separate fixture: the insertion tests above deliberately model a track
    // that does not yet have an EQ Eight (so insertion is possible and a
    // duplicate Saturator request is rejected). The parameter-plan tests need
    // an exact existing EQ Eight device to resolve "1 Gain A" against, so
    // they use their own topology rather than reusing the insertion one.
    kenn::LocalLiveTopology parameterTopology;
    parameterTopology.connected = true;
    parameterTopology.tracks = {
        { 0, "1-MIDI", {} },
        { 1, "2-MIDI", {} },
        { 2, "3-Audio", {} },
        { 3, "4-Audio", { { 0, "EQ Eight" } } },
    };

    kenn::LocalLiveParameterSnapshot parameters;
    parameters.connected = true;
    parameters.trackIndex = 3;
    parameters.deviceIndex = 0;
    parameters.deviceName = "EQ Eight";
    parameters.parameters = {
        { 0, "Output", 0.0, -1.0, 1.0, true },
        { 1, "1 Gain A", -3.0, -12.0, 12.0, true },
    };
    const auto parameterIntent = kenn::parseLocalCommand("Set EQ Eight 1 Gain A to -6 dB on track 4");
    KENN_TEST_CHECK(parameterIntent.recognized && parameterIntent.action == "set_device_parameter");
    KENN_TEST_CHECK(parameterIntent.parameterName == "1 gain a" && !parameterIntent.relative);
    const auto parameterPlan = kenn::makeLocalLiveParameterPlan(parameterIntent, parameterTopology, parameters);
    KENN_TEST_CHECK(parameterPlan.ready);
    KENN_TEST_CHECK(parameterPlan.parameterIndex == 1 && parameterPlan.parameterName == "1 Gain A");
    KENN_TEST_CHECK(parameterPlan.beforeValue == -3.0 && parameterPlan.afterValue == -6.0);
    KENN_TEST_CHECK(parameterPlan.parameterMinimum == -12.0 && parameterPlan.parameterMaximum == 12.0);

    const auto relativeIntent = kenn::parseLocalCommand("Reduce EQ Eight 1 Gain A by 3 dB on track 4");
    const auto relativePlan = kenn::makeLocalLiveParameterPlan(relativeIntent, parameterTopology, parameters);
    KENN_TEST_CHECK(relativePlan.ready && relativePlan.afterValue == -6.0);

    const auto outOfRange = kenn::parseLocalCommand("Set EQ Eight 1 Gain A to -30 dB on track 4");
    const auto rejectedRange = kenn::makeLocalLiveParameterPlan(outOfRange, parameterTopology, parameters);
    KENN_TEST_CHECK(!rejectedRange.ready && rejectedRange.clarification.find("range") != std::string::npos);

    std::cout << "Local C++ Live plan: insertion identity, parameter range/relative planning, duplicate guard, and companion ownership gate passed\n";
    return 0;
}
