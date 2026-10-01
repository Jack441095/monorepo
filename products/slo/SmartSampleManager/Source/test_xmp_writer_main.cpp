#include <algorithm>
#include <iostream>
#include <JuceHeader.h>
#include "AbletonXmpWriter.h"

// Regression test for AbletonXmpWriter -- proves it can (a) create a fresh
// Ableton Folder Info sidecar from scratch and round-trip tags through it,
// (b) parse a REAL sidecar file (the literal fixture from
// github.com/17cupsofcoffee/LiveTagger's test suite, embedded below) without
// corrupting entries it doesn't touch, and (c) always back up before
// modifying an existing sidecar.

namespace {

int failures = 0;

void expectTrue(bool condition, const std::string& label)
{
    if (!condition) {
        std::cerr << "FAIL: " << label << std::endl;
        ++failures;
    }
}

// Verbatim copy of github.com/17cupsofcoffee/LiveTagger's
// src/test_data/initial.xml -- a real Ableton-Live-written (well,
// Ableton-Index-tool-written) sidecar, used here to prove this module can
// actually parse real Ableton output, not just its own round-trip.
const char* kRealAbletonFixture = R"XMP(<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 5.6.0">
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
        <rdf:Description rdf:about=""
                xmlns:dc="http://purl.org/dc/elements/1.1/"
                xmlns:ablFR="https://ns.ableton.com/xmp/fs-resources/1.0/"
                xmlns:xmp="http://ns.adobe.com/xap/1.0/">
            <dc:format>application/vnd.ableton.folder</dc:format>
            <ablFR:resource>folder</ablFR:resource>
            <ablFR:items>
                <rdf:Bag>
                    <rdf:li rdf:parseType="Resource">
                        <ablFR:filePath>bd1.wav</ablFR:filePath>
                        <ablFR:colors>
                            <rdf:Bag>
                                <rdf:li>1</rdf:li>
                            </rdf:Bag>
                        </ablFR:colors>
                        <ablFR:keywords>
                            <rdf:Bag>
                                <rdf:li>Drums|Kick</rdf:li>
                                <rdf:li>Creator|17cupsofcoffee</rdf:li>
                            </rdf:Bag>
                        </ablFR:keywords>
                    </rdf:li>
                    <rdf:li rdf:parseType="Resource">
                        <ablFR:filePath>bd2.wav</ablFR:filePath>
                        <ablFR:keywords>
                            <rdf:Bag>
                                <rdf:li>Creator|17cupsofcoffee</rdf:li>
                            </rdf:Bag>
                        </ablFR:keywords>
                    </rdf:li>
                </rdf:Bag>
            </ablFR:items>
            <xmp:CreatorTool>Ableton Index 12.1</xmp:CreatorTool>
            <xmp:CreateDate>2024-10-10T20:42:58+01:00</xmp:CreateDate>
        </rdf:Description>
    </rdf:RDF>
</x:xmpmeta>
)XMP";

} // namespace

int main()
{
    juce::File scratchDir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                                 .getChildFile("AbletonXmpWriterTest_" + juce::String(juce::Random::getSystemRandom().nextInt(1000000)));
    scratchDir.createDirectory();

    // --- Test 1: fresh sidecar creation + round-trip ---
    {
        juce::File sampleFile = scratchDir.getChildFile("fresh_kick.wav");
        sampleFile.replaceWithText("not real audio, just needs to exist");

        auto result = AbletonXmpWriter::writeTagsForFile(sampleFile.getFullPathName().toStdString(),
                                                           { "Drums|Kick", "One-Shot" });
        expectTrue(result.success, "fresh write should succeed");
        expectTrue(!result.backupCreated, "no backup should be made when no sidecar existed yet");

        auto readBack = AbletonXmpWriter::readTagsForFile(sampleFile.getFullPathName().toStdString());
        expectTrue(readBack.size() == 2, "should read back exactly 2 tags");
        expectTrue(std::find(readBack.begin(), readBack.end(), "Drums|Kick") != readBack.end(), "Drums|Kick should round-trip");
        expectTrue(std::find(readBack.begin(), readBack.end(), "One-Shot") != readBack.end(), "One-Shot should round-trip");

        juce::File xmpFile = scratchDir.getChildFile("Ableton Folder Info")
                                  .getChildFile("dc66a3fa-0fe1-5352-91cf-3ec237e9ee90.xmp");
        expectTrue(xmpFile.existsAsFile(), "sidecar file should exist at the fixed Ableton path");
    }

    // --- Test 2: a second file in the same folder gets its own entry
    //     without disturbing the first file's tags ---
    {
        juce::File sampleFile2 = scratchDir.getChildFile("second_snare.wav");
        sampleFile2.replaceWithText("not real audio, just needs to exist");

        auto result = AbletonXmpWriter::writeTagsForFile(sampleFile2.getFullPathName().toStdString(), { "Drums|Snare" });
        expectTrue(result.success, "second file's write should succeed");
        expectTrue(result.backupCreated, "backup should be made since the sidecar already existed from test 1");

        auto firstFileTags = AbletonXmpWriter::readTagsForFile(scratchDir.getChildFile("fresh_kick.wav").getFullPathName().toStdString());
        expectTrue(firstFileTags.size() == 2, "first file's tags must survive the second file's write untouched");

        auto secondFileTags = AbletonXmpWriter::readTagsForFile(sampleFile2.getFullPathName().toStdString());
        expectTrue(secondFileTags.size() == 1 && secondFileTags[0] == "Drums|Snare", "second file should have its own tag");

        // Backups are timestamped, and the assertion is on how many generations
        // survive rather than on a fixed name. A fixed ".xmp.bak" was the defect:
        // copyFileTo is delete-then-copy, so each write destroys the previous backup.
        //
        // Three writes, not two, and that is the whole point. After two writes a
        // fixed-name backup still holds generation 1 and differs from the current
        // file, so a two-write test passes against the destructive behaviour --
        // verified by mutation. The original is only actually lost on the THIRD
        // write, when the generation-1 backup is overwritten by generation 2.
        const juce::File infoDir = scratchDir.getChildFile("Ableton Folder Info");

        juce::File sampleFile3 = scratchDir.getChildFile("third_hat.wav");
        sampleFile3.replaceWithText("not real audio, just needs to exist");
        const auto third = AbletonXmpWriter::writeTagsForFile(
            sampleFile3.getFullPathName().toStdString(), { "Drums|Hat" });
        expectTrue(third.success, "third file's write should succeed");
        expectTrue(third.backupCreated, "third write should also back up");

        juce::Array<juce::File> backups;
        infoDir.findChildFiles(backups, juce::File::findFiles, false, "*.xmp.bak");
        expectTrue(backups.size() >= 2,
                   "after three writes every prior generation must still be on disk, found "
                     + std::to_string(backups.size()) + " backup(s)");

        // And the two retained generations must actually differ from each other,
        // or "two backups" could just be the same content written twice.
        if (backups.size() >= 2)
        {
            std::vector<juce::String> contents;
            for (const auto& b : backups) contents.push_back(b.loadFileAsString());
            bool anyDistinct = false;
            for (size_t i = 0; i < contents.size() && !anyDistinct; ++i)
                for (size_t j = i + 1; j < contents.size(); ++j)
                    if (contents[i] != contents[j]) { anyDistinct = true; break; }
            expectTrue(anyDistinct, "the retained backups are byte-identical, so no generation was kept");
        }
    }

    // --- Test 3: parse a REAL Ableton/LiveTagger-produced sidecar (not one
    //     this module wrote) and correctly read + extend it ---
    {
        juce::File realFixtureDir = scratchDir.getChildFile("real_fixture_scenario");
        realFixtureDir.createDirectory();
        juce::File infoDir = realFixtureDir.getChildFile("Ableton Folder Info");
        infoDir.createDirectory();
        infoDir.getChildFile("dc66a3fa-0fe1-5352-91cf-3ec237e9ee90.xmp").replaceWithText(kRealAbletonFixture);

        juce::File bd1 = realFixtureDir.getChildFile("bd1.wav");
        bd1.replaceWithText("placeholder");
        juce::File bd2 = realFixtureDir.getChildFile("bd2.wav");
        bd2.replaceWithText("placeholder");

        auto bd1Tags = AbletonXmpWriter::readTagsForFile(bd1.getFullPathName().toStdString());
        expectTrue(bd1Tags.size() == 2, "should correctly read 2 pre-existing tags from a real Ableton-format file");
        expectTrue(std::find(bd1Tags.begin(), bd1Tags.end(), "Drums|Kick") != bd1Tags.end(), "should read Drums|Kick from real fixture");

        // Add a third file to the same real-format document.
        juce::File bd3 = realFixtureDir.getChildFile("bd3.wav");
        bd3.replaceWithText("placeholder");
        auto writeResult = AbletonXmpWriter::writeTagsForFile(bd3.getFullPathName().toStdString(), { "Drums|Kick" });
        expectTrue(writeResult.success, "writing a new entry into a real Ableton-format document should succeed");
        expectTrue(writeResult.backupCreated, "should back up the real fixture before touching it");

        // The pre-existing entries must be completely unharmed.
        auto bd1TagsAfter = AbletonXmpWriter::readTagsForFile(bd1.getFullPathName().toStdString());
        auto bd2TagsAfter = AbletonXmpWriter::readTagsForFile(bd2.getFullPathName().toStdString());
        expectTrue(bd1TagsAfter.size() == 2, "bd1's tags must be untouched after adding bd3");
        expectTrue(bd2TagsAfter.size() == 1 && bd2TagsAfter[0] == "Creator|17cupsofcoffee", "bd2's tag must be untouched after adding bd3");

        auto bd3Tags = AbletonXmpWriter::readTagsForFile(bd3.getFullPathName().toStdString());
        expectTrue(bd3Tags.size() == 1 && bd3Tags[0] == "Drums|Kick", "bd3 should have exactly the tag it was given");
    }

    scratchDir.deleteRecursively();

    if (failures == 0) {
        std::cout << "ALL XMP WRITER TESTS PASSED SUCCESSFULLY!" << std::endl;
        return 0;
    }
    std::cerr << failures << " XMP writer test(s) FAILED." << std::endl;
    return 1;
}
