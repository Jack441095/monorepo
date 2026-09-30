import Foundation
import NiteSubmitCore

// Minimal deterministic test harness (CommandLineTools has no XCTest).
//
// Nothing in a suite is allowed to trap. A regression has to land as a FAIL
// line naming the scenario that broke, because a crash takes the whole run
// with it and we lose the few hundred other checks that would have told us
// what else moved.

nonisolated(unsafe) var _failures = 0
nonisolated(unsafe) var _checks = 0
nonisolated(unsafe) var _currentSuite = ""

func recordFailure(_ message: String, file: StaticString = #file, line: UInt = #line) {
    _failures += 1
    print("   FAIL [\(_currentSuite)] \(message)  (\(file):\(line))")
}

func suite(_ name: String, _ body: () throws -> Void) {
    _currentSuite = name
    print("— \(name)")
    do { try body() } catch {
        _failures += 1
        print("   FAIL [\(name)] uncaught error: \(error)")
    }
}

/// Blast radius for one behaviour under test. A throw ends its own scenario
/// and nothing else, so one broken invariant is one failed check rather than
/// a silently truncated suite.
func scenario(_ what: String, _ body: () throws -> Void,
              file: StaticString = #file, line: UInt = #line) {
    do { try body() }
    catch { recordFailure("\(what) threw \(error)", file: file, line: line) }
}

func check(_ condition: Bool, _ message: String, file: StaticString = #file, line: UInt = #line) {
    _checks += 1
    if !condition { recordFailure(message, file: file, line: line) }
}

func eq<T: Equatable>(_ a: T, _ b: T, _ message: String, file: StaticString = #file, line: UInt = #line) {
    check(a == b, "\(message) — expected \(b), got \(a)", file: file, line: line)
}

func throwsError<T>(_ body: @autoclosure () throws -> T, _ message: String, line: UInt = #line) {
    do { _ = try body(); check(false, message + " (did not throw)", line: line) }
    catch { _checks += 1 }
}

func finish() -> Never {
    print("\n\(_checks - _failures)/\(_checks) checks passed")
    exit(_failures == 0 ? 0 : 1)
}
