#include "AbletonXmpWriter.h"

#include <JuceHeader.h>

namespace AbletonXmpWriter {

namespace {

constexpr const char* kAbletonFolderInfoDirName = "Ableton Folder Info";

// Fixed filename Ableton's own XMP toolkit uses for a folder's tag-metadata
// sidecar -- verified against github.com/17cupsofcoffee/LiveTagger's
// get_folder_metadata_path() and its checked-in test fixtures. Not
// documented anywhere official; treat as reverse-engineered fact, not spec.
constexpr const char* kFolderMetadataFileName = "dc66a3fa-0fe1-5352-91cf-3ec237e9ee90.xmp";

juce::File getFolderInfoDir(const juce::File& sampleFile)
{
    return sampleFile.getParentDirectory().getChildFile(kAbletonFolderInfoDirName);
}

juce::File getFolderMetadataFile(const juce::File& sampleFile)
{
    return getFolderInfoDir(sampleFile).getChildFile(kFolderMetadataFileName);
}

// Matches the exact template Ableton's own XMP toolkit writes for an empty
// document -- verified against LiveTagger's METADATA_TEMPLATE constant.
std::unique_ptr<juce::XmlElement> createEmptyDocument()
{
    static const char* kTemplate =
        "<x:xmpmeta xmlns:x=\"adobe:ns:meta/\" x:xmptk=\"XMP Core 5.6.0\">"
        "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">"
        "<rdf:Description rdf:about=\"\" "
        "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" "
        "xmlns:ablFR=\"https://ns.ableton.com/xmp/fs-resources/1.0/\" "
        "xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\">"
        "<dc:format>application/vnd.ableton.folder</dc:format>"
        "<ablFR:resource>folder</ablFR:resource>"
        "<ablFR:items><rdf:Bag></rdf:Bag></ablFR:items>"
        "</rdf:Description>"
        "</rdf:RDF>"
        "</x:xmpmeta>";
    return juce::XmlDocument::parse(juce::String(kTemplate));
}

juce::XmlElement* findDescription(juce::XmlElement& root)
{
    auto* rdf = root.getChildByName("rdf:RDF");
    if (rdf == nullptr) return nullptr;
    return rdf->getChildByName("rdf:Description");
}

juce::XmlElement* findOrCreateItemsBag(juce::XmlElement& description)
{
    auto* items = description.getChildByName("ablFR:items");
    if (items == nullptr) items = description.createNewChildElement("ablFR:items");

    auto* bag = items->getChildByName("rdf:Bag");
    if (bag == nullptr) bag = items->createNewChildElement("rdf:Bag");

    return bag;
}

// Finds the <rdf:li> entry for a given relative filename within the items
// bag, or nullptr if that file has no entry yet.
juce::XmlElement* findItemForFile(juce::XmlElement& bag, const juce::String& relativeFileName)
{
    for (auto* li : bag.getChildWithTagNameIterator("rdf:li")) {
        auto* pathEl = li->getChildByName("ablFR:filePath");
        if (pathEl != nullptr && pathEl->getAllSubText().trim() == relativeFileName) {
            return li;
        }
    }
    return nullptr;
}

} // namespace

WriteResult writeTagsForFile(const std::string& audioFilePath, const std::vector<std::string>& keywords)
{
    WriteResult result;

    juce::File sampleFile(audioFilePath);
    if (!sampleFile.existsAsFile()) {
        result.errorMessage = "Audio file does not exist.";
        return result;
    }

    juce::File xmpFile = getFolderMetadataFile(sampleFile);
    juce::File infoDir = getFolderInfoDir(sampleFile);

    std::unique_ptr<juce::XmlElement> doc;

    if (xmpFile.existsAsFile()) {
        doc = juce::XmlDocument::parse(xmpFile);
        if (doc == nullptr) {
            result.errorMessage = "Existing 'Ableton Folder Info' XMP file could not be parsed as XML -- "
                                   "refusing to touch it rather than risk corrupting a file that may already "
                                   "have real Ableton tag data in it.";
            return result;
        }

        // Back up before modifying anything pre-existing, using LiveTagger's
        // own ".xmp.bak" convention (restore by renaming it back to ".xmp").
        juce::File backupFile = xmpFile.getSiblingFile(xmpFile.getFileName() + ".bak");
        if (!xmpFile.copyFileTo(backupFile)) {
            result.errorMessage = "Could not create a backup of the existing XMP file -- aborting without "
                                   "writing, to avoid risking data loss.";
            return result;
        }
        result.backupCreated = true;
    } else {
        doc = createEmptyDocument();
        if (doc == nullptr) {
            result.errorMessage = "Internal error building a new XMP document.";
            return result;
        }
        if (!infoDir.createDirectory()) {
            result.errorMessage = "Could not create the 'Ableton Folder Info' directory.";
            return result;
        }
    }

    auto* description = findDescription(*doc);
    if (description == nullptr) {
        result.errorMessage = "Existing XMP file doesn't have the expected Ableton folder-metadata "
                               "structure (missing rdf:RDF/rdf:Description) -- refusing to touch it.";
        return result;
    }

    auto* bag = findOrCreateItemsBag(*description);
    juce::String relativeName = sampleFile.getFileName();

    auto* item = findItemForFile(*bag, relativeName);
    if (item == nullptr) {
        item = bag->createNewChildElement("rdf:li");
        item->setAttribute("rdf:parseType", "Resource");
        auto* pathEl = item->createNewChildElement("ablFR:filePath");
        pathEl->addTextElement(relativeName);
    }

    // Replace this file's keyword set wholesale -- every other file's entry
    // in the same document (including ones this app never wrote) is left
    // untouched, since findItemForFile/the loop above only ever looks at
    // this one <rdf:li>.
    item->deleteAllChildElementsWithTagName("ablFR:keywords");
    if (!keywords.empty()) {
        auto* keywordsEl = item->createNewChildElement("ablFR:keywords");
        auto* keywordsBag = keywordsEl->createNewChildElement("rdf:Bag");
        for (const auto& kw : keywords) {
            auto* li = keywordsBag->createNewChildElement("rdf:li");
            li->addTextElement(juce::String(kw));
        }
    }

    if (!doc->writeTo(xmpFile)) {
        result.errorMessage = "Failed to write the XMP file to disk.";
        return result;
    }

    result.success = true;
    return result;
}

std::vector<std::string> readTagsForFile(const std::string& audioFilePath)
{
    std::vector<std::string> tags;

    juce::File sampleFile(audioFilePath);
    juce::File xmpFile = getFolderMetadataFile(sampleFile);
    if (!xmpFile.existsAsFile()) return tags;

    auto doc = juce::XmlDocument::parse(xmpFile);
    if (doc == nullptr) return tags;

    auto* description = findDescription(*doc);
    if (description == nullptr) return tags;

    auto* items = description->getChildByName("ablFR:items");
    if (items == nullptr) return tags;
    auto* bag = items->getChildByName("rdf:Bag");
    if (bag == nullptr) return tags;

    juce::String relativeName = sampleFile.getFileName();
    auto* item = findItemForFile(*bag, relativeName);
    if (item == nullptr) return tags;

    auto* keywordsEl = item->getChildByName("ablFR:keywords");
    if (keywordsEl == nullptr) return tags;
    auto* keywordsBag = keywordsEl->getChildByName("rdf:Bag");
    if (keywordsBag == nullptr) return tags;

    for (auto* li : keywordsBag->getChildWithTagNameIterator("rdf:li")) {
        tags.push_back(li->getAllSubText().trim().toStdString());
    }

    return tags;
}

} // namespace AbletonXmpWriter
