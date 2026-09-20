#include "MidiGeneratorEngine.h"
#include "ScaleTable.h"

namespace
{
    constexpr int stepsPerBeat = 4; // 16th-note grid

    // Roulette-wheel sample from parallel (candidate, weight) arrays.
    template <typename T>
    T weightedPick(const std::vector<T>& candidates, const std::vector<float>& weights, juce::Random& rng)
    {
        float total = 0.0f;
        for (auto w : weights)
            total += juce::jmax(0.0f, w);

        if (total <= 0.0f)
            return candidates.front();

        float r = rng.nextFloat() * total;
        for (size_t i = 0; i < candidates.size(); ++i)
        {
            r -= juce::jmax(0.0f, weights[i]);
            if (r <= 0.0f)
                return candidates[i];
        }
        return candidates.back();
    }

    // Order-2-ish rhythm chain: next duration depends on the previous duration and the
    // emotion/scale's intensity setting (short & busy at high intensity, long & sparse
    // at low intensity), with a repetition bonus so the chain doesn't feel memoryless.
    int nextDurationSteps(int prevDurationSteps, float intensity, juce::Random& rng)
    {
        static const std::vector<int> durations = { 1, 2, 3, 4, 6, 8 };
        std::vector<float> weights;
        weights.reserve(durations.size());

        for (int d : durations)
        {
            float w = 0.0f;
            switch (d)
            {
                case 1: w = 0.15f + 0.55f * intensity; break;
                case 2: w = 0.25f + 0.30f * intensity; break;
                case 3: w = 0.10f; break;
                case 4: w = 0.25f + 0.30f * (1.0f - intensity); break;
                case 6: w = 0.15f + 0.30f * (1.0f - intensity); break;
                case 8: w = 0.10f + 0.40f * (1.0f - intensity); break;
                default: break;
            }
            if (d == prevDurationSteps)
                w *= 1.4f;
            weights.push_back(w);
        }
        return weightedPick(durations, weights, rng);
    }

    // Order-2-ish interval chain: next scale-degree step depends on the previous step
    // (voice-leading tendency: a leap tends to resolve back with a step, not another leap)
    // and favors small, stepwise motion overall, as tonal melodies typically do.
    int nextDegreeInterval(int prevInterval, int degreeMin, int degreeMax, int currentDegree, juce::Random& rng)
    {
        static const std::vector<int> candidates = { -4, -3, -2, -1, 0, 1, 2, 3, 4 };
        std::vector<int> valid;
        std::vector<float> weights;
        valid.reserve(candidates.size());
        weights.reserve(candidates.size());

        for (int iv : candidates)
        {
            int nextDegree = currentDegree + iv;
            if (nextDegree < degreeMin || nextDegree > degreeMax)
                continue;

            int a = std::abs(iv);
            float w = a == 0 ? 0.22f : a == 1 ? 0.30f : a == 2 ? 0.16f : a == 3 ? 0.10f : 0.06f;

            const bool prevWasLeap = std::abs(prevInterval) >= 2;
            const bool sameSign = (iv > 0 && prevInterval > 0) || (iv < 0 && prevInterval < 0);

            if (prevWasLeap && sameSign && a >= 2)
                w *= 0.4f; // discourage runaway leaps in one direction
            else if (!prevWasLeap && sameSign && a >= 1 && a <= 2)
                w *= 1.15f; // reward smooth continuing contour

            valid.push_back(iv);
            weights.push_back(w);
        }

        if (valid.empty())
            return 0;
        return weightedPick(valid, weights, rng);
    }

    // Converts an absolute scale-degree index (0 = root, scaleLen = root an octave up, etc.,
    // negative going down) into a MIDI pitch, wrapping through the scale's own interval table.
    int degreeToPitch(int degree, int scaleLen, const std::vector<int>& intervals, int rootNote)
    {
        int octaveIndex = degree >= 0 ? degree / scaleLen
                                       : -((-degree + scaleLen - 1) / scaleLen);
        int degreeInOctave = degree - octaveIndex * scaleLen;
        int pitch = 60 + rootNote + 12 * octaveIndex + intervals[(size_t) degreeInOctave];
        return juce::jlimit(0, 127, pitch);
    }

    // A handful of common diatonic degree-loop templates (0-indexed scale degrees), picked
    // by generation seed so the same emotion doesn't always resolve to the same progression.
    // Works for non-7-note scales too since it indexes by degree, not literal triads.
    const std::vector<int>& pickProgressionTemplate(juce::Random& rng)
    {
        static const std::vector<std::vector<int>> templates = {
            { 0, 3, 4, 3 },
            { 0, 5, 3, 4 },
            { 0, 4, 5, 3 },
            { 0, 3, 0, 4 },
        };
        return templates[(size_t) rng.nextInt((int) templates.size())];
    }
}

MidiGeneratorEngine::MidiGeneratorEngine()
    : juce::Thread("MidiGeneratorEngine")
{
    currentPattern = std::make_shared<const GeneratedPattern>();
    startThread(juce::Thread::Priority::low);
}

MidiGeneratorEngine::~MidiGeneratorEngine()
{
    stopThread(2000);
}

void MidiGeneratorEngine::requestGeneration(const GenerationParams& params)
{
    {
        const juce::SpinLock::ScopedLockType lock(paramsLock);
        pendingParams = params;
        hasPendingRequest = true;
    }
    wakeEvent.signal();
}

std::shared_ptr<const GeneratedPattern> MidiGeneratorEngine::getCurrentPattern() const
{
    const juce::SpinLock::ScopedLockType lock(patternLock);
    return currentPattern;
}

void MidiGeneratorEngine::run()
{
    juce::Random rng(juce::Time::currentTimeMillis());

    while (! threadShouldExit())
    {
        wakeEvent.wait(500);
        if (threadShouldExit())
            break;

        GenerationParams params;
        bool shouldRun = false;
        {
            const juce::SpinLock::ScopedLockType lock(paramsLock);
            if (hasPendingRequest)
            {
                params = pendingParams;
                hasPendingRequest = false;
                shouldRun = true;
            }
        }

        if (! shouldRun)
            continue;

        auto pattern = std::make_shared<GeneratedPattern>(generate(params, rng));
        {
            const juce::SpinLock::ScopedLockType lock(patternLock);
            currentPattern = pattern;
        }
    }
}

GeneratedPattern MidiGeneratorEngine::generate(const GenerationParams& params, juce::Random& rng)
{
    GeneratedPattern pattern;
    pattern.lengthBeats = juce::jlimit(1, 64, params.patternLengthBeats);

    const auto& scaleTable = ScaleTable::getAll();
    const auto& scale = scaleTable[(size_t) juce::jlimit(0, (int) scaleTable.size() - 1, params.scaleIndex)];
    const int scaleLen = (int) scale.intervals.size();

    const int octaveMin = juce::jmin(params.octaveMin, params.octaveMax);
    const int octaveMax = juce::jmax(params.octaveMin, params.octaveMax);
    const int degreeMin = octaveMin * scaleLen;
    const int degreeMax = (octaveMax + 1) * scaleLen - 1;

    const float intensity = juce::jlimit(0.0f, 1.0f, params.intensity);
    const float density = juce::jlimit(0.0f, 1.0f, params.density);
    const int velMin = juce::jmin(params.velocityMin, params.velocityMax);
    const int velMax = juce::jmax(params.velocityMin, params.velocityMax);

    const int totalSteps = pattern.lengthBeats * stepsPerBeat;

    int currentDegree = juce::jlimit(degreeMin, degreeMax, 0);
    int prevInterval = 0;
    int prevDurationSteps = -1;
    int step = 0;

    while (step < totalSteps)
    {
        const int durationSteps = juce::jmin(nextDurationSteps(prevDurationSteps, intensity, rng),
                                              totalSteps - step);
        prevDurationSteps = durationSteps;

        const bool isDownbeat = (step % stepsPerBeat) == 0;
        const bool emitNote = rng.nextFloat() < density;

        if (emitNote && durationSteps > 0)
        {
            const int interval = nextDegreeInterval(prevInterval, degreeMin, degreeMax, currentDegree, rng);
            currentDegree = juce::jlimit(degreeMin, degreeMax, currentDegree + interval);
            prevInterval = interval;

            int pitch = degreeToPitch(currentDegree, scaleLen, scale.intervals, params.rootNote);

            int velSpread = velMax - velMin;
            int velocity = velMin + (int) (rng.nextFloat() * (float) velSpread);
            if (isDownbeat)
                velocity = juce::jmin(127, velocity + juce::roundToInt(10.0f * intensity) + 5);
            velocity = juce::jlimit(1, 127, velocity);

            GeneratedNote note;
            note.pitch = pitch;
            note.velocity = velocity;
            note.startBeat = (double) step / (double) stepsPerBeat;
            note.lengthBeats = juce::jmax(0.05, (double) durationSteps / (double) stepsPerBeat * 0.85);
            pattern.notes.push_back(note);
        }

        step += juce::jmax(1, durationSteps);
    }

    // Chord accompaniment: one triad per harmonic-rhythm slot (a bar, or the whole
    // pattern if it's shorter than a bar), voiced a register below the melody by
    // stacking scale-degree thirds so it works for non-7-note scales too.
    const int chordSlotBeats = juce::jmin(4, pattern.lengthBeats);
    const int numChordSlots = juce::jmax(1, pattern.lengthBeats / chordSlotBeats);
    const auto& progression = pickProgressionTemplate(rng);
    const int chordOctaveOffset = (octaveMin - 1) * scaleLen;
    const int chordVelSpread = juce::jmax(1, (velMin + 20) - velMin);

    for (int slot = 0; slot < numChordSlots; ++slot)
    {
        const int degreeOffset = progression[(size_t) slot % progression.size()];
        const int chordRootDegree = chordOctaveOffset + degreeOffset;

        for (int tone : { 0, 2, 4 })
        {
            GeneratedNote chordNote;
            chordNote.pitch = degreeToPitch(chordRootDegree + tone, scaleLen, scale.intervals, params.rootNote);
            chordNote.velocity = juce::jlimit(1, 127, velMin + (int) (rng.nextFloat() * (float) chordVelSpread));
            chordNote.startBeat = (double) (slot * chordSlotBeats);
            chordNote.lengthBeats = (double) chordSlotBeats * 0.95;
            pattern.chordNotes.push_back(chordNote);
        }
    }

    return pattern;
}
