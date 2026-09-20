#pragma once

#include <juce_core/juce_core.h>
#include <sodium.h>
#include <array>
#include <filesystem>

#if JUCE_MAC
#include <stdio.h>
#endif

namespace slo::sortSafety {

// Byte identity, deliberately independent of the metadata-insensitive audio hash.
// An edited tag is still a user change that automatic undo must preserve.
inline juce::String fingerprint(const juce::File& file)
{
    if (!file.existsAsFile() || file.isSymbolicLink()) return {};
    auto input = file.createInputStream();
    if (!input || input->getStatus().failed()) return {};
    const auto size = file.getSize();
    const auto modified = file.getLastModificationTime();
    crypto_hash_sha256_state state;
    crypto_hash_sha256_init(&state);
    std::array<unsigned char, 65536> buffer{};
    juce::int64 read = 0;
    for (;;) {
        const int count = input->read(buffer.data(), static_cast<int>(buffer.size()));
        if (count <= 0) break;
        crypto_hash_sha256_update(&state, buffer.data(), static_cast<unsigned long long>(count));
        read += count;
    }
    if (input->getStatus().failed() || read != size || file.getSize() != size
        || file.getLastModificationTime() != modified) return {};
    std::array<unsigned char, crypto_hash_sha256_BYTES> digest{};
    crypto_hash_sha256_final(&state, digest.data());
    return juce::String::toHexString(digest.data(), static_cast<int>(digest.size()));
}

inline bool matches(const juce::File& file, const juce::String& expected)
{
    return !expected.isEmpty() && fingerprint(file) == expected;
}

// Never use JUCE moveFileTo/copyFileTo here: both can delete the target.
// Cross-volume moves fail closed; users may explicitly choose Copy instead.
inline bool moveExclusive(const juce::File& source, const juce::File& destination)
{
    if (source == destination) return source.existsAsFile();
    if (source.isSymbolicLink() || destination.exists() || destination.isSymbolicLink()) return false;
#if JUCE_MAC
    return ::renamex_np(source.getFullPathName().toRawUTF8(),
                        destination.getFullPathName().toRawUTF8(), RENAME_EXCL) == 0;
#else
    std::error_code error;
    std::filesystem::create_hard_link(source.getFullPathName().toStdString(),
                                      destination.getFullPathName().toStdString(), error);
    if (error) return false;
    // A failed removal intentionally leaves both copies for recovery.
    return source.deleteFile();
#endif
}

inline bool copyExclusive(const juce::File& source, const juce::File& destination)
{
    if (source == destination || source.isSymbolicLink()) return false;
    std::error_code error;
    return std::filesystem::copy_file(source.getFullPathName().toStdString(),
        destination.getFullPathName().toStdString(), std::filesystem::copy_options::none, error)
        && !error;
}
} // namespace slo::sortSafety
