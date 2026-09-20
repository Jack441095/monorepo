#include "LabelFreeEvidencePacket.h"

#include <cstdlib>
#include <iostream>

namespace {
int failures = 0;
void expect(bool value, const char* message)
{
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}
}

int main(int argc, char** argv)
{
    const auto temp = juce::File::getSpecialLocation(juce::File::tempDirectory)
        .getChildFile("slo_label_free_packet_test.json");
    const juce::String valid = R"json({
      "record_type":"slo_label_free_evidence_packet",
      "method_version":"test_v1",
      "coverage":{"domain_route":1,"physical":1,"segments":1,"fused_decision":1,"cluster_discovery":1,"retrieval":1},
      "safety":{"read_only":true,"semantic_labels_created":false,"rename_actions":false},
      "rows":[{
        "path":"/library/a.wav","semantic_label":null,
        "review_state":"suggestion_review_required",
        "ensemble":{"semantic_label":null,"ensemble_suggestion":"Kick",
          "model_agreement":1.0,"safety":{"read_only":true,"semantic_labels_created":false,"rename_actions":false}},
        "domain_route":{"semantic_label":null,"domain_suggestion":"music_sample",
          "safety":{"read_only":true,"semantic_labels_created":false,"rename_actions":false}},
        "specialist":{"semantic_label":null,"specialist_status":"scored",
          "specialist_suggestion":"Kick","specialist_score":0.4},
        "fused_decision":{"semantic_label":null,"decision":"suggest",
          "candidate_label":"Kick","domain_candidate_label":null,
          "candidate_scope":"music_taxonomy","ood_novelty_score":0.12,
          "ood_override":false},
        "name_candidate":{"semantic_label":null,"name_state":"suggested_review_required",
          "candidate_filename":"kick_one-shot_id-a.wav",
          "safety":{"read_only":true,"semantic_label_created":false,
            "rename_applied":false,"metadata_written":false}},
        "physical":{"temporal":{"form_hint":"possibly_one_shot"}},
        "segments":{"semantic_label":null,"n_scored_windows":1,
          "safety":{"read_only":true,"semantic_labels_created":false,"rename_actions":false},
          "segments":[{"semantic_label":null,"suggestion":"Kick","status":"suggest",
            "start_seconds":0.0,"end_seconds":0.25,"score":0.4,"margin":0.1}]}
        ,"cluster_discovery":{"semantic_label":null,"cluster_id":2,"cluster_size":7,
          "discovery_status":"cluster_hypothesis"},
        "retrieval":{"semantic_label":null,"status":"suggest",
          "retrieval_candidate_label":"Kick","retrieval_similarity":0.91},
        "fft_evidence":{"semantic_label":null,"status":"computed",
          "values":{"duration_s":2.0,"sustain_ratio":0.8,
            "low_band_ratio":0.2,"mid_band_ratio":0.5,"high_band_ratio":0.3,
            "flux_mean":0.1,"flux_std":0.2,"flux_peak_rate":3.0},
          "candidate_lanes":["loop_temporal_evidence"]}
      }]
    })json";
    temp.replaceWithText(valid);
    auto parsed = SloLabelFreeEvidence::parse(temp);
    expect(parsed.success, "valid packet must parse");
    expect(parsed.packet.rows.size() == 1, "one packet row expected");
    expect(parsed.packet.rows[0].segments.size() == 1, "one segment expected");
    expect(parsed.packet.rows[0].hasDomainRoute, "domain route should be present");
    expect(parsed.packet.rows[0].hasSpecialist, "specialist evidence should be present");
    expect(parsed.packet.rows[0].hasNameCandidate, "structured name candidate should be present");
    expect(parsed.packet.rows[0].hasFusionDecision, "fused decision should be present");
    expect(parsed.packet.rows[0].fusionDecision == "suggest", "fused decision state should parse");
    expect(parsed.packet.fusedDecisionCoverage == 1, "fused decision coverage should parse");
    expect(parsed.packet.rows[0].hasOodNovelty, "OOD novelty should be present");
    expect(parsed.packet.rows[0].oodNoveltyScore > 0.1 && parsed.packet.rows[0].oodNoveltyScore < 0.2,
           "OOD novelty should parse");
    expect(parsed.packet.clusterDiscoveryCoverage == 1, "cluster coverage should parse");
    expect(parsed.packet.rows[0].hasClusterDiscovery, "cluster discovery should be present");
    expect(parsed.packet.rows[0].clusterDiscovery.clusterSize == 7,
           "cluster size should parse");
    expect(parsed.packet.retrievalCoverage == 1, "retrieval coverage should parse");
    expect(parsed.packet.rows[0].hasRetrievalEvidence, "retrieval evidence should be present");
    expect(parsed.packet.rows[0].retrievalCandidateLabel == "Kick",
           "retrieval candidate should parse");
    expect(parsed.packet.rows[0].hasFftEvidence,
           "FFT evidence should be present");
    expect(parsed.packet.rows[0].fftFluxPeakRate > 2.0
               && parsed.packet.rows[0].fftFluxPeakRate < 4.0,
           "FFT peak rate should parse");

    temp.replaceWithText(valid.replace("\"semantic_label\":null", "\"semantic_label\":\"Kick\""));
    auto rejected = SloLabelFreeEvidence::parse(temp);
    expect(!rejected.success, "semantic labels must be rejected");
    temp.replaceWithText(valid.replace("kick_one-shot_id-a.wav", "../unsafe.wav"));
    auto unsafeName = SloLabelFreeEvidence::parse(temp);
    expect(!unsafeName.success, "path-bearing filename candidates must be rejected");
    temp.replaceWithText(valid.replace("/library/a.wav", "relative/a.wav"));
    auto relativePath = SloLabelFreeEvidence::parse(temp);
    expect(!relativePath.success, "relative evidence paths must be rejected");
    temp.deleteFile();

    if (argc > 1) {
        const auto actual = SloLabelFreeEvidence::parse(juce::File(argv[1]));
        expect(actual.success, "real evidence packet must parse");
        if (!actual.success)
            std::cerr << "real packet parse error: " << actual.error << '\n';
        if (actual.success) {
            expect(actual.packet.nRows == actual.packet.rows.size(),
                   "real packet row count must agree with parsed rows");
            expect(actual.packet.domainCoverage == actual.packet.nRows,
                   "real packet domain coverage must be complete");
            expect(actual.packet.physicalCoverage <= actual.packet.nRows,
                   "real packet physical coverage must not exceed row count");
            expect(actual.packet.segmentCoverage <= actual.packet.nRows,
                   "real packet segment coverage must not exceed row count");
            expect(actual.packet.nameCandidateCoverage <= actual.packet.nRows,
                   "real packet name-candidate coverage must not exceed row count");
        }
    }
    if (argc > 2) {
        const auto fused = SloLabelFreeEvidence::parse(juce::File(argv[2]));
        expect(fused.success, "real fused evidence packet must parse");
        if (!fused.success)
            std::cerr << "real fused packet parse error: " << fused.error << '\n';
        if (fused.success) {
            expect(fused.packet.fusedDecisionCoverage == fused.packet.nRows,
                   "real fused packet coverage must be complete");
            expect(fused.packet.clusterDiscoveryCoverage == fused.packet.nRows,
                   "real cluster discovery coverage must be complete");
            expect(fused.packet.retrievalCoverage == fused.packet.nRows,
                   "real retrieval coverage must be complete");
            expect(fused.packet.rows.size() > 0 && fused.packet.rows[0].hasFusionDecision,
                   "real fused packet rows must expose fusion decisions");
            if (fused.packet.fftCoverage > 0) {
                expect(fused.packet.fftCoverage <= fused.packet.nRows,
                       "FFT coverage must not exceed row count");
                expect(fused.packet.rows[0].hasFftEvidence || fused.packet.fftCoverage < fused.packet.nRows,
                       "FFT evidence rows should expose parsed measurements");
            }
        }
    }
    if (failures == 0) std::cout << "Label-free evidence packet tests passed\n";
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
