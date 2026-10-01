#include "SearchLexicon.h"

#include <iostream>

// A bare assert() is not a test here. CMakeLists.txt:436 sets NDEBUG=1 for every
// non-Debug config and both qualification presets are Release, so all of these
// would compile to nothing and the binary would report success no matter what
// SearchLexicon.h contained. Count failures instead, like the other 40 files.
static int failures = 0;

#define CHECK(cond, msg) \
    do { \
        if (!(cond)) { \
            std::cerr << "FAIL: " << msg << " (line " << __LINE__ << ")" << std::endl; \
            failures++; \
        } \
    } while (0)

int main()
{
    using SloSearchLexicon::matches;
    CHECK(matches("Kick_01.wav", "bd"), "matches(\"Kick_01.wav\", \"bd\")");
    CHECK(matches("HH_Open_Loop.wav", "hihat"), "matches(\"HH_Open_Loop.wav\", \"hihat\")");
    CHECK(matches("tambourine_one_shot.wav", "shaker"), "matches(\"tambourine_one_shot.wav\", \"shaker\")");
    CHECK(matches("room-tone.wav", "atmosphere"), "matches(\"room-tone.wav\", \"atmosphere\")");
    CHECK(matches("Bass_Hit.wav", "bass"), "matches(\"Bass_Hit.wav\", \"bass\")"); // literal text remains valid
    CHECK(!matches("snare.wav", "kick"), "!matches(\"snare.wav\", \"kick\")");
    CHECK(!matches("bass_reese.wav", "bass hit"), "!matches(\"bass_reese.wav\", \"bass hit\")"); // multi-word stays literal
    CHECK(matches("drumskin_strike.wav", "membrane"), "matches(\"drumskin_strike.wav\", \"membrane\")");
    CHECK(matches("cymbal_crash.wav", "plate"), "matches(\"cymbal_crash.wav\", \"plate\")");
    CHECK(matches("acoustic_guitar.wav", "string"), "matches(\"acoustic_guitar.wav\", \"string\")");
    CHECK(matches("808_glide_fall.wav", "dive"), "matches(\"808_glide_fall.wav\", \"dive\")");
    CHECK(matches("synth_uplifter.wav", "sweep"), "matches(\"synth_uplifter.wav\", \"sweep\")");
    CHECK(matches("grand_piano_stiff.wav", "stiff"), "matches(\"grand_piano_stiff.wav\", \"stiff\")");
    CHECK(matches("kick.wav", "kick"), "matches(\"kick.wav\", \"kick\")");
    if (failures == 0) {
        std::cout << "SearchLexicon tests passed" << std::endl;
        return 0;
    }

    std::cerr << failures << " SEARCH LEXICON TEST(S) FAILED" << std::endl;
    return 1;
}
