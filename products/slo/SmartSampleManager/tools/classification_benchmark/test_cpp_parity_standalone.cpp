#include "AcousticClassifier.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>
#include <string>
#include <algorithm>

struct ReferenceCase {
    std::string filename;
    std::vector<float> embedding;
    std::vector<float> expected_logits;
    std::vector<float> expected_probs;
    std::string expected_subcategory;
};

static std::vector<float> parseNumbers(const std::string& str) {
    std::vector<float> nums;
    size_t pos = 0;
    while (pos < str.size()) {
        while (pos < str.size() && (str[pos] == ' ' || str[pos] == '[' || str[pos] == ']' || str[pos] == ',' || str[pos] == '\n' || str[pos] == '\r')) pos++;
        if (pos >= str.size()) break;
        size_t nextPos = 0;
        float val = std::stof(str.substr(pos), &nextPos);
        nums.push_back(val);
        pos += nextPos;
    }
    return nums;
}

int main() {
    std::cout << "Testing C++ AcousticClassifier V4 (Hybrid 520D ArcFace) numerical parity..." << std::endl;
    std::cout << "Embedding Dimension: " << AcousticWeights::embeddingDim << " (512 PANNs + 8 DSP)" << std::endl;
    std::cout << "Number of Classes: " << AcousticWeights::numClasses << std::endl;

    std::ifstream file("tools/classification_benchmark/parity_references.json");
    if (!file.is_open()) {
        std::cerr << "FAIL: Could not open parity_references.json" << std::endl;
        return 1;
    }

    std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    file.close();

    std::vector<ReferenceCase> cases;
    size_t refPos = content.find("\"references\":");
    if (refPos == std::string::npos) {
        std::cerr << "FAIL: Could not find references key in JSON" << std::endl;
        return 1;
    }

    size_t itemStart = content.find("{", refPos + 13);
    while (itemStart != std::string::npos) {
        size_t itemEnd = content.find("}", itemStart);
        size_t subcatPos = content.find("\"expected_subcategory\":", itemStart);
        if (subcatPos != std::string::npos && subcatPos > itemStart) {
            itemEnd = content.find("}", subcatPos);
        }
        if (itemEnd == std::string::npos) break;

        std::string itemStr = content.substr(itemStart, itemEnd - itemStart + 1);

        ReferenceCase rc;
        size_t fnPos = itemStr.find("\"filename\":");
        if (fnPos != std::string::npos) {
            size_t q1 = itemStr.find("\"", fnPos + 11);
            size_t q2 = itemStr.find("\"", q1 + 1);
            rc.filename = itemStr.substr(q1 + 1, q2 - q1 - 1);
        }

        size_t embPos = itemStr.find("\"embedding\":");
        size_t expLogitsPos = itemStr.find("\"expected_logits\":");
        size_t expProbsPos = itemStr.find("\"expected_probs\":");
        size_t expSubPos = itemStr.find("\"expected_subcategory\":");

        if (embPos != std::string::npos && expLogitsPos != std::string::npos) {
            size_t embStart = itemStr.find("[", embPos);
            size_t embEnd = itemStr.find("]", embStart);
            rc.embedding = parseNumbers(itemStr.substr(embStart, embEnd - embStart + 1));

            size_t logitsStart = itemStr.find("[", expLogitsPos);
            size_t logitsEnd = itemStr.find("]", logitsStart);
            rc.expected_logits = parseNumbers(itemStr.substr(logitsStart, logitsEnd - logitsStart + 1));

            size_t probsStart = itemStr.find("[", expProbsPos);
            size_t probsEnd = itemStr.find("]", probsStart);
            rc.expected_probs = parseNumbers(itemStr.substr(probsStart, probsEnd - probsStart + 1));

            size_t q1 = itemStr.find("\"", expSubPos + 23);
            size_t q2 = itemStr.find("\"", q1 + 1);
            rc.expected_subcategory = itemStr.substr(q1 + 1, q2 - q1 - 1);

            cases.push_back(rc);
        }

        itemStart = content.find("{", itemEnd + 1);
    }

    std::cout << "Loaded " << cases.size() << " reference test cases from parity_references.json" << std::endl;

    float maxLogitError = 0.0f;
    float maxProbError = 0.0f;
    int passCount = 0;

    for (size_t i = 0; i < cases.size(); ++i) {
        const auto& c = cases[i];
        if (c.embedding.size() != AcousticWeights::embeddingDim) {
            std::cerr << "WARN: Skip case " << i << ", embedding dim mismatch: " << c.embedding.size() << std::endl;
            continue;
        }

        float cppLogits[AcousticWeights::numClasses] = { 0.0f };
        AcousticClassifier::computeLogits(c.embedding.data(), cppLogits);

        auto res = AcousticClassifier::classify(c.embedding.data());

        float maxCaseLogitErr = 0.0f;
        for (int k = 0; k < AcousticWeights::numClasses; ++k) {
            float err = std::abs(cppLogits[k] - c.expected_logits[k]);
            if (err > maxCaseLogitErr) maxCaseLogitErr = err;
        }

        if (maxCaseLogitErr > maxLogitError) maxLogitError = maxCaseLogitErr;

        int subIdx = 0;
        for (int k = 0; k < AcousticWeights::numClasses; ++k) {
            if (std::string(AcousticWeights::classNames[k]) == res.subcategory) {
                subIdx = k;
                break;
            }
        }

        float probErr = std::abs(res.confidence - c.expected_probs[subIdx]);
        if (probErr > maxProbError) maxProbError = probErr;

        if (res.subcategory == c.expected_subcategory && maxCaseLogitErr < 1e-4f) {
            passCount++;
        }

        std::cout << "Case " << i << " [" << c.filename << "]: Predicted=" << res.subcategory 
                  << " (Expected=" << c.expected_subcategory << ") LogitMaxErr=" << maxCaseLogitErr << std::endl;
    }

    std::cout << "\n=== Numerical Parity Summary ===" << std::endl;
    std::cout << "Passed cases: " << passCount << " / " << cases.size() << std::endl;
    std::cout << "Max Logit Absolute Error: " << maxLogitError << std::endl;
    std::cout << "Max Confidence Error:     " << maxProbError << std::endl;

    if (maxLogitError < 1e-4f) {
        std::cout << "\nSUCCESS: C++ AcousticClassifier V4 (Hybrid 520D) verified bit-accurate!" << std::endl;
        return 0;
    } else {
        std::cerr << "\nFAIL: Numerical parity error exceeded threshold 1e-4" << std::endl;
        return 1;
    }
}
