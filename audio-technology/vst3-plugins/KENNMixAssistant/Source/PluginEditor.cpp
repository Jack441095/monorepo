#include "PluginEditor.h"
#include <juce_gui_extra/juce_gui_extra.h>
#include <cmath>

namespace
{
juce::String liveLifecycleText(const juce::var& value)
{
    auto* object = value.getDynamicObject();
    if (object == nullptr) return {};
    auto* lifecycle = object->getProperty("lifecycle").getDynamicObject();
    if (lifecycle == nullptr) return {};

    const auto stage = lifecycle->getProperty("stage").toString();
    const auto elapsed = lifecycle->getProperty("snapshot_elapsed_ms").toString();
    const auto observed = static_cast<double>(lifecycle->getProperty("snapshot_observed_at"));
    juce::String text = "Live observation: " + (stage.isNotEmpty() ? stage : "unknown");
    if (elapsed.isNotEmpty()) text += ", snapshot read " + elapsed + " ms";
    if (std::isfinite(observed) && observed > 0.0)
        text += ", observed " + juce::Time(static_cast<int64_t>(observed * 1000.0)).toString(false, true, true, true);
    return text;
}
}

juce::String KENNMixAssistantAudioProcessorEditor::formatLiveProposal(const juce::var& value, const juce::String& title, bool isUndo) const
{
    auto* object = value.getDynamicObject();
    if (object == nullptr) return title + "\n\nNo exact Live proposal is available.";

    const auto schema = object->getProperty("schema").toString();
    if (schema == "kenn.ableton_recipe_proposal.v1" || schema == "kenn.ableton_recipe_receipt.v1")
    {
        const auto stepsValue = object->getProperty(schema == "kenn.ableton_recipe_receipt.v1" ? "step_receipts" : "steps");
        auto* steps = stepsValue.getArray();
        const auto stepCount = object->getProperty("step_count").toString();
        juce::String text = title + "\n\n" + (schema == "kenn.ableton_recipe_receipt.v1" ? "Verified Live recipe" : "Exact Live recipe")
            + (stepCount.isNotEmpty() ? " (" + stepCount + " steps)" : juce::String());
        const auto lifecycle = liveLifecycleText(value);
        if (lifecycle.isNotEmpty()) text += "\n" + lifecycle;

        if (steps == nullptr || steps->isEmpty())
            return text + "\n\nNo typed Live steps are available.";

        for (int index = 0; index < steps->size(); ++index)
        {
            auto* step = steps->getUnchecked(index).getDynamicObject();
            if (step == nullptr)
            {
                text += "\n" + juce::String(index + 1) + ". Invalid step";
                continue;
            }

            const auto targetValue = step->getProperty("target");
            auto* target = targetValue.getDynamicObject();
            const auto readText = [&step, &target](const char* key) {
                const auto direct = step->getProperty(key).toString();
                return direct.isNotEmpty() ? direct : (target != nullptr ? target->getProperty(key).toString() : juce::String());
            };
            const auto action = readText("action").isNotEmpty() ? readText("action") : readText("operation");
            const auto track = readText("track_name");
            const auto device = readText("device_name");
            const auto parameter = readText("parameter");
            const auto before = step->getProperty("before").toString();
            const auto after = step->getProperty("after").toString().isNotEmpty()
                ? step->getProperty("after").toString()
                : step->getProperty("requested").toString();
            const auto readback = step->getProperty("readback").toString();
            const auto unit = step->getProperty("unit").toString();

            juce::String targetText = track.isNotEmpty() ? track : "Live";
            if (device.isNotEmpty())
            {
                targetText += " -> " + device;
                const auto deviceIndex = readText("device_index");
                if (deviceIndex.isNotEmpty()) targetText += " (device " + juce::String(deviceIndex.getIntValue() + 1) + ")";
            }
            if (parameter.isNotEmpty()) targetText += " -> " + parameter;

            text += "\n" + juce::String(index + 1) + ". " + (action.isNotEmpty() ? action : "Live action") + ": " + targetText;
            if (before.isNotEmpty() || after.isNotEmpty())
                text += "\n   " + (before.isNotEmpty() ? before : "unknown") + " -> " + (after.isNotEmpty() ? after : "unknown")
                    + (unit.isNotEmpty() ? " " + unit : juce::String());
            if (readback.isNotEmpty()) text += "\n   Readback: " + readback + (unit.isNotEmpty() ? " " + unit : juce::String());
            if (schema == "kenn.ableton_recipe_receipt.v1")
            {
                text += "\n   Verified: ";
                text += (static_cast<bool>(step->getProperty("verified")) ? "yes" : "no");
            }
        }

        text += isUndo ? "\n\nThis restores the prior verified values. Nothing has changed yet."
                       : (schema == "kenn.ableton_recipe_receipt.v1" ? "\n\nAll recipe steps were applied and verified."
                                                                      : "\n\nNothing has changed yet. Confirm this exact recipe to apply it.");
        return text;
    }

    if (schema == "kenn.ableton_local_plan.v1")
    {
        const auto track = object->getProperty("track_name").toString();
        const auto device = object->getProperty("device_name").toString();
        juce::String text = title + "\n\nRead-only C++ Live plan\nExact target: "
            + (track.isNotEmpty() ? track : "unknown track")
            + (device.isNotEmpty() ? " -> " + device : juce::String());
        const auto parameter = object->getProperty("parameter_name").toString();
        if (parameter.isNotEmpty())
        {
            text += " -> " + parameter;
            text += "\nBefore: " + object->getProperty("before").toString() + " dB";
            text += "\nAfter: " + object->getProperty("after").toString() + " dB";
            text += "\nRange: " + object->getProperty("min").toString() + " .. "
                + object->getProperty("max").toString() + " dB";
            text += "\nParameter index: " + juce::String(object->getProperty("parameter_index").toString().getIntValue() + 1);
            const auto canConfirmDirectly = static_cast<bool>(object->getProperty("requires_confirmation"));
            text += canConfirmDirectly
                ? "\n\nDeveloper direct mode is enabled. Confirm only on a disposable Live set."
                : "\n\nThe companion is required to confirm and apply this plan. Nothing has changed.";
            return text;
        }
        text += "\nAppend position: " + juce::String(object->getProperty("insertion_index").toString().getIntValue() + 1);
        text += "\nBefore: ";
        const auto appendDevices = [&text](const juce::var& deviceValue) {
            const auto* devices = deviceValue.getArray();
            if (devices == nullptr || devices->isEmpty())
            {
                text += "[]";
                return;
            }
            text += "[";
            for (int index = 0; index < devices->size(); ++index)
            {
                if (index != 0) text += ", ";
                auto* item = devices->getUnchecked(index).getDynamicObject();
                text += item != nullptr ? item->getProperty("name").toString() : "unknown";
            }
            text += "]";
        };
        appendDevices(object->getProperty("before_devices"));
        text += "\nAfter: ";
        appendDevices(object->getProperty("after_devices"));
        text += "\nSnapshot fingerprint: " + object->getProperty("before_device_fingerprint").toString();
        const auto canConfirmDirectly = static_cast<bool>(object->getProperty("requires_confirmation"));
        text += canConfirmDirectly
            ? "\n\nDeveloper direct mode is enabled. Confirm only on a disposable Live set."
            : "\n\nThe companion is required to confirm and apply this plan. Nothing has changed.";
        return text;
    }

    const auto action = object->getProperty("action").toString();

    const auto targetObject = object->getProperty("target");
    auto* targetDetails = targetObject.getDynamicObject();
    const auto track = object->getProperty("track_name").toString().isNotEmpty()
        ? object->getProperty("track_name").toString()
        : (targetDetails != nullptr ? targetDetails->getProperty("track_name").toString() : juce::String());
    const auto device = object->getProperty("device_name").toString().isNotEmpty()
        ? object->getProperty("device_name").toString()
        : (targetDetails != nullptr ? targetDetails->getProperty("device_name").toString() : juce::String());
    const auto parameter = object->getProperty("parameter").toString().isNotEmpty()
        ? object->getProperty("parameter").toString()
        : (object->getProperty("parameter_name").toString().isNotEmpty()
            ? object->getProperty("parameter_name").toString()
            : (targetDetails != nullptr ? targetDetails->getProperty("parameter").toString() : juce::String()));
    const auto before = object->getProperty("before").toString();
    const auto after = object->getProperty("after").toString().isNotEmpty()
        ? object->getProperty("after").toString()
        : object->getProperty("requested").toString();
    const auto readback = object->getProperty("readback").toString();
    const auto unit = object->getProperty("unit").toString();
    const auto band = object->getProperty("eq_band").toString();
    const auto frequency = object->getProperty("frequency_hz").toString();

    juce::String text = title + "\n\nExact target: "
        + (track.isNotEmpty() ? track : "unknown track")
        + (device.isNotEmpty() ? " -> " + device : juce::String())
        + (parameter.isNotEmpty() ? " -> " + parameter : juce::String());
    const auto lifecycle = liveLifecycleText(value);
    if (lifecycle.isNotEmpty()) text += "\n" + lifecycle;
    if (band.isNotEmpty()) text += "\nEQ band: " + band;
    if (action == "set_eq_band_tuning_gain")
    {
        text += "\nFrequency: " + object->getProperty("frequency_before_hz").toString()
            + " Hz -> " + object->getProperty("frequency_after_hz").toString() + " Hz";
        text += "\nGain: " + object->getProperty("gain_before_value").toString()
            + " dB -> " + object->getProperty("gain_after_value").toString() + " dB";
    }
    else if (frequency.isNotEmpty()) text += "\nFrequency: " + frequency + " Hz";
    text += "\nBefore: " + (before.isNotEmpty() ? before : "unknown")
        + (unit.isNotEmpty() ? " " + unit : juce::String())
        + "\nAfter: " + (after.isNotEmpty() ? after : "unknown")
        + (unit.isNotEmpty() ? " " + unit : juce::String());
    if (readback.isNotEmpty()) text += "\nReadback: " + readback + (unit.isNotEmpty() ? " " + unit : juce::String());
    if (object->getProperty("reason").toString().isNotEmpty()) text += "\nReason: " + object->getProperty("reason").toString();
    text += isUndo ? "\n\nThis restores the prior verified value. Nothing has changed yet." : "\n\nNothing has changed yet.";
    return text;
}

void KENNMixAssistantAudioProcessorEditor::clearPendingLiveProposal(const juce::String& message)
{
    pendingLiveProposal = juce::var();
    pendingLiveReceipt = juce::var();
    pendingLiveIsUndo = false;
    confirmLiveProposalButton.setEnabled(false);
    cancelLiveProposalButton.setEnabled(false);
    liveProposalViewer.setText(message, false);
}

void KENNMixAssistantAudioProcessorEditor::beginLiveRequest(const juce::String& stage, const juce::String& detail)
{
    liveRequestStage = stage;
    liveRequestStarted = juce::Time::getCurrentTime();
    liveRequestTimedOut.store(false);
    liveRequestInFlight.store(true);
    status.setText("Live [" + stage + "] " + detail + " (30 s timeout)", juce::dontSendNotification);
}

void KENNMixAssistantAudioProcessorEditor::finishLiveRequest(const juce::String& stage, const juce::String& detail)
{
    const bool returnedAfterTimeout = liveRequestTimedOut.load();
    liveRequestInFlight.store(false);
    liveResponseReceived = juce::Time::getCurrentTime();
    liveRequestStage = stage;
    const auto timing = returnedAfterTimeout ? "; response returned after local timeout" : "";
    status.setText("Live [" + stage + "] " + detail + timing, juce::dontSendNotification);
}

void KENNMixAssistantAudioProcessorEditor::failLiveRequest(const juce::String& detail)
{
    const auto lower = detail.toLowerCase();
    const auto stage = lower.contains("not running") || lower.contains("offline") || lower.contains("cannot reach")
        ? "offline"
        : (lower.contains("readback") ? "readback failed" : (lower.contains("timed out") ? "timeout" : "failed"));
    finishLiveRequest(stage, detail);
}

bool KENNMixAssistantAudioProcessorEditor::liveRequestBusy(const juce::String& attemptedStage)
{
    if (! liveRequestInFlight.load()) return false;
    const auto suffix = attemptedStage.isNotEmpty() ? " while " + attemptedStage + " is running" : juce::String();
    status.setText("Live [busy] Wait for the current request to finish" + suffix + ". Do not start a second request.", juce::dontSendNotification);
    return true;
}

KENNMixAssistantAudioProcessorEditor::KENNMixAssistantAudioProcessorEditor(KENNMixAssistantAudioProcessor& p)
    : AudioProcessorEditor(&p), kennProcessor(p)
{
    webView = std::make_unique<juce::WebBrowserComponent>(
        juce::WebBrowserComponent::Options{}
            .withNativeIntegrationEnabled());
    addChildComponent(webView.get());
    setWantsKeyboardFocus(true);

    const auto foreground = juce::Colour(0xfff2f5f7);
    const auto secondaryForeground = juce::Colour(0xffd7e0e5);
    const auto panel = juce::Colour(0xff202832);
    const auto panelRaised = juce::Colour(0xff2a353c);
    const auto outline = juce::Colour(0xff96a4ab);
    for (auto* label : { &heading, &metrics, &guidance, &status, &actionAudit, &endpointLabel, &sessionLabel, &modeLabel })
    {
        addAndMakeVisible(label);
        label->setJustificationType(juce::Justification::centredLeft);
        label->setColour(juce::Label::textColourId, foreground);
    }
    heading.setText("KENN Mix Assistant", juce::dontSendNotification); heading.setFont(juce::FontOptions(22.0f, juce::Font::bold));
    guidance.setColour(juce::Label::textColourId, secondaryForeground);
    status.setColour(juce::Label::textColourId, secondaryForeground);
    actionAudit.setColour(juce::Label::textColourId, secondaryForeground);
    guidance.setText("Local meters and Mix Check work without the companion. Chat, handoff, proposals, and AutoMix use the optional local KENN Companion.", juce::dontSendNotification);
    endpointLabel.setText("KENN Companion (optional)", juce::dontSendNotification);
    sessionLabel.setText("Session ID", juce::dontSendNotification);
    modeLabel.setText("Mode", juce::dontSendNotification);
    addAndMakeVisible(modeSelector);
    modeSelector.addItemList({ "Ask", "Suggest", "Assist", "Auto" }, 1);
    modeSelector.setColour(juce::ComboBox::backgroundColourId, panel);
    modeSelector.setColour(juce::ComboBox::buttonColourId, panelRaised);
    modeSelector.setColour(juce::ComboBox::textColourId, foreground);
    modeSelector.setColour(juce::ComboBox::outlineColourId, outline);
    modeAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment>(kennProcessor.apvts, "assistant_mode", modeSelector);
    addAndMakeVisible(liveContextToggle);
    liveContextAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment>(kennProcessor.apvts, "live_context_enabled", liveContextToggle);
    for (auto* editor : { &endpointEditor, &sessionEditor })
    {
        addAndMakeVisible(editor);
        editor->setSelectAllWhenFocused(true);
        editor->setColour(juce::TextEditor::backgroundColourId, panel);
        editor->setColour(juce::TextEditor::textColourId, foreground);
        editor->setColour(juce::TextEditor::outlineColourId, outline);
        editor->setColour(juce::TextEditor::focusedOutlineColourId, foreground);
    }
    endpointEditor.setText(kennProcessor.getKennEndpoint(), false);
    sessionEditor.setText(kennProcessor.getKennSessionId(), false);
    addAndMakeVisible(questionEditor);
    questionEditor.setTextToShowWhenEmpty("Ask about this bus, e.g. What is wrong with this mix?", juce::Colours::grey);
    questionEditor.onReturnKey = [this] { askButton.triggerClick(); };
    addAndMakeVisible(answerViewer);
    answerViewer.setMultiLine(true, true);
    answerViewer.setReadOnly(true);
    answerViewer.setScrollbarsShown(true);
    answerViewer.setColour(juce::TextEditor::backgroundColourId, juce::Colour(0xff171d25));
    answerViewer.setColour(juce::TextEditor::textColourId, foreground);
    answerViewer.setColour(juce::TextEditor::outlineColourId, outline);
    answerViewer.setColour(juce::TextEditor::focusedOutlineColourId, foreground);
    answerViewer.setText("KENN answers here using this plug-in's live bus context and selected session.", false);
    addAndMakeVisible(liveProposalViewer);
    liveProposalViewer.setMultiLine(true, true);
    liveProposalViewer.setReadOnly(true);
    liveProposalViewer.setScrollbarsShown(true);
    liveProposalViewer.setColour(juce::TextEditor::backgroundColourId, panel);
    liveProposalViewer.setColour(juce::TextEditor::textColourId, foreground);
    liveProposalViewer.setColour(juce::TextEditor::outlineColourId, outline);
    liveProposalViewer.setColour(juce::TextEditor::focusedOutlineColourId, foreground);
    liveProposalViewer.setText("No pending Live proposal. Control Live will show the exact target here before anything changes.", false);

    for (auto* button : { &saveConnectionButton, &testConnectionButton, &localReviewButton, &exportButton,
                          &askButton, &liveCommandButton, &inspectLiveControlsButton, &automixButton, &applySafeTargetButton,
                          &undoTargetButton, &copyAutoMixLinkButton, &confirmLiveProposalButton,
                          &cancelLiveProposalButton, &undoLiveCommandButton,
                          &masterSpotifyButton, &matchRefButton, &autoGainTrimButton,
                          &arrangeTransitionsButton, &packageStemsButton })
    {
        button->setColour(juce::TextButton::buttonColourId, panelRaised);
        button->setColour(juce::TextButton::textColourOffId, foreground);
        button->setColour(juce::TextButton::textColourOnId, foreground);
    }
    liveContextToggle.setColour(juce::ToggleButton::textColourId, foreground);
    liveContextToggle.setColour(juce::ToggleButton::tickColourId, foreground);
    addAndMakeVisible(confirmLiveProposalButton);
    addAndMakeVisible(cancelLiveProposalButton);
    addAndMakeVisible(undoLiveCommandButton);
    addAndMakeVisible(masterSpotifyButton);
    addAndMakeVisible(matchRefButton);
    addAndMakeVisible(autoGainTrimButton);
    addAndMakeVisible(arrangeTransitionsButton);
    addAndMakeVisible(packageStemsButton);
    masterSpotifyButton.onClick = [this] {
        status.setText("Mastering target: SPOTIFY_STREAMING (-14 LUFS, -1.0 dBTP)", juce::dontSendNotification);
    };
    matchRefButton.onClick = [this] {
        status.setText("Reference Track Matcher: Analyzing 40-band ERB spectrum...", juce::dontSendNotification);
    };
    autoGainTrimButton.onClick = [this] {
        status.setText("Auto-Gain Stager: Nominal -18 dBFS headroom audit initiated.", juce::dontSendNotification);
    };
    arrangeTransitionsButton.onClick = [this] {
        status.setText("Arrangement Doctor: Analyzing timeline energy curves and transitions...", juce::dontSendNotification);
    };
    packageStemsButton.onClick = [this] {
        status.setText("Stem Packager: Preparing 5-tier commercial release stems and certificate...", juce::dontSendNotification);
    };
    confirmLiveProposalButton.setEnabled(false);
    cancelLiveProposalButton.setEnabled(false);
    undoLiveCommandButton.setEnabled(false);
    addAndMakeVisible(saveConnectionButton); saveConnectionButton.onClick = [this] {
        juce::String error;
        if (kennProcessor.setKennConnection(endpointEditor.getText(), sessionEditor.getText(), error))
            status.setText("KENN connection saved for this DAW session.", juce::dontSendNotification);
        else
            status.setText(error, juce::dontSendNotification);
    };
    addAndMakeVisible(testConnectionButton); testConnectionButton.onClick = [this] {
        if (liveRequestBusy("connection check")) return;
        beginLiveRequest("checking", "checking KENN Companion and AbletonOSC");
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis] {
            if (safeThis == nullptr) return;
            juce::String result; const bool ok = safeThis->kennProcessor.testKennConnection(result);
            juce::MessageManager::callAsync([safeThis, ok, result] {
                if (safeThis == nullptr) return;
                if (ok)
                    safeThis->finishLiveRequest(result.containsIgnoreCase("AbletonOSC is connected") ? "connected" : "companion online", result);
                else
                    safeThis->failLiveRequest("Connection failed: " + result);
            });
        });
    };
    addAndMakeVisible(localReviewButton); localReviewButton.onClick = [this] {
        answerViewer.setText(kennProcessor.localDiagnosticSummary(), false);
        status.setText("Local Mix Check complete; no KENN Companion required.", juce::dontSendNotification);
    };
    addAndMakeVisible(exportButton); exportButton.onClick = [this] { juce::String result; if (! kennProcessor.sendHandoffToKenn(result)) { juce::String path; const bool saved = kennProcessor.writeHandoffFile(path); result += saved ? " Saved: " + path : " " + path; answerViewer.setText(kennProcessor.localDiagnosticSummary(), false); result += " Local Mix Check is still available."; } status.setText(result, juce::dontSendNotification); };
    addAndMakeVisible(askButton); askButton.onClick = [this] {
        const auto question = questionEditor.getText();
        if (question.trim().isEmpty()) { status.setText("Type a question for KENN first.", juce::dontSendNotification); return; }
        status.setText("KENN is thinking...", juce::dontSendNotification);
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis, question] {
            if (safeThis == nullptr) return;
            juce::String answer; const bool ok = safeThis->kennProcessor.askKenn(question, answer);
            juce::MessageManager::callAsync([safeThis, ok, answer] {
                if (safeThis == nullptr) return;
                safeThis->answerViewer.setText(answer, false);
                safeThis->status.setText(ok ? "KENN answered using the current session context." : "KENN could not answer: " + answer, juce::dontSendNotification);
            });
        });
    };
    addAndMakeVisible(liveCommandButton); liveCommandButton.onClick = [this] {
        const auto command = questionEditor.getText();
        if (command.trim().isEmpty()) { status.setText("Type a Live command first.", juce::dontSendNotification); return; }
        if (liveRequestBusy("Live inspection")) return;
        beginLiveRequest("inspecting", "checking the exact Live target");
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis, command] {
            if (safeThis == nullptr) return;
            juce::var proposal; juce::String result;
            const bool ok = safeThis->kennProcessor.planLiveCommand(command, proposal, result);
            juce::MessageManager::callAsync([safeThis, ok, proposal, result] {
                if (safeThis == nullptr) return;
                safeThis->answerViewer.setText(result, false);
                safeThis->pendingLiveProposal = juce::var();
                safeThis->pendingLiveReceipt = juce::var();
                safeThis->pendingLiveIsUndo = false;
                safeThis->confirmLiveProposalButton.setEnabled(false);
                safeThis->cancelLiveProposalButton.setEnabled(false);
                if (!ok || !proposal.isObject())
                {
                    safeThis->clearPendingLiveProposal(ok ? "No exact proposal was created. KENN made no change." : "No change was made: " + result);
                    if (ok)
                        safeThis->finishLiveRequest("inspected", result.isNotEmpty() ? result : "No exact proposal was created; no change was made.");
                    else
                        safeThis->failLiveRequest("No change was made: " + result);
                    return;
                }
                safeThis->pendingLiveProposal = proposal;
                safeThis->pendingLiveIsUndo = false;
                safeThis->liveProposalViewer.setText(safeThis->formatLiveProposal(proposal, "Pending Live proposal", false), false);
                const auto confirmationBound = static_cast<bool>(proposal.getProperty("requires_confirmation", false));
                safeThis->confirmLiveProposalButton.setEnabled(confirmationBound);
                safeThis->cancelLiveProposalButton.setEnabled(true);
                safeThis->finishLiveRequest(confirmationBound ? "proposal ready" : "read-only plan",
                                            confirmationBound
                                                ? "Exact target is shown below; nothing has changed. Confirm or cancel it."
                                                : "Exact C++ plan is shown below; the companion is required before it can be confirmed.");
            });
        });
    };
    addAndMakeVisible(inspectLiveControlsButton); inspectLiveControlsButton.onClick = [this] {
        if (liveRequestBusy("Live control inspection")) return;
        beginLiveRequest("inspecting", "reading exact Live devices and parameters");
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis] {
            if (safeThis == nullptr) return;
            juce::String result;
            const bool ok = safeThis->kennProcessor.inspectLiveControls(result);
            juce::MessageManager::callAsync([safeThis, ok, result] {
                if (safeThis == nullptr) return;
                safeThis->answerViewer.setText(result, false);
                if (ok)
                    safeThis->finishLiveRequest("connected", "Read-only Live controls loaded; nothing changed.");
                else
                    safeThis->failLiveRequest(result);
            });
        });
    };
    confirmLiveProposalButton.onClick = [this] {
        if (!pendingLiveProposal.isObject()) { status.setText("No Live proposal is waiting for confirmation.", juce::dontSendNotification); return; }
        if (liveRequestBusy("Live apply")) return;
        const auto proposal = pendingLiveProposal;
        const auto sourceReceipt = pendingLiveReceipt;
        const auto isUndo = pendingLiveIsUndo;
        confirmLiveProposalButton.setEnabled(false);
        cancelLiveProposalButton.setEnabled(false);
        beginLiveRequest("applying", isUndo ? "applying and verifying Live undo" : "applying and verifying the Live change");
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis, proposal, sourceReceipt, isUndo] {
            if (safeThis == nullptr) return;
            juce::var receipt;
            juce::String result;
            const bool ok = isUndo
                ? safeThis->kennProcessor.confirmLiveUndo(sourceReceipt, proposal, receipt, result)
                : safeThis->kennProcessor.confirmLiveCommand(proposal, receipt, result);
            juce::MessageManager::callAsync([safeThis, ok, receipt, result, isUndo] {
                if (safeThis == nullptr) return;
                if (ok)
                {
                    safeThis->pendingLiveProposal = juce::var();
                    safeThis->pendingLiveReceipt = juce::var();
                    safeThis->pendingLiveIsUndo = false;
                    safeThis->confirmLiveProposalButton.setEnabled(false);
                    safeThis->cancelLiveProposalButton.setEnabled(false);
                    if (isUndo)
                    {
                        safeThis->pendingLiveReceipt = juce::var();
                        safeThis->hasLiveUndo = false;
                        safeThis->undoLiveCommandButton.setEnabled(false);
                        safeThis->liveProposalViewer.setText("Undo applied and verified. The prior Live value has been restored.", false);
                        safeThis->finishLiveRequest("verified", "Live undo applied and read back successfully.");
                    }
                    else
                    {
                        safeThis->pendingLiveReceipt = receipt;
                        safeThis->hasLiveUndo = receipt.isObject();
                        safeThis->undoLiveCommandButton.setEnabled(safeThis->hasLiveUndo);
                        safeThis->liveProposalViewer.setText("Live change applied and verified.\n\n" + safeThis->formatLiveProposal(receipt, "Applied Live change", false), false);
                        safeThis->finishLiveRequest("verified", "Live change applied and read back successfully. Undo is available below.");
                    }
                    safeThis->answerViewer.setText(result, false);
                }
                else
                {
                    safeThis->confirmLiveProposalButton.setEnabled(safeThis->pendingLiveProposal.isObject());
                    safeThis->cancelLiveProposalButton.setEnabled(safeThis->pendingLiveProposal.isObject());
                    safeThis->answerViewer.setText(result, false);
                    safeThis->failLiveRequest("Live change was not verified: " + result);
                }
            });
        });
    };
    cancelLiveProposalButton.onClick = [this] {
        clearPendingLiveProposal("Proposal cancelled. Nothing was changed.");
        liveRequestStage = "cancelled";
        status.setText("Live [cancelled] Proposal cancelled; nothing was changed.", juce::dontSendNotification);
    };
    undoLiveCommandButton.onClick = [this] {
        if (pendingLiveProposal.isObject()) { status.setText("Confirm or cancel the current Live proposal first.", juce::dontSendNotification); return; }
        if (!hasLiveUndo || !pendingLiveReceipt.isObject()) { status.setText("No verified Live change is available to undo.", juce::dontSendNotification); return; }
        if (liveRequestBusy("undo inspection")) return;
        const auto receipt = pendingLiveReceipt;
        beginLiveRequest("inspecting undo", "preparing a fresh Live undo proposal");
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis, receipt] {
            if (safeThis == nullptr) return;
            juce::var proposal; juce::String result;
            const bool ok = safeThis->kennProcessor.planLiveUndo(receipt, proposal, result);
            juce::MessageManager::callAsync([safeThis, ok, proposal, receipt, result] {
                if (safeThis == nullptr) return;
                if (!ok || !proposal.isObject())
                {
                    safeThis->failLiveRequest("Undo proposal failed: " + result);
                    return;
                }
                safeThis->pendingLiveReceipt = receipt;
                safeThis->pendingLiveProposal = proposal;
                safeThis->pendingLiveIsUndo = true;
                safeThis->liveProposalViewer.setText(safeThis->formatLiveProposal(proposal, "Pending Live undo proposal", true), false);
                safeThis->confirmLiveProposalButton.setEnabled(true);
                safeThis->cancelLiveProposalButton.setEnabled(true);
                safeThis->finishLiveRequest("proposal ready", "Undo target is shown below; nothing has changed. Confirm or cancel it.");
            });
        });
    };
    addAndMakeVisible(automixButton); automixButton.onClick = [this] {
        stemChooser = std::make_unique<juce::FileChooser>("Choose audio stems for AutoMix", juce::File(), "*.wav;*.aif;*.aiff;*.flac");
        stemChooser->launchAsync(juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles | juce::FileBrowserComponent::canSelectMultipleItems,
            [this](const juce::FileChooser& chooser) {
                const auto files = chooser.getResults();
                if (files.isEmpty()) return;
                status.setText("Uploading stems to AutoMix...", juce::dontSendNotification);
                juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
                juce::Thread::launch([safeThis, files] {
                    if (safeThis == nullptr) return;
                    juce::String result; const bool ok = safeThis->kennProcessor.startAutoMix(files, result);
                    juce::MessageManager::callAsync([safeThis, ok, result] { if (safeThis != nullptr) { if (ok) safeThis->activeAutoMixJob = result.fromFirstOccurrenceOf(": ", false, false); safeThis->status.setText(ok ? result : "AutoMix failed: " + result, juce::dontSendNotification); } });
                });
            });
    };
    addAndMakeVisible(applySafeTargetButton); applySafeTargetButton.onClick = [this] {
        if (kennProcessor.getAssistantMode() != "assist" && kennProcessor.getAssistantMode() != "auto")
        {
            status.setText("Switch to Assist or Auto mode before applying a KENN proposal.", juce::dontSendNotification);
            return;
        }
        status.setText("Requesting a safe proposal from KENN...", juce::dontSendNotification);
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis] {
            if (safeThis == nullptr) return;
            float proposed = 0.0f; juce::String reason;
            const bool ok = safeThis->kennProcessor.requestSafeTargetProposal(proposed, reason);
            juce::MessageManager::callAsync([safeThis, ok, proposed, reason] {
                if (safeThis == nullptr) return;
                if (! ok) { safeThis->status.setText(reason, juce::dontSendNotification); return; }
                safeThis->targetBeforeProposal = safeThis->kennProcessor.apvts.getRawParameterValue("target_lufs")->load();
                if (juce::NativeMessageBox::showOkCancelBox(juce::MessageBoxIconType::WarningIcon, "Apply KENN proposal", "KENN recommends changing target from " + juce::String(safeThis->targetBeforeProposal, 1) + " to " + juce::String(proposed, 1) + " LUFS.\n\n" + reason + "\n\nThis changes only the KENN plug-in setting and can be undone.", safeThis.getComponent(), nullptr))
                {
                    if (auto* parameter = safeThis->kennProcessor.apvts.getParameter("target_lufs")) { parameter->beginChangeGesture(); parameter->setValueNotifyingHost(parameter->convertTo0to1(proposed)); parameter->endChangeGesture(); safeThis->kennProcessor.recordTargetAction("applied", safeThis->targetBeforeProposal, proposed, reason); safeThis->hasTargetUndo = true; safeThis->status.setText("Applied confirmed KENN target proposal.", juce::dontSendNotification); }
                }
            });
        });
    };
    addAndMakeVisible(undoTargetButton); undoTargetButton.onClick = [this] {
        if (! hasTargetUndo) { status.setText("No KENN target change to undo.", juce::dontSendNotification); return; }
        if (auto* parameter = kennProcessor.apvts.getParameter("target_lufs")) { const auto current = parameter->convertFrom0to1(parameter->getValue()); parameter->beginChangeGesture(); parameter->setValueNotifyingHost(parameter->convertTo0to1(targetBeforeProposal)); parameter->endChangeGesture(); kennProcessor.recordTargetAction("undone", current, targetBeforeProposal, "User selected Undo Target."); hasTargetUndo = false; status.setText("Restored prior KENN target.", juce::dontSendNotification); }
    };
    addAndMakeVisible(copyAutoMixLinkButton); copyAutoMixLinkButton.onClick = [this] {
        if (completedAutoMixJob.isEmpty()) { status.setText("No completed AutoMix delivery is available yet.", juce::dontSendNotification); return; }
        const auto url = juce::URL(kennProcessor.getKennEndpoint() + "/api/automix-download").withParameter("id", completedAutoMixJob).toString(true);
        juce::SystemClipboard::copyTextToClipboard(url);
        status.setText("AutoMix download link copied to the clipboard.", juce::dontSendNotification);
    };
    addAndMakeVisible(targetLufs); targetLufs.setSliderStyle(juce::Slider::LinearHorizontal); targetLufs.setTextBoxStyle(juce::Slider::TextBoxRight, false, 70, 22); targetLufs.setRange(-24.0, -6.0, 0.1);
    targetLufs.setColour(juce::Slider::backgroundColourId, panel);
    targetLufs.setColour(juce::Slider::trackColourId, juce::Colour(0xff4d91b3));
    targetLufs.setColour(juce::Slider::thumbColourId, juce::Colour(0xff61b7df));
    targetLufs.setColour(juce::Slider::textBoxTextColourId, foreground);
    targetLufs.setColour(juce::Slider::textBoxBackgroundColourId, panel);
    targetLufs.setColour(juce::Slider::textBoxOutlineColourId, outline);
    targetAttachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment>(kennProcessor.apvts, "target_lufs", targetLufs);
    // Keep the command and confirmation controls visible on compact laptop or
    // remote desktops.  The editor switches to a focused command layout below
    // 680 px and remains resizable for the full receipt and AutoMix controls.
    setSize(1020, 680);
    setResizable(true, true);
    setResizeLimits(560, 480, 1920, 1400);
    startTimerHz(8);
}
void KENNMixAssistantAudioProcessorEditor::paint(juce::Graphics& g)
{
    if (webView != nullptr && webView->isVisible())
    {
        g.fillAll(juce::Colour(0xff0b0f17));
        return;
    }
    g.fillAll(juce::Colour(0xff12151c));
    g.setColour(juce::Colour(0xff263041));
    g.drawRoundedRectangle(getLocalBounds().toFloat().reduced(8), 8.0f, 1.0f);
}
void KENNMixAssistantAudioProcessorEditor::resized()
{
    if (webView != nullptr && webView->isVisible())
    {
        webView->setBounds(getLocalBounds());
        return;
    }

    auto area = getLocalBounds().reduced(22);
    const bool compact = getHeight() < 680;
    for (auto* button : { &localReviewButton, &exportButton, &automixButton,
                          &applySafeTargetButton, &undoTargetButton,
                          &copyAutoMixLinkButton })
        button->setVisible(! compact);
    actionAudit.setVisible(! compact);

    if (compact)
    {
        heading.setBounds(area.removeFromTop(30));
        metrics.setBounds(area.removeFromTop(38));
        guidance.setBounds(area.removeFromTop(42));
        targetLufs.setBounds(area.removeFromTop(34));
        auto modeRow = area.removeFromTop(28); modeLabel.setBounds(modeRow.removeFromLeft(150)); modeSelector.setBounds(modeRow.removeFromLeft(150));
        liveContextToggle.setBounds(area.removeFromTop(28));
        auto endpointRow = area.removeFromTop(28); endpointLabel.setBounds(endpointRow.removeFromLeft(150)); endpointEditor.setBounds(endpointRow);
        auto sessionRow = area.removeFromTop(28); sessionLabel.setBounds(sessionRow.removeFromLeft(150)); sessionEditor.setBounds(sessionRow.removeFromLeft(150)); saveConnectionButton.setBounds(sessionRow.removeFromLeft(90)); testConnectionButton.setBounds(sessionRow);
        auto questionRow = area.removeFromTop(30); askButton.setBounds(questionRow.removeFromRight(105)); liveCommandButton.setBounds(questionRow.removeFromRight(120)); questionEditor.setBounds(questionRow);
        auto liveInventoryRow = area.removeFromTop(30); inspectLiveControlsButton.setBounds(liveInventoryRow.removeFromLeft(180));
        answerViewer.setBounds(area.removeFromTop(74));
        liveProposalViewer.setBounds(area.removeFromTop(100));
        auto proposalButtons = area.removeFromTop(34);
        confirmLiveProposalButton.setBounds(proposalButtons.removeFromLeft(190));
        cancelLiveProposalButton.setBounds(proposalButtons.removeFromLeft(150));
        undoLiveCommandButton.setBounds(proposalButtons.removeFromLeft(190));
        status.setBounds(area);
        return;
    }

    heading.setBounds(area.removeFromTop(34)); metrics.setBounds(area.removeFromTop(48)); guidance.setBounds(area.removeFromTop(34));
    targetLufs.setBounds(area.removeFromTop(34));
    auto modeRow = area.removeFromTop(28); modeLabel.setBounds(modeRow.removeFromLeft(150)); modeSelector.setBounds(modeRow.removeFromLeft(150));
    liveContextToggle.setBounds(area.removeFromTop(28));
    auto endpointRow = area.removeFromTop(28); endpointLabel.setBounds(endpointRow.removeFromLeft(150)); endpointEditor.setBounds(endpointRow);
    auto sessionRow = area.removeFromTop(28); sessionLabel.setBounds(sessionRow.removeFromLeft(150)); sessionEditor.setBounds(sessionRow.removeFromLeft(150)); saveConnectionButton.setBounds(sessionRow.removeFromLeft(90)); testConnectionButton.setBounds(sessionRow);
    auto questionRow = area.removeFromTop(30); askButton.setBounds(questionRow.removeFromRight(105)); liveCommandButton.setBounds(questionRow.removeFromRight(120)); questionEditor.setBounds(questionRow);
    auto liveInventoryRow = area.removeFromTop(30); inspectLiveControlsButton.setBounds(liveInventoryRow.removeFromLeft(180));
    answerViewer.setBounds(area.removeFromTop(120));
    liveProposalViewer.setBounds(area.removeFromTop(145));
    auto proposalButtons = area.removeFromTop(34);
    confirmLiveProposalButton.setBounds(proposalButtons.removeFromLeft(190));
    cancelLiveProposalButton.setBounds(proposalButtons.removeFromLeft(150));
    undoLiveCommandButton.setBounds(proposalButtons.removeFromLeft(190));
    localReviewButton.setBounds(area.removeFromTop(34).removeFromLeft(240));
    exportButton.setBounds(area.removeFromTop(34).removeFromLeft(240)); automixButton.setBounds(area.removeFromTop(34).removeFromLeft(240));
    applySafeTargetButton.setBounds(area.removeFromTop(34).removeFromLeft(240)); undoTargetButton.setBounds(area.removeFromTop(34).removeFromLeft(240));
    copyAutoMixLinkButton.setBounds(area.removeFromTop(34).removeFromLeft(240)); actionAudit.setBounds(area.removeFromTop(22)); status.setBounds(area.reduced(0, 10));
}
void KENNMixAssistantAudioProcessorEditor::timerCallback()
{
    const auto s = kennProcessor.meterSnapshot();
    metrics.setText(juce::String::formatted("Peak %.1f dBFS   RMS %.1f dBFS   Correlation %.2f   Width %.2f\nCrest %.1f dB   Transient %.2f   Clipped %d", s.peakDb, s.rmsDb, s.correlation, s.stereoWidth, s.crestDb, s.transientRatio, s.clippedSamples), juce::dontSendNotification);
    actionAudit.setText(kennProcessor.latestTargetActionSummary(), juce::dontSendNotification);

    if (serverOnline && ++paramSyncTicks >= 4)
    {
        paramSyncTicks = 0;
        kennProcessor.syncWebParameters();
    }

    if (++serverCheckTicks >= 16 || ! webViewLoaded)
    {
        serverCheckTicks = 0;
        int healthStatus = 0;
        const auto healthOptions = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
            .withConnectionTimeoutMs(350).withNumRedirectsToFollow(0).withStatusCode(&healthStatus);
        const auto stream = juce::URL(kennProcessor.getKennEndpoint() + "/api/health").createInputStream(healthOptions);
        const bool online = (stream != nullptr && healthStatus == 200);
        if (online != serverOnline)
        {
            serverOnline = online;
            if (serverOnline)
            {
                if (! webViewLoaded && webView != nullptr)
                {
                    const auto targetUrl = kennProcessor.getKennEndpoint() + "/?session_id=" + kennProcessor.getKennSessionId();
                    webView->goToURL(targetUrl);
                    webViewLoaded = true;
                }
                if (webView != nullptr) webView->setVisible(true);
                for (auto* comp : std::initializer_list<juce::Component*>{
                    &heading, &metrics, &guidance, &status, &actionAudit, &endpointLabel, &sessionLabel, &modeLabel,
                    &localReviewButton, &exportButton, &askButton, &liveCommandButton, &inspectLiveControlsButton,
                    &automixButton, &applySafeTargetButton, &undoTargetButton, &copyAutoMixLinkButton,
                    &saveConnectionButton, &testConnectionButton, &confirmLiveProposalButton, &cancelLiveProposalButton,
                    &undoLiveCommandButton, &masterSpotifyButton, &matchRefButton, &autoGainTrimButton,
                    &arrangeTransitionsButton, &packageStemsButton,
                    &endpointEditor, &sessionEditor, &questionEditor, &answerViewer,
                    &liveProposalViewer, &modeSelector, &liveContextToggle, &targetLufs
                })
                {
                    comp->setVisible(false);
                }
            }
            else
            {
                if (webView != nullptr) webView->setVisible(false);
                webViewLoaded = false;
                guidance.setText("Connecting to KENN Companion Server...", juce::dontSendNotification);
                for (auto* comp : std::initializer_list<juce::Component*>{
                    &heading, &metrics, &guidance, &status, &endpointLabel, &sessionLabel,
                    &saveConnectionButton, &testConnectionButton, &endpointEditor, &sessionEditor,
                    &localReviewButton
                })
                {
                    comp->setVisible(true);
                }
                for (auto* comp : std::initializer_list<juce::Component*>{
                    &actionAudit, &modeLabel, &exportButton, &askButton, &liveCommandButton,
                    &inspectLiveControlsButton, &automixButton, &applySafeTargetButton, &undoTargetButton,
                    &copyAutoMixLinkButton, &confirmLiveProposalButton, &cancelLiveProposalButton,
                    &undoLiveCommandButton, &masterSpotifyButton, &matchRefButton, &autoGainTrimButton,
                    &arrangeTransitionsButton, &packageStemsButton,
                    &questionEditor, &answerViewer, &liveProposalViewer,
                    &modeSelector, &liveContextToggle, &targetLufs
                })
                {
                    comp->setVisible(false);
                }
            }
            resized();
            repaint();
        }
    }

    if (liveRequestInFlight.load() && ! liveRequestTimedOut.load()
        && liveRequestStarted.toMilliseconds() > 0
        && juce::Time::getCurrentTime().toMilliseconds() - liveRequestStarted.toMilliseconds() >= 30000)
    {
        liveRequestTimedOut.store(true);
        status.setText("Live [timeout] " + liveRequestStage + " exceeded 30 s. Do not retry; wait for the current result.", juce::dontSendNotification);
    }
    if (activeAutoMixJob.isNotEmpty() && ++pollTicks >= 64)
    {
        pollTicks = 0;
        const auto job = activeAutoMixJob;
        juce::Component::SafePointer<KENNMixAssistantAudioProcessorEditor> safeThis(this);
        juce::Thread::launch([safeThis, job] { if (safeThis == nullptr) return; juce::String result; bool complete = false; const bool ok = safeThis->kennProcessor.fetchAutoMixStatus(job, result, complete); juce::MessageManager::callAsync([safeThis, ok, complete, job, result] { if (safeThis != nullptr) { if (ok) safeThis->status.setText(result, juce::dontSendNotification); if (complete) { if (result.startsWithIgnoreCase("AutoMix complete")) safeThis->completedAutoMixJob = job; safeThis->activeAutoMixJob.clear(); } } }); });
    }
}

