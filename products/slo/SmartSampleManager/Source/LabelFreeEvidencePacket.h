#pragma once

#include <juce_core/juce_core.h>

#include <set>

// Read-only bridge for the Python label-free evidence packet.  This type is
// intentionally separate from SampleItem/AbletonTaxonomy: a packet contains
// suggestions and measurements, never an approved semantic label or an
// instruction to rename/write a file.
namespace SloLabelFreeEvidence {

struct Segment
{
    juce::String suggestion;
    juce::String status;
    double startSeconds = 0.0;
    double endSeconds = 0.0;
    double score = 0.0;
    double margin = 0.0;
};

struct ClusterDiscovery
{
    int clusterId = -1;
    int clusterSize = 0;
    juce::String status;
};

struct Row
{
    juce::String path;
    juce::String reviewState;
    juce::String domainSuggestion;
    juce::String ensembleSuggestion;
    juce::String specialistSuggestion;
    double specialistScore = 0.0;
    bool hasSpecialist = false;
    juce::String candidateFilename;
    juce::String nameState;
    bool hasNameCandidate = false;
    juce::String fusionDecision;
    juce::String fusionCandidateLabel;
    juce::String domainCandidateLabel;
    juce::String fusionCandidateScope;
    bool hasFusionDecision = false;
    double oodNoveltyScore = 0.0;
    bool hasOodNovelty = false;
    bool oodOverride = false;
    double modelAgreement = 0.0;
    int nScoredWindows = 0;
    juce::Array<Segment> segments;
    bool hasDomainRoute = false;
    bool hasPhysicalEvidence = false;
    bool hasSegmentEvidence = false;
    ClusterDiscovery clusterDiscovery;
    bool hasClusterDiscovery = false;
    juce::String retrievalCandidateLabel;
    double retrievalSimilarity = 0.0;
    juce::String retrievalStatus;
    bool hasRetrievalEvidence = false;
    // Optional native FFT sidecar evidence. These are measurements and
    // explainable review hints only; they are never semantic labels.
    bool hasFftEvidence = false;
    double fftDurationSeconds = 0.0;
    double fftSustainRatio = 0.0;
    double fftLowBandRatio = 0.0;
    double fftMidBandRatio = 0.0;
    double fftHighBandRatio = 0.0;
    double fftFluxMean = 0.0;
    double fftFluxStd = 0.0;
    double fftFluxPeakRate = 0.0;
    juce::StringArray fftCandidateLanes;
};

struct Packet
{
    juce::String methodVersion;
    int nRows = 0;
    int domainCoverage = 0;
    int physicalCoverage = 0;
    int segmentCoverage = 0;
    int nameCandidateCoverage = 0;
    int fusedDecisionCoverage = 0;
    int clusterDiscoveryCoverage = 0;
    int retrievalCoverage = 0;
    int fftCoverage = 0;
    juce::Array<Row> rows;
};

struct ParseResult
{
    bool success = false;
    juce::String error;
    Packet packet;
};

namespace detail {

inline bool isNull(const juce::var& value)
{
    return value.isVoid();
}

inline bool readOnlySafety(const juce::var& object)
{
    if (!object.isObject()) return false;
    const auto safety = object.getProperty("safety", juce::var());
    if (!safety.isObject()) return false;
    return static_cast<bool>(safety.getProperty("read_only", false))
        && !static_cast<bool>(safety.getProperty("semantic_labels_created", false))
        && !static_cast<bool>(safety.getProperty("rename_actions", false));
}

inline bool hasNoSemanticLabel(const juce::var& object)
{
    if (!object.isObject()) return false;
    return isNull(object.getProperty("semantic_label", juce::var()));
}

// Nested source rows in the Python packet inherit the packet's top-level
// safety contract and therefore do not repeat a safety object.  If a nested
// producer does provide one, honour it and fail closed on mutation flags.
inline bool evidenceObjectSafe(const juce::var& object)
{
    if (!object.isObject() || !hasNoSemanticLabel(object)) return false;
    const auto safety = object.getProperty("safety", juce::var());
    if (safety.isVoid()) return true;
    if (!safety.isObject()) return false;
    if (safety.hasProperty("read_only")
        && !static_cast<bool>(safety.getProperty("read_only", false))) return false;
    return !static_cast<bool>(safety.getProperty("semantic_labels_created", false))
        && !static_cast<bool>(safety.getProperty("semantic_label_created", false))
        && !static_cast<bool>(safety.getProperty("rename_actions", false))
        && !static_cast<bool>(safety.getProperty("rename_action", false))
        && !static_cast<bool>(safety.getProperty("source_audio_modified", false))
        && !static_cast<bool>(safety.getProperty("source_modified", false));
}

inline bool finite(double value)
{
    return juce::juce_isfinite(value);
}

inline bool safeCandidateFilename(const juce::var& value)
{
    if (!value.isString()) return false;
    const auto text = value.toString().trim();
    if (text.isEmpty() || text.length() > 255 || text == "." || text == "..") return false;
    return !text.containsChar('/') && !text.containsChar('\\')
        && !text.containsChar('\n') && !text.containsChar('\r');
}

inline bool safeCandidateLabel(const juce::var& value)
{
    if (!value.isString()) return false;
    const auto text = value.toString().trim();
    if (text.isEmpty() || text.length() > 256) return false;
    return !text.containsChar('\n') && !text.containsChar('\r');
}

} // namespace detail

inline ParseResult parse(const juce::File& file, int maxRows = 50000,
                         int maxSegmentsPerRow = 1024)
{
    ParseResult result;
    if (maxRows < 1 || maxSegmentsPerRow < 1) {
        result.error = "invalid packet limits";
        return result;
    }
    if (!file.existsAsFile()) {
        result.error = "evidence packet does not exist";
        return result;
    }
    constexpr juce::int64 kMaxPacketBytes = 256 * 1024 * 1024;
    if (file.getSize() <= 0 || file.getSize() > kMaxPacketBytes) {
        result.error = "evidence packet size is outside the safety limit";
        return result;
    }

    const auto root = juce::JSON::parse(file.loadFileAsString());
    if (!root.isObject()) {
        result.error = "evidence packet is not a JSON object";
        return result;
    }
    if (root.getProperty("record_type", juce::var()).toString()
            != "slo_label_free_evidence_packet") {
        result.error = "unexpected evidence packet record type";
        return result;
    }
    if (!detail::readOnlySafety(root)) {
        result.error = "evidence packet is not read-only";
        return result;
    }

    const auto rowsValue = root.getProperty("rows", juce::var());
    const auto* rows = rowsValue.getArray();
    if (rows == nullptr || rows->size() > maxRows) {
        result.error = "evidence packet row count is invalid";
        return result;
    }

    result.packet.methodVersion = root.getProperty("method_version", juce::var()).toString();
    result.packet.nRows = static_cast<int>(rows->size());
    const auto coverage = root.getProperty("coverage", juce::var());
    if (coverage.isObject()) {
        result.packet.domainCoverage = static_cast<int>(coverage.getProperty("domain_route", 0));
        result.packet.physicalCoverage = static_cast<int>(coverage.getProperty("physical", 0));
        result.packet.segmentCoverage = static_cast<int>(coverage.getProperty("segments", 0));
        result.packet.nameCandidateCoverage = static_cast<int>(coverage.getProperty("name_candidate", 0));
        result.packet.fusedDecisionCoverage = static_cast<int>(coverage.getProperty("fused_decision", 0));
        result.packet.clusterDiscoveryCoverage = static_cast<int>(coverage.getProperty("cluster_discovery", 0));
        result.packet.retrievalCoverage = static_cast<int>(coverage.getProperty("retrieval", 0));
        result.packet.fftCoverage = static_cast<int>(coverage.getProperty("fft_evidence", 0));
    }

    std::set<std::string> seenPaths;
    for (const auto& rowValue : *rows) {
        if (!detail::evidenceObjectSafe(rowValue)) {
            result.error = "evidence row contains a semantic label or is invalid";
            return result;
        }
        Row row;
        row.path = rowValue.getProperty("path", juce::var()).toString();
        row.reviewState = rowValue.getProperty("review_state", juce::var()).toString();
        if (row.path.isEmpty() || !juce::File::isAbsolutePath(row.path)
            || (row.reviewState != "suggestion_review_required"
                && row.reviewState != "review_required")) {
            result.error = "evidence row path must be absolute and review state must be valid";
            return result;
        }
        if (!seenPaths.insert(row.path.toStdString()).second) {
            result.error = "evidence packet contains duplicate paths";
            return result;
        }

        const auto ensemble = rowValue.getProperty("ensemble", juce::var());
        if (!detail::evidenceObjectSafe(ensemble)) {
            result.error = "ensemble evidence is not read-only";
            return result;
        }
        row.ensembleSuggestion = ensemble.getProperty("ensemble_suggestion", juce::var()).toString();
        row.modelAgreement = static_cast<double>(ensemble.getProperty("model_agreement", 0.0));
        if (!detail::finite(row.modelAgreement) || row.modelAgreement < 0.0 || row.modelAgreement > 1.0) {
            result.error = "ensemble agreement is invalid";
            return result;
        }

        const auto route = rowValue.getProperty("domain_route", juce::var());
        if (!detail::isNull(route)) {
            if (!detail::evidenceObjectSafe(route)) {
                result.error = "domain-route evidence is not read-only";
                return result;
            }
            row.hasDomainRoute = true;
            row.domainSuggestion = route.getProperty("domain_suggestion", juce::var()).toString();
        }

        const auto specialist = rowValue.getProperty("specialist", juce::var());
        if (!detail::isNull(specialist)) {
            if (!detail::evidenceObjectSafe(specialist)) {
                result.error = "specialist evidence is not read-only";
                return result;
            }
            const auto specialistStatus = specialist.getProperty("specialist_status", juce::var()).toString();
            if (specialistStatus != "scored" && specialistStatus != "not_dispatched") {
                result.error = "specialist status is invalid";
                return result;
            }
            row.hasSpecialist = specialistStatus == "scored";
            row.specialistSuggestion = specialist.getProperty("specialist_suggestion", juce::var()).toString();
            const auto specialistScore = specialist.getProperty("specialist_score", juce::var());
            // Undispatched/abstained routes legitimately have no score.  Keep
            // the native value at its neutral default while still failing
            // closed on malformed scored evidence.
            row.specialistScore = specialistScore.isVoid() ? 0.0 : static_cast<double>(specialistScore);
            if (row.hasSpecialist && (!detail::finite(row.specialistScore)
                                      || row.specialistScore < -1.0
                                      || row.specialistScore > 1.0)) {
                result.error = "specialist score is invalid";
                return result;
            }
        }

        const auto nameCandidate = rowValue.getProperty("name_candidate", juce::var());
        if (!detail::isNull(nameCandidate)) {
            if (!detail::evidenceObjectSafe(nameCandidate)) {
                result.error = "structured name candidate is not read-only";
                return result;
            }
            const auto candidateFilename = nameCandidate.getProperty("candidate_filename", juce::var());
            const auto nameState = nameCandidate.getProperty("name_state", juce::var()).toString();
            if (!detail::safeCandidateFilename(candidateFilename)
                || (nameState != "suggested_review_required" && nameState != "review_required")) {
                result.error = "structured name candidate is invalid";
                return result;
            }
            row.hasNameCandidate = true;
            row.candidateFilename = candidateFilename.toString();
            row.nameState = nameState;
        }

        const auto fused = rowValue.getProperty("fused_decision", juce::var());
        if (!detail::isNull(fused)) {
            if (!detail::evidenceObjectSafe(fused)) {
                result.error = "fused decision is not read-only";
                return result;
            }
            const auto decision = fused.getProperty("decision", juce::var()).toString();
            const auto scope = fused.getProperty("candidate_scope", juce::var()).toString();
            if (decision != "suggest" && decision != "review" && decision != "unknown_domain") {
                result.error = "fused decision state is invalid";
                return result;
            }
            if (scope != "music_taxonomy" && scope != "open_world_domain" && scope != "none") {
                result.error = "fused candidate scope is invalid";
                return result;
            }
            const auto candidate = fused.getProperty("candidate_label", juce::var());
            const auto domainCandidate = fused.getProperty("domain_candidate_label", juce::var());
            if (!candidate.isVoid() && !detail::safeCandidateLabel(candidate)) {
                result.error = "fused candidate label is invalid";
                return result;
            }
            if (!domainCandidate.isVoid() && !detail::safeCandidateLabel(domainCandidate)) {
                result.error = "open-world candidate label is invalid";
                return result;
            }
            if (decision == "suggest" && (candidate.isVoid() || scope != "music_taxonomy")) {
                result.error = "accepted fused decision has no music candidate";
                return result;
            }
            row.hasFusionDecision = true;
            row.fusionDecision = decision;
            row.fusionCandidateScope = scope;
            row.fusionCandidateLabel = candidate.isVoid() ? juce::String() : candidate.toString();
            row.domainCandidateLabel = domainCandidate.isVoid() ? juce::String() : domainCandidate.toString();
            const auto novelty = fused.getProperty("ood_novelty_score", juce::var());
            if (!novelty.isVoid()) {
                row.oodNoveltyScore = static_cast<double>(novelty);
                if (!detail::finite(row.oodNoveltyScore) || row.oodNoveltyScore < 0.0
                    || row.oodNoveltyScore > 1.0) {
                    result.error = "OOD novelty score is invalid";
                    return result;
                }
                row.hasOodNovelty = true;
            }
            row.oodOverride = static_cast<bool>(fused.getProperty("ood_override", false));
            if (row.oodOverride && decision != "review") {
                result.error = "OOD override must downgrade to review";
                return result;
            }
        }

        const auto physical = rowValue.getProperty("physical", juce::var());
        if (!detail::isNull(physical)) {
            if (!detail::evidenceObjectSafe(physical)) {
                result.error = "physical evidence is invalid";
                return result;
            }
            row.hasPhysicalEvidence = true;
        }

        const auto segmentEvidence = rowValue.getProperty("segments", juce::var());
        if (!detail::isNull(segmentEvidence)) {
            if (!detail::evidenceObjectSafe(segmentEvidence)) {
                result.error = "segment evidence is not read-only";
                return result;
            }
            const auto windowsValue = segmentEvidence.getProperty("segments", juce::var());
            const auto* windows = windowsValue.getArray();
            if (windows == nullptr || windows->size() > maxSegmentsPerRow) {
                result.error = "segment window count is invalid";
                return result;
            }
            row.hasSegmentEvidence = true;
            row.nScoredWindows = static_cast<int>(segmentEvidence.getProperty("n_scored_windows", 0));
            if (row.nScoredWindows < 0) {
                result.error = "segment score count is invalid";
                return result;
            }
            for (const auto& windowValue : *windows) {
                if (!windowValue.isObject() || !detail::hasNoSemanticLabel(windowValue)) {
                    result.error = "segment window is invalid";
                    return result;
                }
                Segment segment;
                segment.suggestion = windowValue.getProperty("suggestion", juce::var()).toString();
                segment.status = windowValue.getProperty("status", juce::var()).toString();
                segment.startSeconds = static_cast<double>(windowValue.getProperty("start_seconds", 0.0));
                segment.endSeconds = static_cast<double>(windowValue.getProperty("end_seconds", 0.0));
                segment.score = static_cast<double>(windowValue.getProperty("score", 0.0));
                segment.margin = static_cast<double>(windowValue.getProperty("margin", 0.0));
                if (segment.suggestion.isEmpty()
                    || (segment.status != "suggest" && segment.status != "review")
                    || !detail::finite(segment.startSeconds) || !detail::finite(segment.endSeconds)
                    || !detail::finite(segment.score) || !detail::finite(segment.margin)
                    || segment.startSeconds < 0.0 || segment.endSeconds < segment.startSeconds) {
                    result.error = "segment window values are invalid";
                    return result;
                }
                row.segments.add(segment);
            }
        }

        const auto clusterEvidence = rowValue.getProperty("cluster_discovery", juce::var());
        if (!detail::isNull(clusterEvidence)) {
            if (!detail::evidenceObjectSafe(clusterEvidence)) {
                result.error = "cluster-discovery evidence is not read-only";
                return result;
            }
            const auto clusterId = clusterEvidence.getProperty("cluster_id", juce::var());
            const auto clusterSize = clusterEvidence.getProperty("cluster_size", juce::var());
            const auto status = clusterEvidence.getProperty("discovery_status", juce::var()).toString();
            if (!clusterId.isInt() || !clusterSize.isInt()
                || static_cast<int>(clusterSize) < 0
                || (status != "cluster_hypothesis" && status != "noise_review")) {
                result.error = "cluster-discovery values are invalid";
                return result;
            }
            row.clusterDiscovery.clusterId = static_cast<int>(clusterId);
            row.clusterDiscovery.clusterSize = static_cast<int>(clusterSize);
            row.clusterDiscovery.status = status;
            row.hasClusterDiscovery = true;
        }

        const auto retrieval = rowValue.getProperty("retrieval", juce::var());
        if (!detail::isNull(retrieval)) {
            if (!detail::evidenceObjectSafe(retrieval)) {
                result.error = "retrieval evidence is not read-only";
                return result;
            }
            const auto status = retrieval.getProperty("status", juce::var()).toString();
            const auto candidate = retrieval.getProperty("retrieval_candidate_label", juce::var());
            const auto similarity = retrieval.getProperty("retrieval_similarity", juce::var());
            if (status != "suggest" && status != "review") {
                result.error = "retrieval status is invalid";
                return result;
            }
            if (!candidate.isVoid() && !detail::safeCandidateLabel(candidate)) {
                result.error = "retrieval candidate label is invalid";
                return result;
            }
            if (!similarity.isVoid()) {
                row.retrievalSimilarity = static_cast<double>(similarity);
                if (!detail::finite(row.retrievalSimilarity)
                    || row.retrievalSimilarity < -1.0 || row.retrievalSimilarity > 1.0) {
                    result.error = "retrieval similarity is invalid";
                    return result;
                }
            }
            if (status == "suggest" && candidate.isVoid()) {
                result.error = "retrieval suggestion has no candidate";
                return result;
            }
            row.retrievalStatus = status;
            row.retrievalCandidateLabel = candidate.isVoid() ? juce::String() : candidate.toString();
            row.hasRetrievalEvidence = true;
        }

        const auto fftEvidence = rowValue.getProperty("fft_evidence", juce::var());
        if (!detail::isNull(fftEvidence)) {
            if (!detail::evidenceObjectSafe(fftEvidence)) {
                result.error = "FFT evidence is not read-only";
                return result;
            }
            const auto status = fftEvidence.getProperty("status", juce::var()).toString();
            if (status != "computed" && status != "unresolved_local_audio"
                && status != "decode_or_short_audio") {
                result.error = "FFT evidence status is invalid";
                return result;
            }
            const auto values = fftEvidence.getProperty("values", juce::var());
            if (status == "computed") {
                if (!values.isObject()) {
                    result.error = "computed FFT evidence has no values";
                    return result;
                }
                row.fftDurationSeconds = static_cast<double>(values.getProperty("duration_s", 0.0));
                row.fftSustainRatio = static_cast<double>(values.getProperty("sustain_ratio", 0.0));
                row.fftLowBandRatio = static_cast<double>(values.getProperty("low_band_ratio", 0.0));
                row.fftMidBandRatio = static_cast<double>(values.getProperty("mid_band_ratio", 0.0));
                row.fftHighBandRatio = static_cast<double>(values.getProperty("high_band_ratio", 0.0));
                row.fftFluxMean = static_cast<double>(values.getProperty("flux_mean", 0.0));
                row.fftFluxStd = static_cast<double>(values.getProperty("flux_std", 0.0));
                row.fftFluxPeakRate = static_cast<double>(values.getProperty("flux_peak_rate", 0.0));
                const auto finiteNonNegative = [](double value) {
                    return detail::finite(value) && value >= 0.0;
                };
                if (!finiteNonNegative(row.fftDurationSeconds)
                    || row.fftDurationSeconds > 86400.0
                    || !finiteNonNegative(row.fftSustainRatio) || row.fftSustainRatio > 2.0
                    || !finiteNonNegative(row.fftLowBandRatio) || row.fftLowBandRatio > 1.0
                    || !finiteNonNegative(row.fftMidBandRatio) || row.fftMidBandRatio > 1.0
                    || !finiteNonNegative(row.fftHighBandRatio) || row.fftHighBandRatio > 1.0
                    || !finiteNonNegative(row.fftFluxMean) || row.fftFluxMean > 1000.0
                    || !finiteNonNegative(row.fftFluxStd) || row.fftFluxStd > 1000.0
                    || !finiteNonNegative(row.fftFluxPeakRate) || row.fftFluxPeakRate > 1000.0) {
                    result.error = "FFT evidence values are invalid";
                    return result;
                }
                const auto lanes = fftEvidence.getProperty("candidate_lanes", juce::var());
                if (!lanes.isArray() || lanes.getArray()->size() > 16) {
                    result.error = "FFT evidence lanes are invalid";
                    return result;
                }
                for (const auto& lane : *lanes.getArray()) {
                    if (!lane.isString()) {
                        result.error = "FFT evidence lane is invalid";
                        return result;
                    }
                    const auto laneText = lane.toString();
                    if (laneText != "loop_temporal_evidence"
                        && laneText != "transient_temporal_evidence"
                        && laneText != "bright_spectral_evidence") {
                        result.error = "FFT evidence lane is unknown";
                        return result;
                    }
                    row.fftCandidateLanes.add(laneText);
                }
                row.hasFftEvidence = true;
            }
        }
        result.packet.rows.add(row);
    }
    result.success = true;
    return result;
}

} // namespace SloLabelFreeEvidence
