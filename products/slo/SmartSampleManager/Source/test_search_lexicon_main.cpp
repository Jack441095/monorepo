#include "SearchLexicon.h"

#include <cassert>
#include <iostream>

int main()
{
    using SloSearchLexicon::matches;
    assert(matches("Kick_01.wav", "bd"));
    assert(matches("HH_Open_Loop.wav", "hihat"));
    assert(matches("tambourine_one_shot.wav", "shaker"));
    assert(matches("room-tone.wav", "atmosphere"));
    assert(matches("Bass_Hit.wav", "bass")); // literal text remains valid
    assert(!matches("snare.wav", "kick"));
    assert(!matches("bass_reese.wav", "bass hit")); // multi-word stays literal
    assert(matches("drumskin_strike.wav", "membrane"));
    assert(matches("cymbal_crash.wav", "plate"));
    assert(matches("acoustic_guitar.wav", "string"));
    assert(matches("808_glide_fall.wav", "dive"));
    assert(matches("synth_uplifter.wav", "sweep"));
    assert(matches("grand_piano_stiff.wav", "stiff"));
    assert(matches("kick.wav", "kick"));
    std::cout << "SearchLexicon tests passed\n";
    return 0;
}
