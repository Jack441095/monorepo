"""Deterministic, evidence-first diagnostic planning for audio questions.

Retrieval can tell KENN *what* a technique is.  It cannot, by itself, decide
whether that technique is warranted for the symptom in front of it.  This
module supplies that missing causal layer.  It deliberately produces a small
ranked set of hypotheses and cheap discriminating tests; it is not a preset
library and never claims to have heard unprovided audio.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kenn.core.evidence import EvidencePacket


@dataclass(frozen=True)
class Hypothesis:
    cause: str
    why_plausible: str
    test: str
    if_confirmed: str


@dataclass(frozen=True)
class DiagnosticPlan:
    symptom: str
    issue_type: str
    hypotheses: tuple[Hypothesis, ...]
    verification: str
    question: str


def _contains_all(text: str, *terms: str) -> bool:
    return all(term in text for term in terms)


def plan_for(query: str) -> DiagnosticPlan | None:
    """Return a causal diagnostic plan for an ambiguous audio symptom.

    Plans are intentionally selected only for clear symptom-shaped requests.
    A direct how-to ("how do I make a send reverb?") should remain a normal
    workflow answer rather than being padded with unnecessary diagnosis.
    """
    text = query.lower()
    realtime_reference_question = (
        any(term in text for term in ("live bus", "realtime", "real-time", "plugin bus", "plug-in bus"))
        and any(term in text for term in ("compare", "comparison", "reference", "uploaded"))
    )

    if re.search(r"\bbass\b.*\b(?:disappear|disappears|vanish|vanishes|drop|drops)\b", text) and "kick" in text:
        return DiagnosticPlan(
            symptom="The bass loses audibility when the kick plays.",
            issue_type="Usually a technical kick/bass interaction; how much audible ducking is desirable is a creative choice.",
            hypotheses=(
                Hypothesis("Sidechain or volume ducking is too deep or too long", "A kick-triggered compressor, shaper, or automation can keep the bass below audibility after the kick rather than merely making room for it.", "Bypass the sidechain path at matched loudness, then restore it with less gain reduction and a shorter release. Compare only the kick-hit region.", "Use the minimum sidechain depth and release that clears the kick while letting the bass recover before the next musical note."),
                Hypothesis("Fundamentals are masking or cancelling", "Even without sidechain processing, overlapping low notes can hide the bass or reduce the summed low end through timing or polarity interaction.", "Mute the kick briefly on the affected bass note, then compare mono, polarity, and tiny timing changes without changing level.", "Choose a low-frequency owner and adjust note length, octave, alignment, or frequency-specific space before applying a large EQ boost."),
                Hypothesis("The bass has no audible harmonic cue on the target system", "A sub-heavy bass can seem to disappear on phones or small speakers even when its deepest octave is present on full-range monitoring.", "High-pass the mix temporarily and compare with a matched reference on a small speaker. If the bass role vanishes, it needs body above the sub range.", "Add controlled harmonics or body, then re-check that the apparent improvement is not simply louder overall."),
            ),
            verification="At matched loudness, the kick should have space and the bass should recover predictably on every hit in mono and on a small speaker.",
            question="Is there a sidechain/volume-shaper on the bass, and does the loss last only for the kick transient or through the next note?",
        )

    if (
        "reference" in text
        and ("mix" in text or realtime_reference_question)
        and not any(term in text for term in ("choose", "choosing", "pick", "picking", "select", "selecting", "find", "finding", "need", "want", "looking for"))
        and (
            any(term in text for term in ("dark", "darker", "bright", "brighter", "dull", "duller", "match", "different"))
            or realtime_reference_question
        )
    ):
        return DiagnosticPlan(
            symptom="The mix is being judged as tonally different from a chosen reference.",
            issue_type="A reference comparison can measure differences between two renders, but whether to match its tone, arrangement, and dynamics is a creative decision—not a mandate to copy it.",
            hypotheses=(
                Hypothesis("The two renders are not level-matched", "A louder reference can seem brighter, fuller, punchier, or clearer even when the spectral difference is small.", "Match integrated or short-term listening level before comparing the same musical section. Switch quickly and do not judge from a louder version.", "Keep the loudness-neutral comparison as the baseline before making a tonal move."),
                Hypothesis("A measured spectral difference is coming from one or a few musical relationships", "A broad difference can come from sound choice, octave, arrangement density, ambience, or processing; a band label alone does not name the cause.", "Identify the densest matching section, then mute or rebalance likely contributors one at a time while comparing to the level-matched reference.", "Change the smallest source or relationship that moves the stated difference; do not automatically apply a master-bus match curve."),
                Hypothesis("The reference has a deliberately different arrangement or aesthetic", "Two valid productions can distribute bass, presence, width, and dynamics differently because the song and target are different.", "State which quality you actually want from the reference—weight, vocal clarity, punch, brightness, width, or loudness—then compare that quality separately.", "Adopt the transferable goal while retaining intentional differences that suit this record."),
            ),
            verification="At matched loudness, the chosen quality should move toward the intended reference without losing the mix's vocal hierarchy, low-end control, mono stability, or creative identity.",
            question="Which specific reference quality are you trying to borrow: tonal brightness, low-end weight, vocal clarity, punch, width, or loudness?",
        )

    if any(term in text for term in ("reverb", "plate", "hall", "delay return")) and any(
        term in text for term in ("wash", "washes", "washed", "wash out", "muddy", "blur")
    ):
        return DiagnosticPlan(
            symptom="A vocal or lead-space effect works in one section but washes out a denser section.",
            issue_type="The intended sense of vocal depth and space is creative, while intelligibility, masking, and section-dependent effect buildup can be tested before changing the dry lead or adding more processing.",
            hypotheses=(
                Hypothesis("The same wet level is too dense for the chorus arrangement", "A return that leaves useful gaps in a sparse verse can overlap competing instruments and sustained vocal phrases once the chorus becomes denser.", "Keep the dry lead level fixed, then automate the plate/send down only in the chorus and compare the words immediately before and after it at matched loudness.", "Use section-specific send or return automation; retain the verse setting if it still serves the intimate/close role there."),
                Hypothesis("Decay or pre-delay does not fit the chorus phrase rhythm", "A tail can cross into the next lyric or rhythmic event even if its level is moderate, making the lead feel further back.", "Shorten decay first, then compare two pre-delay settings while looping the densest chorus phrase. Listen for the dry consonant and the gap after each line.", "Keep the shortest timing that preserves the desired glue; reserve longer tails for endings or sparse transitions."),
                Hypothesis("The return carries masking low-mids or bright consonants", "Full-band ambience can build low-mid cloud or repeat sibilants as the arrangement adds more material.", "High-pass, low-pass, or de-ess the return temporarily, then bypass/restore it at equal perceived vocal level to identify which range creates the wash.", "Filter or dynamically duck the return from the dry lead rather than EQing the whole vocal to compensate."),
            ),
            verification="At matched dry-vocal level, the chorus should retain the intended depth and space while every lyric remains as intelligible and forward as the verse; the return should fill gaps rather than cover the next phrase.",
            question="Does the wash arrive because the chorus is denser, because the tail overlaps the next lyric, or because a specific low-mid/bright range builds up on the return?",
        )

    if "snare" in text and any(term in text for term in ("weak", "small", "no punch", "lacks punch", "disappear", "buried")):
        return DiagnosticPlan(
            symptom="The snare is described as weak or lacking impact.",
            issue_type="Snare impact is an interaction of source, transient, body, groove, and arrangement; the preferred amount of crack, weight, and room remains creative.",
            hypotheses=(
                Hypothesis("The source transient or body is not surviving the chain", "Fast dynamics control, clipping, saturation, or an unsuitable layer can reduce the contrast that makes a snare read.", "Level-match and bypass each snare dynamics/saturation stage and any layer one at a time. Compare the combined snare in mono.", "Keep only the stage or layer that improves the hit; restore transient/body balance before adding more level."),
                Hypothesis("Other parts or tails are masking the snare at the hit", "Dense guitars, synths, hats, rooms, and long snare tails can hide either its attack or its body.", "Mute or shorten one likely competitor for a bar around the backbeat. If the snare returns without an EQ boost, the relationship is the first problem.", "Create a small arrangement, envelope, automation, or contextual-frequency pocket instead of boosting the whole drum bus."),
                Hypothesis("Timing, polarity, or layer alignment is reducing the combined hit", "Related layers can sum smaller when their starts or polarity disagree.", "Check polarity and tiny start offsets while monitoring the summed snare in mono; retain only changes that improve the audible hit at matched level.", "Use the alignment that improves the combined source, not the waveform that merely looks aligned."),
            ),
            verification="At matched loudness, the snare should define the backbeat at low volume and in mono without becoming clicky, harsh, or disconnected from the kit.",
            question="Does the snare feel weak in the raw kit, only in the dense section, or only after drum/bus processing?",
        )

    if "vocal" in text and any(term in text for term in ("poor recording", "bad recording", "recording sounds bad", "recorded badly", "sounds bad raw", "raw recording")):
        return DiagnosticPlan(
            symptom="The vocal recording is reported as poor before mix processing.",
            issue_type="Capture quality is mostly a technical constraint, while the desired vocal character remains creative. Repair processing cannot fully replace a controlled source, room, and performance.",
            hypotheses=(
                Hypothesis("Direct-to-room ratio is too low", "Distance, untreated reflections, and a noisy room can make the raw vocal sound distant, boxy, or unstable before any plug-in is inserted.", "Record a short identical phrase closer and at the current position, with the same input gain. Compare dry takes for room between words and tonal stability.", "Choose the more direct position and reduce the strongest nearby reflection before relying on denoise, gates, or broad EQ."),
                Hypothesis("Microphone angle, distance, or gain staging does not suit the performer", "Capsule angle and distance change plosives, proximity/body, sibilance, and level; a weak capture can force excessive processing later.", "Make two controlled tests: slightly off-axis/closer versus current position, while leaving enough headroom for peaks. Compare diction, plosives, and body dry.", "Use the position that needs the least corrective processing; set preamp gain for healthy peaks without clipping."),
                Hypothesis("Performance or monitoring is driving inconsistent capture", "Headphone balance, distance changes, delivery, and fatigue can create level/tone variation that resembles a microphone fault.", "Listen to several raw phrases and note whether the problem follows words, distance movement, or the whole take. Confirm the performer can hear a comfortable cue mix.", "Solve cue, technique, comping, or take selection before compressing every inconsistency."),
            ),
            verification="A new dry test should sound more direct and even at matched monitoring level, with less room, clipping, harshness, or proximity excess before mix processing.",
            question="What is the raw symptom—roomy/boxy, noisy, thin, harsh, clipped, inconsistent, or plosive-heavy—and what mic distance/room setup are you using?",
        )

    if "streaming" in text and any(term in text for term in ("too quiet", "too loud", "sounds worse", "sounds bad", "normaliz", "normalis", "loudness concern", "loudness problem")):
        return DiagnosticPlan(
            symptom="A streaming-normalization or delivery loudness concern is reported.",
            issue_type="Platform normalization and true-peak safety are technical delivery considerations; the desired master density and competitive character remain release-context choices, not a universal LUFS target.",
            hypotheses=(
                Hypothesis("The comparison is level-biased or uses different platform behaviour", "Normalization may turn a hotter master down, while different apps, settings, codecs, and playback paths change what is actually heard.", "Compare your master and reference at matched perceived loudness with the same platform/normalization setting. Check whether the concern is loudness, punch, codec artifacts, or tone.", "Choose the version that survives matched listening rather than mastering only to a displayed target number."),
                Hypothesis("The master is paying too much for loudness", "Excess limiting, clipping, or dense low end can reduce punch and create distortion that remains after normalization turns the file down.", "Level-match a less-driven print and compare transient clarity, pumping, and distortion before changing the final ceiling.", "Reduce the stage or mix trigger that causes the cost; then set a delivery ceiling appropriate to the release path."),
                Hypothesis("True-peak or codec behaviour is causing a technical artifact", "A file can be sample-peak-safe yet develop inter-sample or codec overs, especially with aggressive high-frequency or limiting content.", "Inspect true peak with an appropriate meter, audition the encoded/platform preview where available, and compare an offline encode of the affected passage.", "Leave adequate true-peak margin and fix the source of the overs/artifact instead of simply reducing the whole master blindly."),
            ),
            verification="On the intended platform and at matched loudness, the master should retain the intended punch and tone without clipping, codec artifacts, or a misleading loudness advantage.",
            question="Which platform and normalization setting are you comparing, and is the problem perceived loudness, loss of punch, distortion, or codec artifacts?",
        )

    if any(term in text for term in ("harsh", "brittle", "fatiguing")) and any(term in text for term in ("mastering", "mastered", "limiter", "after mastering", "after limiting")):
        return DiagnosticPlan(
            symptom="Harshness is reported after mastering or final limiting.",
            issue_type="A master-chain change can be tested technically, while the intended brightness and density remain creative decisions. Do not assume a broad high-frequency cut is the correct first move.",
            hypotheses=(
                Hypothesis("Limiter, clipper, or saturation is making upper detail too constant", "Final dynamics control can raise the apparent density of cymbals, consonants, distortion, and upper-mid transients even when static EQ was acceptable.", "Level-match and bypass each final dynamics/drive stage one at a time on the harshest section. Listen for fatigue changing without a large level shift.", "Reduce, retime, or redistribute the stage that intensifies the symptom before globally cutting high frequencies."),
                Hypothesis("The master is exposing a mix-stage brightness or resonance issue", "A limiter may reveal an existing source/arrangement buildup rather than create it from nothing.", "Compare the pre-master and mastered print at matched loudness, then mute likely bright contributors in the pre-master mix during the same section.", "Address the contributing source, arrangement, or mix-bus relationship before using a broad mastering EQ correction."),
                Hypothesis("The comparison is biased by level or playback", "A louder or different playback path can sound brighter and more fatiguing, encouraging an over-correction.", "Compare to a matched reference quietly and on one alternate playback system before committing a tonal move.", "Keep only a correction that improves repeated matched observations across relevant systems."),
            ),
            verification="At matched loudness, the mastered version should retain intended articulation and energy while the harshest section becomes less fatiguing on repeated playback checks.",
            question="Does the harshness begin with one specific limiter/clipper stage, or is it already present in the pre-master mix at matched loudness?",
        )

    if any(term in text for term in ("inconsistent dynamics", "dynamics are inconsistent", "chorus too loud", "verse too quiet", "levels jump")) and any(term in text for term in ("mix", "master", "song", "track")):
        return DiagnosticPlan(
            symptom="Dynamics or perceived level are inconsistent across sections.",
            issue_type="Section-to-section consistency is partly a creative arrangement decision, but unintended jumps, overload, and unstable control can be measured and tested before applying more bus compression.",
            hypotheses=(
                Hypothesis("Arrangement density or source levels change more than intended", "A chorus can feel much louder because of added sustained layers, low end, or brightness even if a master meter does not show a proportionate change.", "Compare verse and chorus at matched monitoring level, then mute or lower one added group at a time to identify the largest perceptual change.", "Use arrangement, clip gain, group level, or automation to shape the transition before relying on the master bus."),
                Hypothesis("Bus/master processing reacts differently by section", "Compression, limiting, and clipping may grip dense sections harder, flattening one section or making the release pump between events.", "Compare gain reduction and matched bypass in each section. Check whether the same settings alter transient shape or phrase movement differently.", "Retune, automate, or redistribute control so the processing supports both sections rather than forcing one compromise setting."),
                Hypothesis("The monitoring comparison is not controlled", "Small level differences can be heard as large energy or tonal changes, especially across different sections and references.", "Use short, repeatable A/B loops at a consistent monitor level and compare measured section loudness where available.", "Keep only changes that improve the intended contrast without accidental jumps or lost musical lift."),
            ),
            verification="The intended verse/chorus contrast should remain, but transitions should feel deliberate and stable without one section collapsing, pumping, or winning only by level.",
            question="Which transition is wrong—verse to chorus, drop to breakdown, or loud/quiet phrases—and does it change when bus/master processing is bypassed?",
        )

    if any(term in text for term in ("narrow", "lacks width", "no width", "not wide enough", "weak stereo image", "stereo image is weak")) and any(term in text for term in ("mix", "stereo", "image", "production")):
        return DiagnosticPlan(
            symptom="The mix is described as narrower than intended.",
            issue_type="Desired width is a creative decision; mono compatibility and loss of important centre information are technical constraints.",
            hypotheses=(
                Hypothesis("The arrangement has few genuinely different left/right cues", "Duplicating the same mono source or widening everything does not create useful contrast or depth.", "Identify one non-essential supporting role, then compare a real double, contrasting performance, or deliberate pan against the centred original in the full arrangement.", "Build width from complementary parts while retaining lead, kick, bass, and other anchor roles where they serve the song."),
                Hypothesis("Returns and side content are too similar or too quiet", "Stereo ambience and delays can exist but contribute little if they are filtered, masked, or not automated around phrases.", "Solo then reintroduce one stereo return at matched loudness; check whether it adds a distinct side cue or merely washes the centre.", "Use a selective return or phrase-based automation rather than widening every source."),
                Hypothesis("The apparent width depends on a mono-risk process", "Haas delay, phase rotation, and aggressive widening can enlarge stereo while weakening the fold-down.", "Compare stereo and mono while bypassing each width process. Judge vocal/instrument role and level, not just the size of the stereo display.", "Keep only width that survives the relevant mono check; use safer doubles or panned texture for the rest."),
            ),
            verification="The mix should feel wider in stereo while its anchors retain their role and approximate level when folded to mono.",
            question="Which role should become wider—lead, doubles, pads, drums, ambience, or the whole mix—and does mono compatibility matter for release?",
        )

    if any(term in text for term in ("dull", "too dark", "lacks brightness", "not bright enough")) and any(term in text for term in ("mix", "master", "track", "vocal")):
        return DiagnosticPlan(
            symptom="The material is described as dull or darker than intended.",
            issue_type="Brightness is partly aesthetic, but monitoring, source bandwidth, masking, and over-control can be tested before applying a broad high shelf.",
            hypotheses=(
                Hypothesis("Monitoring level, room, or playback is biasing the judgement", "A room/system or loud listening can make a valid tonal balance seem darker or lead to compensating boosts that fail elsewhere.", "Compare quietly on one known alternate system against a level-matched reference before changing EQ.", "Keep only a tonal move that survives both systems and the intended playback context."),
                Hypothesis("The audible high-frequency source is masked or missing", "The issue can be sound choice, arrangement overlap, microphone angle, or an absent transient/harmonic cue rather than a master-bus EQ problem.", "Mute likely masking parts or compare the dry source to the processed chain in the affected section. Check whether the desired detail returns without a broad boost.", "Address source choice, arrangement, or the specific relationship first; add only a small contextual tonal change if it remains necessary."),
                Hypothesis("Processing is reducing contrast or bandwidth", "Low-pass filtering, de-essing, saturation, compression, or limiting can make air and transient detail less distinct.", "Level-match and bypass relevant stages one at a time, listening for restored articulation rather than extra loudness.", "Retune or reduce the stage that removes the desired detail before adding brightness downstream."),
            ),
            verification="At matched loudness, articulation and air should return without brittle cymbals, painful consonants, or a tonal correction that works only on one system.",
            question="Does the dullness exist in the raw source, arrive after processing, or only appear on a particular monitor/playback system?",
        )

    if "master" not in text and any(term in text for term in ("distorted", "distortion", "crackling", "crackle", "clipping", "clips", "clipped")) and any(term in text for term in ("mix", "track", "vocal", "audio")):
        return DiagnosticPlan(
            symptom="Unwanted distortion or crackling is reported.",
            issue_type="Unintended digital overload, faulty routing, or hardware/capture problems are technical; intentional saturation/distortion is a creative choice that still needs gain-staged verification.",
            hypotheses=(
                Hypothesis("A gain stage is clipping or overshooting", "Distortion can occur before the final limiter, and a meter elsewhere does not clear every plug-in, send, converter, or export stage.", "Bypass or reduce one stage at a time while level-matching, starting at the first stage that changes the symptom. Check sample and true-peak where available.", "Fix the earliest overload and restore headroom there rather than compensating with a later limiter."),
                Hypothesis("A processor is producing unwanted harmonics or aliasing", "Saturation, clipping, time-stretching, restoration, or low-quality resampling can sound rough even below full scale.", "Bypass the suspect processor or compare its quality/oversampling mode at equal output level on the affected phrase.", "Use the least aggressive setting or a higher-quality mode only if it improves the audible symptom."),
                Hypothesis("The problem is capture, hardware, or playback-specific", "Intermittent crackle can come from buffer/driver issues, a cable, converter, clocking, or a damaged source rather than the mix balance.", "Render the same section offline, then compare another playback path/input and note whether the artifact prints into the file.", "Repair the physical or system path if it does not print; treat a printed artifact as an audio-stage problem."),
            ),
            verification="The artifact should disappear in the affected section at matched loudness without merely lowering the entire mix or removing intentional character.",
            question="Does the distortion print into an offline export, and does it begin at one processor/gain stage or only on a particular playback path?",
        )

    if "kick" in text and any(term in text for term in ("bass", "sub", "808")) and any(
        term in text for term in (
            "disappear", "disappears", "lost", "fight", "conflict", "mask",
            "coexist", "co-exist", "losing weight", "lose weight",
        )
    ):
        return DiagnosticPlan(
            symptom="The kick loses audibility when the bass plays.",
            issue_type="Usually a technical interaction, but the preferred kick/bass balance is a creative choice.",
            hypotheses=(
                Hypothesis(
                    "Overlapping fundamentals or excessive bass sustain",
                    "Both parts may be occupying the same low-frequency time window, so level alone cannot preserve the kick's outline.",
                    "Level-match them, then mute the bass only on kick hits. If the kick immediately returns, overlap is the primary issue.",
                    "Choose which part owns the deepest octave, then create space with arrangement, envelope shaping, or modest frequency-specific ducking.",
                ),
                Hypothesis(
                    "Polarity, phase, or timing interaction",
                    "If the combined low end becomes smaller rather than merely busier, cancellation or misalignment is plausible.",
                    "Flip polarity on one source and nudge timing only while monitoring the summed low end in mono. Keep the version that gains weight without changing level.",
                    "Retain the better alignment; do not use a large EQ cut to compensate for cancellation.",
                ),
                Hypothesis(
                    "The kick lacks an audible cue above the sub range",
                    "A kick can have enough sub energy yet vanish on small speakers if its transient/body is masked.",
                    "Low-pass the mix temporarily, then listen again without the low-pass. If the kick exists only in the low-passed version, its upper cue is being hidden.",
                    "Improve the kick's envelope or a narrow body/attack area before adding more sub level.",
                ),
            ),
            verification="A/B at matched loudness in mono and on a small speaker: the kick should read on every hit without making the bass feel disconnected.",
            question="Are the kick and bass overlapping on every hit, or only on particular notes?",
        )

    if "vocal" in text and "thin" in text and any(term in text for term in ("harsh", "sibil", "brittle", "bright")):
        return DiagnosticPlan(
            symptom="The vocal is described as both thin and harsh.",
            issue_type="This is partly subjective, but the source, masking, and dynamics can be tested objectively before tonal processing.",
            hypotheses=(
                Hypothesis(
                    "The recording is naturally bright or underweight",
                    "Mic distance, angle, room reflections, and performance can create a thin/forward capture before any mix processing.",
                    "Compare the unprocessed vocal to the processed chain at matched loudness. If the problem is already present dry, investigate the capture before adding more processing.",
                    "For the next take, test a slightly closer or more off-axis position and control reflections; for this mix, use restrained corrective tone shaping rather than broad boosts.",
                ),
                Hypothesis(
                    "Compression or saturation is exposing upper-mid energy",
                    "Dynamics processing can make consonants and 2–6 kHz energy feel more constant, while reducing the body-to-presence contrast.",
                    "Bypass compression and saturation separately. If harshness appears only when one is active, match output level and adjust its envelope or amount before EQ.",
                    "Use slower or lighter control, or targeted dynamic reduction only where the harshness occurs.",
                ),
                Hypothesis(
                    "The mix is masking the vocal's body",
                    "A vocal can sound thin in context even when it is balanced solo because instruments occupy its body range or because the vocal is simply too quiet.",
                    "Toggle the competing instruments or a vocal-body band while listening in the full mix, not solo. If the vocal body returns, solve the relationship rather than boosting the vocal blindly.",
                    "Create a small, dynamic pocket in the competing part or rebalance first; then reassess whether the vocal needs tonal work.",
                ),
            ),
            verification="Compare dry/processed and in-mix/solo at matched loudness. The vocal should gain stability and body without becoming dull, lisped, or detached from the track.",
            question="Does the harshness exist on the raw recording, or does it arrive after compression, saturation, or the full mix?",
        )

    if "vocal" in text and any(term in text for term in ("wide", "wider", "width", "widen")) and any(term in text for term in ("mud", "muddy", "congested")):
        return DiagnosticPlan(
            symptom="The goal is a wider vocal without adding mud or losing a stable centre.",
            issue_type="Width is a creative choice, but low-mid buildup and mono compatibility are technical constraints that should be checked before committing to a widening effect.",
            hypotheses=(
                Hypothesis("The lead and width layers are competing in the low mids", "Wide doubles, choruses, and reverb can make the vocal feel larger while their low-mid energy masks the central lead.", "Keep the lead vocal central, then high-pass the wide doubles and effect returns temporarily. Compare the full mix at matched loudness.", "Leave the lead's body in the centre and use filtered doubles/returns only for the width they add."),
                Hypothesis("The widening process is not mono-safe", "Haas delay and some modulation can create impressive side energy that partially cancels when summed to mono.", "Collapse to mono and bypass the Haas delay, doubler, and stereo return one at a time. Listen for vocal level, diction, and phasey tone—not only width.", "Use panned performances or a mono-compatible doubler for the important vocal role; keep risky width lower or on an auxiliary texture."),
                Hypothesis("Wet level or decay is filling the vocal's gaps", "Long, full-band effects can blur phrases even when their tone is attractive in solo.", "Shorten and high-pass the reverb/delay return, then compare the spaces between phrases in context.", "Automate the return or use a shorter filtered effect so the vocal stays wide without washing over the mix."),
            ),
            verification="In stereo the vocal should feel wide, while in mono its centre, intelligibility, and approximate level remain stable and the low-mid range stays clear.",
            question="Are you widening a double, a reverb/delay return, or the lead vocal itself?",
        )

    if any(term in text for term in ("muddy", "mud", "boxy")) and any(term in text for term in ("mix", "master", "bus", "track")):
        return DiagnosticPlan(
            symptom="The mix is described as muddy or congested.",
            issue_type="A technical balance problem may be present, while the desired amount of warmth is a creative judgement.",
            hypotheses=(
                Hypothesis(
                    "Too many sustained parts share the low-mid range",
                    "Congestion usually comes from simultaneous arrangement and envelope overlap, not one universally bad frequency.",
                    "Mute one sustained element at a time during the dense section. If clarity returns when a part leaves, that relationship is more important than a master-bus EQ move.",
                    "Reduce overlap through arrangement, octave, sound choice, or a small contextual cut on the competing source.",
                ),
                Hypothesis(
                    "Low-frequency buildup or reverb tails are clouding the body range",
                    "Uncontrolled lows and long ambience both accumulate energy between notes.",
                    "Bypass reverbs/delays, then high-pass only their returns temporarily. Separately compare the mix with the bass/kick muted.",
                    "Shorten/filter the return or clean the source that creates the buildup; avoid applying a broad master cut first.",
                ),
                Hypothesis(
                    "Monitoring level or room response is exaggerating the problem",
                    "Low-mid decisions made loudly or in an untreated room can be misleading.",
                    "Check quietly in mono and on headphones or a known alternate system before committing to a large correction.",
                    "Use the result as a translation check, then make the smallest move that survives both systems.",
                ),
            ),
            verification="At matched loudness, the dense section should separate more clearly while retaining weight when the mix is quiet and in mono.",
            question="Is the mud present throughout, or does it arrive only in the busiest section?",
        )

    if any(term in text for term in ("phasey", "phase", "mono", "collapse")) and any(
        term in text for term in ("mix", "wide", "width", "stereo", "vocal", "drum")
    ):
        return DiagnosticPlan(
            symptom="The stereo image is unstable or loses energy in mono.",
            issue_type="This is a measurable technical compatibility problem; how wide the mix should be remains creative.",
            hypotheses=(
                Hypothesis(
                    "A widening process is creating phase-dependent side energy",
                    "Some stereo effects sound impressive in stereo precisely because they rely on differences that cancel in mono.",
                    "Bypass wideners, choruses, Haas delays, and stereo reverbs one at a time while collapsing to mono.",
                    "Keep width on elements that survive the fold-down; narrow or replace the process that causes the loss.",
                ),
                Hypothesis(
                    "Multiple microphones or layered sources are misaligned",
                    "Timing differences between related signals can cause frequency-dependent cancellation.",
                    "Solo the related pair, check polarity, then make tiny alignment changes while monitoring mono—not the full mix.",
                    "Choose the alignment that improves the actual source tone; do not align unrelated layers merely by waveform appearance.",
                ),
            ),
            verification="Mono should retain the musical role and approximate level of the element, even if the deliberate stereo spread becomes smaller.",
            question="Does the loss begin when a specific widening effect or layered/miked source is enabled?",
        )

    if any(term in text for term in ("crushed", "too loud", "over-compressed", "overcompressed", "distorted master")) and any(
        term in text for term in ("master", "lufs", "limiter", "loudness")
    ):
        return DiagnosticPlan(
            symptom="The master may be over-driven or dynamically over-controlled.",
            issue_type="Clipping and true-peak overs are technical; the desired loudness is genre and release-context dependent.",
            hypotheses=(
                Hypothesis(
                    "The limiter or clipper is being asked to solve a mix-balance problem",
                    "Dense low end, sharp transients, or harsh upper mids force more gain reduction and make loudness costly.",
                    "Level-match a less-limited version. If it feels clearer, inspect the mix balance and transient sources before pushing the master harder.",
                    "Return to the mix for the limiting trigger; reduce only the source of excess energy rather than globally flattening the master.",
                ),
                Hypothesis(
                    "A specific stage is clipping or overshooting",
                    "Audible distortion can originate before the final limiter, and sample peak alone does not prove true-peak safety.",
                    "Check each gain stage and use a true-peak meter or a controlled oversampling check. Bypass stages one at a time to locate the first audible change.",
                    "Lower or rebalance that stage, then re-level-match before deciding on a final ceiling.",
                ),
            ),
            verification="The quieter matched version should not feel subjectively weaker because of distortion or pumping; confirm on a second playback system and with true-peak measurement.",
            question="Do you hear distortion/pumping, or is the concern only the integrated LUFS number?",
        )

    if any(term in text for term in ("hum", "buzz", "noisy recording", "recording noise")):
        return DiagnosticPlan(
            symptom="The recording has unwanted noise or a hum/buzz.",
            issue_type="Usually a technical fault; the correct repair depends on whether it is present before the DAW, tied to mains frequency, or caused by the room/source.",
            hypotheses=(
                Hypothesis("Ground-loop or power-related hum", "A stable tonal hum commonly enters through a grounding, power, or connection path.", "Record ten seconds with the mic/input disconnected, then reconnect one part of the chain at a time. Note whether the noise changes with laptop power or a different outlet.", "Fix the physical connection or power path first; a notch is cleanup, not a cure for a persistent electrical fault."),
                Hypothesis("Gain staging or a noisy source", "High preamp gain can reveal self-noise, room noise, or an underpowered source.", "Compare the noise floor with the source muted, then with normal performance level. Check whether turning down an unnecessary gain stage improves the ratio.", "Improve capture level, distance, or source noise before relying on a gate/denoiser."),
            ),
            verification="Re-record a short silent section and compare at the same monitoring level; the noise should reduce without removing intelligibility or natural room tone.",
            question="Is the noise a steady low hum/buzz, broadband hiss, or only audible while the performer is present?",
        )

    if "vocal" in text and any(term in text for term in ("buried", "lost in the mix", "can\'t hear", "cannot hear", "too far back", "sits too far back")):
        return DiagnosticPlan(
            symptom="The vocal is not consistently audible in the full mix.",
            issue_type="Usually a balance or masking relationship; the desired vocal prominence is a creative decision.",
            hypotheses=(
                Hypothesis("Arrangement or frequency masking", "Competing instruments may occupy the vocal's intelligibility/body range only in dense sections.", "Mute or turn down likely competitors during the problem phrase. If the words return without changing the vocal, solve the relationship first.", "Create a small contextual pocket with arrangement, automation, or dynamic EQ on the competing part."),
                Hypothesis("Uneven vocal level or compression envelope", "Words can disappear when phrase level varies or compression reacts too slowly/quickly for the performance.", "Listen to the vocal against the mix while bypassing compression, then try a simple phrase ride. Compare at matched output.", "Use clip gain or automation before asking a compressor to correct every phrase."),
            ),
            verification="At low playback level, the lyric should remain intelligible without the vocal becoming unnaturally loud in sparse sections.",
            question="Does it disappear only in the chorus/dense sections, or throughout the whole song?",
        )

    if any(term in text for term in ("over-compressed", "overcompressed", "pumping", "squashed")) and "vocal" in text:
        return DiagnosticPlan(
            symptom="The vocal may be losing natural dynamic movement under compression.",
            issue_type="Partly technical (audible pumping, lost transients) and partly creative (how controlled the vocal should feel).",
            hypotheses=(
                Hypothesis("Too much gain reduction or unsuitable release", "Fast recovery can make breaths and room rise between words; excessive reduction flattens phrase shape.", "Level-match the bypass, then compare less gain reduction and a slower release during the same phrase.", "Use the lightest control that keeps the lyric stable."),
                Hypothesis("The compressor is correcting level swings that automation should handle", "One setting rarely follows every phrase musically.", "Bypass compression and make two small clip-gain or fader rides. If that sounds more natural, the issue is level management.", "Ride phrases before applying gentle compression."),
            ), verification="At matched loudness, consonants and phrase endings should breathe naturally without words jumping out.", question="Does the pumping happen between words, or do whole phrases feel flat?",
        )

    if (re.search(r"\bflat\b", text) or any(term in text for term in ("no depth", "lacks depth", "two-dimensional", "2d"))) and any(
        term in text for term in ("mix", "song", "production", "track")
    ):
        return DiagnosticPlan(
            symptom="The mix is described as flat or lacking front-to-back depth.",
            issue_type="Depth is partly an aesthetic choice, but level, arrangement, ambience, and dynamics relationships can be tested before adding more reverb.",
            hypotheses=(
                Hypothesis("Everything is competing at a similar level and density", "When every part is continuously present and similarly loud, the ear has few foreground/background cues; the resulting balance gives the ear little foreground/background contrast.", "Mute or lower supporting parts during the vocal or lead phrase, then compare at matched loudness with a suitable reference. If depth appears immediately, the first problem is balance, arrangement, or automation.", "Create intentional foreground, midground, and background roles with level balance, density, and phrase-based automation."),
                Hypothesis("Ambience is masking rather than locating sources", "Long or unfiltered shared reverbs can push all sources into the same cloudy plane instead of creating distance.", "Bypass each reverb/delay return, then reintroduce it one at a time with its return high-passed and shortened. Listen in context, not solo.", "Use shorter, filtered, or selectively automated ambience; reserve longer tails for elements intended to sit behind the lead."),
                Hypothesis("Dynamics and transient contrast are too uniform", "Heavy bus control or flattened source envelopes reduce near/far and punch/soft contrast.", "Level-match the mix with bus compression bypassed, and compare one foreground transient against its supporting layer.", "Restore contrast with lighter bus control or source-level envelope/automation changes before widening everything."),
            ),
            verification="At the same loudness, the lead should remain clearly foreground while supporting elements occupy believable positions without the mix becoming quieter or wetter overall.",
            question="Does the flatness come from the arrangement itself, or only after the bus processing and reverbs are enabled?",
        )

    if any(term in text for term in ("translation", "translate", "car", "small speakers", "phone speaker", "headphones")) and any(
        term in text for term in ("mix", "master", "bass", "low end", "song", "track")
    ):
        return DiagnosticPlan(
            symptom="The mix does not translate consistently between playback systems; this is a translation check, not a single-speaker verdict.",
            issue_type="Inconsistent playback is a technical delivery problem; which reference systems matter most depends on the listener and release context.",
            hypotheses=(
                Hypothesis("The balance relies on frequencies a target system cannot reproduce", "Small speakers omit sub-bass, while room and headphone responses can exaggerate different bands.", "Compare a reference and the mix at matched loudness on two systems. Low-pass and high-pass briefly to identify whether the musical role survives outside the deepest octave.", "Give important low-end parts an audible harmonic/body cue and rebalance against a suitable reference rather than simply adding sub."),
                Hypothesis("A monitoring or room-specific decision is being over-corrected", "A mix can sound right in one room but wrong elsewhere when the room response drives large tonal moves.", "Check quietly in mono and on one known alternate system before making a large EQ correction. Note only differences that repeat across checks.", "Make smaller changes that improve repeated evidence; do not chase a single unfamiliar speaker."),
                Hypothesis("The master changes disproportionately with level or codec/playback processing", "Very dense, clipped, or phase-sensitive material can react differently on consumer playback.", "Level-match a less-driven export and compare mono compatibility and peaks; if possible, audition the actual delivery encode.", "Fix the mix or limiting trigger that fails the comparison, then verify the final delivery version rather than a pre-export master only."),
            ),
            verification="The lead, groove, and low-end role should remain intelligible at low volume, in mono, and on the chosen target systems—even if tonal detail differs.",
            question="What changes most between systems: vocal level, bass/kick relationship, harshness, or stereo width?",
        )

    if any(term in text for term in ("weak low end", "low end sounds weak", "low end is weak", "no low end", "lacks low end", "thin low end", "bass is weak", "sub is weak")):
        return DiagnosticPlan(
            symptom="The low end is described as weak or absent.",
            issue_type="Low-frequency level can be measured, but whether the mix needs more weight is contextual; first establish whether the musical role is missing, masked, or simply inaudible on the monitor.",
            hypotheses=(
                Hypothesis("The arrangement or sound choice has no stable low-frequency owner", "If kick, bass, and sub all have short or inconsistent fundamentals, adding a broad boost may create energy without a clear foundation.", "Solo kick and bass in the section, then listen in mono at low volume. Identify which one should carry the lowest octave and whether it sustains through the groove.", "Choose one primary low-frequency owner and adjust sound choice, octave, or note length before applying large EQ boosts."),
                Hypothesis("Fundamentals are masked or cancelling", "A low end can feel weak when sources overlap in time or sum destructively, even if meters show plenty of level.", "Mute the bass on kick hits, then compare polarity and very small timing changes in mono at matched loudness.", "Keep the alignment/arrangement that restores weight; only then make modest source-specific tonal changes."),
                Hypothesis("The part lacks a harmonic cue for target playback", "Sub-only energy disappears on phones and many small speakers, so the role may be present but not audible outside the studio.", "High-pass the mix temporarily and compare against a matched reference. If the bass role vanishes entirely, it needs an audible upper cue.", "Add controlled harmonics or body to the source, then verify that the sub has not become louder merely because the mix is louder."),
            ),
            verification="At matched loudness, the groove should retain weight in mono and on a small speaker, while the deepest octave remains controlled on full-range playback.",
            question="Is the low end weak everywhere, or only on small speakers and in certain notes?",
        )

    if any(term in text for term in ("drums lack punch", "drums are flat", "flat drums", "weak drums", "drums weak", "drums have no punch")):
        return DiagnosticPlan(
            symptom="The drums are described as flat or lacking punch.",
            issue_type="Punch is an audible relationship between transient, body, groove, and surrounding arrangement—not a fixed compressor setting.",
            hypotheses=(
                Hypothesis("The transient is being reduced by processing or source layering", "Fast compression, limiting, clipping, or misaligned layers can remove the initial contrast that makes a hit feel punchy.", "Level-match and bypass each dynamics stage and any drum layers one at a time. For layers, check polarity and start alignment while listening to the combined drum in mono.", "Keep only processing/layers that improve the actual hit; use slower or lighter control when the transient returns on bypass."),
                Hypothesis("Tails and sustained instruments are obscuring the groove", "Punch depends on a clear gap after the hit; long samples, reverbs, and dense instruments can fill it.", "Shorten a drum tail or mute the relevant ambience during one bar. If the groove tightens without changing peak level, the issue is time-domain masking.", "Trim/shape tails or automate the competing sustain rather than boosting the entire drum bus."),
                Hypothesis("The drum is not carrying a readable body on the intended system", "A sharp click alone may read as small, while too much low body can disappear on smaller playback.", "Compare the drum against a matched reference at low volume and briefly high-pass/low-pass to find whether attack or body is missing.", "Use source choice or a narrow, contextual body/attack change only after the masking and transient tests."),
            ),
            verification="At matched loudness, the groove should feel more decisive at low volume and in mono without making the drums clicky, brittle, or disconnected from the music.",
            question="Do the drums lose punch only after bus/master processing, or even with the raw samples in the arrangement?",
        )

    if "vocal" in text and any(term in text for term in ("sibilant", "sibilance", "ess sounds", "esses", "too much s", "too many s")):
        return DiagnosticPlan(
            symptom="The vocal has excessive or distracting sibilance.",
            issue_type="Sibilance is an audible and partly aesthetic issue. The goal is intelligibility without dulling consonants or changing the performer’s character.",
            hypotheses=(
                Hypothesis("The capture emphasises sibilants", "Microphone voicing, distance, angle, room reflections, and vocal delivery can make consonants prominent before processing.", "Compare the raw vocal and the processed chain at matched loudness, focusing on several S/T/CH sounds. If it is present dry, identify whether it changes with mic angle or distance on a test take.", "For a future take, use modest off-axis adjustment or distance control; for the current take, use the smallest targeted correction that preserves diction."),
                Hypothesis("Compression, saturation, or bright EQ is making consonants too constant", "Dynamics and harmonic processing can bring quiet consonants forward and make a narrow harsh band sound continuous.", "Bypass each processor separately at matched output. If the sibilance falls when one stage is bypassed, adjust its amount, envelope, or tonal balance before adding a de-esser.", "Reduce the stage’s contribution or use targeted dynamic control only when the consonants occur."),
                Hypothesis("The vocal is being made brighter to overcome masking", "A vocal can be over-brightened when competing instruments hide its intelligibility in dense sections.", "Mute or automate likely competitors during the problem phrase. If the words stay clear with less vocal brightness, the relationship—not the vocal alone—is the issue.", "Create a contextual pocket or rebalance the competing source, then reassess the vocal without permanently over-de-essing it."),
            ),
            verification="A/B at matched loudness on words with S/T/CH: the lyric should stay clear while the vocal remains natural, not lisped, dull, or suddenly tucked behind the mix.",
            question="Is the sibilance already obvious on the raw take, or does it arrive after your vocal processing and in the dense sections?",
        )

    if any(term in text for term in ("roomy recording", "room reflections", "room sound", "bad room", "echoey recording", "boxy room")):
        return DiagnosticPlan(
            symptom="The recording may contain distracting room reflections or room coloration.",
            issue_type="Early reflections and noise are technical capture constraints; how much room character is desirable remains a creative choice.",
            hypotheses=(
                Hypothesis("Early reflections are colouring the source", "Nearby hard surfaces can create short, comb-filter-like colouration that changes with mic position and is difficult to remove cleanly later.", "Record a short spoken/clapped test while moving the microphone and performer slightly away from nearby walls. Compare the dry takes at matched level rather than judging a reverb-heavy mix.", "Choose the position with the least distracting colouration; add portable absorption only where it solves the reflected path."),
                Hypothesis("Microphone distance is capturing more room than direct source", "Greater distance lowers the direct-to-room ratio, especially for quieter performers or sources.", "Make a safe close-versus-current-distance test at the same input gain and performance level. Check plosives/proximity separately so one problem is not exchanged for another.", "Use the closer, better-controlled position or a different microphone pattern if it improves the direct-to-room balance."),
                Hypothesis("The mix processing is exaggerating existing room tone", "Compression, gating, expansion, and reverb can make room tails more apparent even when the raw capture is acceptable.", "Compare raw and processed phrases at matched loudness, then bypass dynamics and ambience separately. Listen to the gaps between words/notes.", "Adjust the process that raises the room tail before applying aggressive denoising or broad EQ."),
            ),
            verification="The revised capture or processing should sound more direct and stable without becoming unnaturally dry, gated, or overly close.",
            question="Does the room sound appear on the raw recording between phrases, or only after compression, gating, or added ambience?",
        )

    if re.search(r"\b(?:what(?:'s|\s+is)\s+wrong\s+with\s+(?:my|this|the)\s+mix|analyse\s+(?:my|this|the)\s+mix)\b", text):
        return DiagnosticPlan(
            symptom="No specific audible symptom has been supplied for the mix.",
            issue_type="A bus snapshot can identify limited technical indicators, but it cannot diagnose arrangement, individual tracks, routing, plug-ins, automation, or what sounds wrong without a render/section and a symptom.",
            hypotheses=(
                Hypothesis("The main issue may be a relationship, not a single processor", "Balance, arrangement density, masking, timing, and dynamics can produce a similar broad impression while needing different interventions.", "Name the moment and symptom: for example, ‘vocal disappears in chorus’, ‘kick vanishes with bass’, ‘harsh after limiter’, or ‘collapses in mono’.", "Start from that concrete symptom and test the smallest reversible relationship first."),
                Hypothesis("A current measurement may reveal a technical boundary", "Peak, clipping, correlation, and loudness data can flag what deserves checking, but cannot identify the musical cause on their own.", "Use the current measured indicators to choose a focused check—gain stage for clipping, mono fold-down for correlation, or a rendered Mix Review for broader analysis.", "Treat any flag as a priority for inspection, not proof that it is the audible problem."),
                Hypothesis("The monitoring context may be shaping the judgement", "A mix can feel different across room, headphones, mono, level, and consumer playback.", "Compare the same dense section quietly, in mono, and on one known alternate system before making broad changes.", "Keep only changes that improve the stated symptom across the relevant playback checks."),
            ),
            verification="After identifying one symptom and testing one reversible change, the result should improve that symptom at matched loudness without making another range, section, or playback system worse.",
            question="Which exact moment is failing first, and is the problem balance, low end, harshness, punch, width, depth, or loudness?",
        )

    if (
        any(term in text for term in ("harsh mix", "mix is harsh", "brittle mix", "mix is brittle", "too bright mix", "mix too bright"))
        or ("mix" in text and any(term in text for term in ("harsh", "brittle", "bright")) and any(term in text for term in ("sounds", "too", "excessively")))
    ):
        return DiagnosticPlan(
            symptom="The overall mix is described as harsh, brittle, or too bright.",
            issue_type="The listening judgement is partly aesthetic, but persistent upper-mid build-up, dynamics processing, and monitoring conditions can be tested objectively before applying a broad master cut.",
            hypotheses=(
                Hypothesis("Multiple sources are accumulating upper-mid or high-frequency energy", "Vocals, cymbals, guitars, synths, distortion, and bright ambience can each be acceptable alone but become fatiguing together.", "Mute or lower likely contributors one at a time during the harshest section, then compare at matched loudness. Identify the smallest number of contributors that changes the symptom.", "Address the contributing source or arrangement relationship first; use a broad bus move only if the problem remains after source checks."),
                Hypothesis("Dynamics, clipping, saturation, or limiting is making brightness more constant", "Heavy control can flatten transient contrast and make high-frequency detail feel relentless even when static EQ is reasonable.", "Level-match and bypass bus compression, saturation, clipping, and limiting stages one at a time. Listen for whether fatigue changes without a large tonal shift.", "Reduce or retime the stage that intensifies the symptom before cutting highs globally."),
                Hypothesis("Monitoring level or playback response is exaggerating the impression", "Loud monitoring and system-specific resonances can overstate brightness and lead to over-correction.", "Check quietly, in mono, and on one known alternate playback system; compare to a matched reference at the same perceived level.", "Keep only a correction that improves repeated observations across the relevant systems."),
            ),
            verification="At matched loudness, the dense section should feel less fatiguing while retaining articulation, air, and the intended creative brightness.",
            question="Does the harshness arrive only in the busiest section or only after bus/master processing is enabled?",
        )

    if any(term in text for term in ("mix is squashed", "mix sounds squashed", "mix has no dynamics", "mix lacks dynamics", "overcompressed mix", "mix is overcompressed")):
        return DiagnosticPlan(
            symptom="The mix is described as squashed or lacking dynamic movement.",
            issue_type="Dynamics are partly a creative choice, but audible pumping, lost transient contrast, and stage overload can be tested. A crest-factor number alone is not a universal quality score.",
            hypotheses=(
                Hypothesis("Bus/master dynamics control is reducing transient and phrase contrast", "Compression, limiting, clipping, and saturation can make a dense mix more constant, especially when several stages share the workload.", "Level-match the bypass of each bus/master dynamics stage during one busy section. Compare transient clarity, phrase movement, and fatigue—not apparent loudness.", "Reduce, retime, or redistribute only the stage that removes the desired movement."),
                Hypothesis("The arrangement or source envelopes are already continuously dense", "If every part sustains through the same moments, master processing may be reacting to a musical-density problem rather than causing it.", "Mute or shorten one sustained contributor during the dense section before touching the master chain. If movement returns, the relationship is the first fix.", "Create space with arrangement, automation, or source envelopes; then reassess how much bus control is actually needed."),
                Hypothesis("Level matching is masking the real comparison", "A louder processed version often feels more exciting even when it has less punch or depth.", "Match output level within a fraction of a dB, then compare at normal and low monitoring levels.", "Choose the version that retains the intended groove and emotion at matched loudness, not the version that merely wins by level."),
            ),
            verification="At matched loudness, the mix should regain the intended punch and phrase movement without unstable peaks, loss of cohesion, or a sudden drop in perceived energy.",
            question="Do the drums/transients lose shape, do the gaps pump, or do whole phrases simply feel flat?",
        )

    return None


def render(plan: DiagnosticPlan, *, skill_level: str = "") -> list[str]:
    """Render the plan as concise user-facing diagnostic reasoning."""
    lines = [
        "Diagnosis first:",
        plan.symptom,
        "",
        "What this is:",
        plan.issue_type,
        "",
        "Most useful hypotheses to test:",
        "Ordered by plausible impact, ease of testing, and reversibility—not certainty. Start with the first low-risk discriminator, then move on only if it does not explain the symptom.",
    ]
    if skill_level == "beginner":
        lines.append("Plain-language approach: change one thing, compare it at the same volume, and keep only the change that clearly improves the symptom.")
    elif skill_level == "advanced":
        lines.append("Advanced check: preserve gain while isolating one variable; use mono, matched bypass, and stage-by-stage comparison before committing a corrective move.")
    for index, hypothesis in enumerate(plan.hypotheses, start=1):
        lines.extend(
            [
                f"{index}. {hypothesis.cause} — {hypothesis.why_plausible}",
                f"   Test: {hypothesis.test}",
                f"   If confirmed: {hypothesis.if_confirmed}",
            ]
        )
    lines.extend(["", "Verification:", plan.verification])
    if plan.question:
        lines.extend(["", "Most useful question:", plan.question])
    return lines


def rank_with_evidence(plan: DiagnosticPlan, packets: list["EvidencePacket"]) -> tuple[DiagnosticPlan, str]:
    """Reorder only when a typed fact makes one *test* more useful first.

    This intentionally never turns a measurement into a diagnosis.  The
    returned explanation says what the fact changed in the order and retains
    the plan's discriminating test and verification boundary.
    """
    facts_by_source = {
        packet.source: {fact.name: fact.value for fact in packet.facts}
        for packet in packets
    }
    facts = {
        fact.name: fact.value
        for packet in packets
        for fact in packet.facts
    }
    preferred_cause = ""
    rationale = ""
    if plan.symptom == "The master may be over-driven or dynamically over-controlled.":
        # If a fresh bus snapshot exists, it is the only source that can
        # describe the *current* bus.  An uploaded Mix Review remains useful
        # when no current snapshot exists, but must not be silently blended
        # into a fictional current render.
        master_facts = facts_by_source.get("plugin_bus_snapshot") or facts_by_source.get("mix_review_upload") or {}
        clipped = master_facts.get("clipped_samples")
        # Mix Review's established handoff uses ``true_peak_dbfs`` while
        # older callers used ``true_peak_db``.  Both are measurements of the
        # uploaded render; neither identifies an internal source of overload.
        true_peak = master_facts.get("true_peak_dbfs", master_facts.get("true_peak_db"))
        if (isinstance(clipped, (int, float)) and clipped > 0) or (
            isinstance(true_peak, (int, float)) and true_peak >= -1.0
        ):
            preferred_cause = "A specific stage is clipping or overshooting"
            source_label = "current bus" if "plugin_bus_snapshot" in facts_by_source else "uploaded render"
            rationale = f"Measured {source_label} peak/clipping evidence makes locating the first overloaded stage the most useful test first; it still does not identify that stage by itself."
    elif plan.symptom == "The low end is described as weak or absent.":
        names = str(facts.get("track_names") or "").lower()
        if "kick" in names and any(term in names for term in ("bass", "sub", "808")):
            preferred_cause = "Fundamentals are masked or cancelling"
            rationale = "The opted-in Ableton snapshot confirms both kick and bass/sub-named tracks exist, so testing their interaction is more informative first; names do not prove masking or cancellation."
    elif plan.symptom in {"The kick loses audibility when the bass plays.", "The bass loses audibility when the kick plays.", "The mix is described as muddy or congested."}:
        visibility = facts.get("stem_masking_lowest_visibility")
        stem = facts.get("stem_masking_lowest_visibility_stem")
        if isinstance(visibility, (int, float)) and isinstance(stem, str) and visibility < 0.6:
            preferred_cause = "Overlapping fundamentals or excessive bass sustain" if "kick loses" in plan.symptom else "Fundamentals are masking or cancelling"
            rationale = f"The uploaded stem analysis measured low simultaneous-masking visibility ({visibility:.2f}) for '{stem}', so testing overlap first is the most informative discriminator; it does not prove which source, frequency, timing, or processing caused the audible problem."
    elif plan.symptom == "The drums are described as flat or lacking punch.":
        score = facts.get("transient_preservation_score")
        if isinstance(score, (int, float)) and score < 0.75:
            preferred_cause = "The transient is being reduced by processing or source layering"
            rationale = f"The uploaded pre/post comparison measured a {score:.2f}/1.00 transient-preservation score, so checking processing or layer impact first is justified; the comparison cannot identify the responsible stage or prove that its change is creatively undesirable."
    elif plan.symptom == "The mix is being judged as tonally different from a chosen reference.":
        spectral_delta = facts.get("reference_largest_spectral_delta")
        spectral_band = facts.get("reference_largest_spectral_band")
        lufs_delta = facts.get("reference_lufs_delta_db")
        if isinstance(spectral_delta, (int, float)) and isinstance(spectral_band, str) and abs(spectral_delta) >= 0.04 and not (isinstance(lufs_delta, (int, float)) and abs(lufs_delta) > 1.5):
            preferred_cause = "A measured spectral difference is coming from one or a few musical relationships"
            rationale = f"The uploaded reference comparison found its largest spectral difference in {spectral_band.replace('_', ' ')} ({spectral_delta:+.3f}), so trace the contributing relationship after level matching; this comparison does not prove a cause or require matching the reference exactly."
    elif plan.symptom == "The stereo image is unstable or loses energy in mono.":
        correlation = facts.get("stereo_correlation")
        if isinstance(correlation, (int, float)) and correlation < 0.2:
            preferred_cause = "A widening process is creating phase-dependent side energy"
            rationale = "The current low bus-correlation snapshot makes a mono fold-down test of width-producing processes the most useful first check; it does not establish which process caused it."

    if not preferred_cause:
        return plan, ""
    reordered = tuple(
        sorted(plan.hypotheses, key=lambda hypothesis: hypothesis.cause != preferred_cause)
    )
    if reordered == plan.hypotheses:
        return plan, rationale
    return DiagnosticPlan(plan.symptom, plan.issue_type, reordered, plan.verification, plan.question), rationale
