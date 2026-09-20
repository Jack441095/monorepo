#pragma once

#include <string>
#include <vector>

// Writes Ableton Live 12+ "Places"/Browser tags as XMP sidecar files.
//
// This is the ONLY tagging mechanism verified (not assumed) to be
// XMP-based: Ableton has no official API or documented file format for
// this feature. The format used here is reverse-engineered by the
// community project github.com/17cupsofcoffee/LiveTagger, confirmed
// against its actual source and test fixtures. Ableton could change this
// format in a future release without notice -- treat this module as
// experimental/best-effort, not a supported integration, and always surface
// that to the user in the UI.
//
// Never touches the audio file itself. Only ever reads/writes the sidecar
// XMP file living in an "Ableton Folder Info" subdirectory next to the
// audio files it describes -- and always backs up an existing sidecar
// before modifying it (see writeTagsForFile).
namespace AbletonXmpWriter {

struct WriteResult {
    bool success = false;
    std::string errorMessage;
    bool backupCreated = false;
};

// Sets the given file's Ableton keyword list in its folder's XMP sidecar,
// creating the sidecar (and "Ableton Folder Info" directory) if it doesn't
// exist yet. `keywords` should already be in Ableton's own tag string
// format (e.g. "Drums|Kick" for a category/subcategory pair, or a flat
// single-word tag like "Loop") -- this function stores them verbatim, it
// doesn't interpret or validate their content.
//
// This replaces exactly this file's keyword set with `keywords` -- every
// other file's entry already present in the same sidecar is left
// untouched. If the sidecar already exists, it is copied to
// "<name>.xmp.bak" (overwriting any previous backup) before being modified,
// matching LiveTagger's own backup convention.
WriteResult writeTagsForFile(const std::string& audioFilePath, const std::vector<std::string>& keywords);

// Reads back the Ableton keywords currently on disk for a file (empty if no
// sidecar exists, or the file has no entry in it yet). Used to verify what
// was actually written, not just what a caller believes it wrote.
std::vector<std::string> readTagsForFile(const std::string& audioFilePath);

} // namespace AbletonXmpWriter
