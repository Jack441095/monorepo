import Foundation
import NiteSubmitCore

func runSanitizerTests() {
    suite("FilenameSanitizer") {
        eq(FilenameSanitizer.sanitize("a/b\\c:d*e?f\"g<h>i|j"), "a_b_c_d_e_f_g_h_i_j", "forbidden chars")
        eq(FilenameSanitizer.sanitize("Re\u{0007}port"), "Report", "control char removed")
        eq(FilenameSanitizer.sanitize("Ti\u{200B}tle"), "Title", "zero-width removed")
        eq(FilenameSanitizer.sanitize("My___Project"), "My_Project", "duplicate underscores")
        eq(FilenameSanitizer.sanitize("My   Project"), "My Project", "duplicate spaces")
        eq(FilenameSanitizer.sanitize("  .hidden name. "), "hidden name", "dots/spaces trimmed")
        eq(FilenameSanitizer.sanitize("Étude Zoë"), "Étude Zoë", "accents preserved")

        let s = "interactive audio systems"
        eq(FilenameSanitizer.sanitize(s, caseStyle: .titleCase), "Interactive_Audio_Systems", "title case")
        eq(FilenameSanitizer.sanitize(s, caseStyle: .snakeCase), "interactive_audio_systems", "snake case")
        eq(FilenameSanitizer.sanitize(s, caseStyle: .kebabCase), "interactive-audio-systems", "kebab case")
        eq(FilenameSanitizer.sanitize(s, caseStyle: .safeSpaces), "interactive audio systems", "safe spaces")
        eq(FilenameSanitizer.sanitize(s, caseStyle: .keepOriginal), s, "keep original")

        let long = String(repeating: "é", count: 300)
        let out = FilenameSanitizer.sanitize(long)
        check(out.utf8.count <= FilenameSanitizer.defaultMaxBaseLength, "grapheme-safe length cap")
        eq(FilenameSanitizer.sanitize("///"), "Untitled", "empty becomes Untitled")
        eq(FilenameSanitizer.sanitize("Weird : Name? v2"), FilenameSanitizer.sanitize("Weird : Name? v2"), "deterministic")
        check(FilenameSanitizer.invalidBaseNameReason("../escape") != nil,
              "path traversal name rejected")
        check(FilenameSanitizer.invalidBaseNameReason("CON") != nil,
              "reserved device name rejected")
        check(FilenameSanitizer.invalidBaseNameReason("safe_name") == nil,
              "ordinary direct name accepted")
    }
}
