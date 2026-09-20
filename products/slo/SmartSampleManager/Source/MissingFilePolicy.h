#pragma once

#include <juce_core/juce_core.h>

// A file on a temporarily disconnected macOS volume is unavailable, not
// deleted.  Keep its catalogue record so reconnecting the drive restores the
// library instead of requiring a rescan.  If the volume itself is mounted,
// a missing descendant is a genuine missing-file candidate and may be pruned.
inline bool shouldPreserveMissingFileForUnavailableStorage(const juce::File& file)
{
#if JUCE_MAC
    const auto path = file.getFullPathName();
    const juce::String volumesPrefix("/Volumes/");
    if (!path.startsWith(volumesPrefix))
        return false;

    const auto relativePath = path.substring(volumesPrefix.length());
    const int separator = relativePath.indexOfChar('/');
    if (separator <= 0)
        return false;

    const auto volumeRoot = juce::File(volumesPrefix + relativePath.substring(0, separator));
    return !volumeRoot.isDirectory();
#else
    juce::ignoreUnused(file);
    return false;
#endif
}
