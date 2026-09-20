// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "NiteSubmit",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "NiteSubmitCore", targets: ["NiteSubmitCore"]),
        .executable(name: "nitesubmit-cli", targets: ["nitesubmit-cli"]),
        .executable(name: "NiteSubmitApp", targets: ["NiteSubmitApp"]),
        .executable(name: "nitesubmit-tests", targets: ["NiteSubmitTests"]),
        .executable(name: "nitesubmit-keygen", targets: ["nitesubmit-keygen"]),
    ],
    targets: [
        .target(name: "NiteSubmitCore"),
        .executableTarget(
            name: "nitesubmit-cli",
            dependencies: ["NiteSubmitCore"]
        ),
        .executableTarget(
            name: "NiteSubmitTests",
            dependencies: ["NiteSubmitCore"],
            // Corpus files are resolved from the source tree via #filePath in
            // CorpusTests.swift. They are test fixtures, not SwiftPM runtime
            // resources; excluding them makes that boundary explicit and
            // prevents a noisy "unhandled files" warning for every PDF.
            exclude: ["Fixtures"]
        ),
        .executableTarget(
            name: "NiteSubmitApp",
            dependencies: ["NiteSubmitCore"]
        ),
        .executableTarget(
            name: "nitesubmit-keygen",
            dependencies: []
        )
    ]
)
