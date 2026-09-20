import Foundation
import NiteSubmitCore

// Minimal deterministic test harness (CommandLineTools has no XCTest).

nonisolated(unsafe) var _failures = 0
nonisolated(unsafe) var _checks = 0
nonisolated(unsafe) var _currentSuite = ""

func suite(_ name: String, _ body: () throws -> Void) {
    _currentSuite = name
    print("— \(name)")
    do { try body() } catch {
        _failures += 1
        print("   FAIL [\(_currentSuite)] uncaught error: \(error)")
    }
}

func check(_ condition: Bool, _ message: String, file: StaticString = #file, line: UInt = #line) {
    _checks += 1
    if !condition {
        _failures += 1
        print("   FAIL [\(_currentSuite)] \(message)  (\(file):\(line))")
    }
}

func eq<T: Equatable>(_ a: T, _ b: T, _ message: String, line: UInt = #line) {
    check(a == b, "\(message) — expected \(b), got \(a)", line: line)
}

func throwsError<T>(_ body: @autoclosure () throws -> T, _ message: String, line: UInt = #line) {
    do { _ = try body(); check(false, message + " (did not throw)", line: line) }
    catch { _checks += 1 }
}

func finish() -> Never {
    print("\n\(_checks - _failures)/\(_checks) checks passed")
    exit(_failures == 0 ? 0 : 1)
}
