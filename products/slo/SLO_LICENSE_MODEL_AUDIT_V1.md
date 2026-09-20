# SLO License and Model Audit V1

## Model

- Shipping model: PANNs CNN10 embedding ONNX plus linear classifier/centroid data.
- ONNX SHA256: `cbc3653cf2ef3cc35f6be48c4863b6d735b0ff85af3b3e9607706a0f467ffad2`.
- ONNX data SHA256: `8e2b47834248ba6ba0e0993bedcac8babd01666e82a5faf77aaeaca69fa086a8`.
- Taxonomy version: 2; embedding model version: 1.
- Research CLAP/foundation/V5 artifacts are not part of the shipping classifier.

## Licensing

License code uses libsodium and a configurable HTTP client path. The default source URL is `http://localhost:8420`, with comments requiring a real HTTPS endpoint in production. No production endpoint, live key, entitlement service, or authorized licensing run was supplied.

JUCE commercial licensing and third-party notices require human/commercial review. This audit does not certify legal compliance.

## Decision

Model identity is reproducible from hashes. Distribution licensing is **BLOCKED** pending production endpoint/credential configuration, license-server tests, JUCE commercial confirmation, and complete third-party notices.
