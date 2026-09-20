// Single-window table: Path|Size|Last Used|Category|Safety|Why + action buttons.
import SwiftUI

private func fmtGB(_ b: Int64) -> String { String(format: "%.2fG", Double(b) / 1e9) }

struct ContentView: View {
    @EnvironmentObject var store: ScanStore
    @State private var sortOrder = [KeyPathComparator(\VerdictRow.size_bytes, order: .reverse)]

    var body: some View {
        VStack(spacing: 0) {
            Table(store.rows, sortOrder: $sortOrder) {
                TableColumn("Path", value: \.path) { Text($0.path).truncationMode(.middle) }
                TableColumn("Size") { Text(fmtGB($0.size_bytes)).monospacedDigit() }
                TableColumn("Safety", value: \.safety) { SafetyBadge(safety: $0.safety) }
                TableColumn("Why") { Text($0.reason).lineLimit(1).foregroundStyle(.secondary) }
                TableColumn("") { row in
                    Toggle("", isOn: Binding(
                        get: { store.checked.contains(row.path) },
                        set: { on in
                            if on { store.checked.insert(row.path) } else { store.checked.remove(row.path) }
                        }
                    ))
                    .labelsHidden()
                    .disabled(row.safety == "BLOCKED") // BLOCKED rows: unselectable
                    .accessibilityLabel(row.safety == "BLOCKED" ? "Locked system path" : "Select \(row.path)")
                }
            }
            .tableStyle(.inset)
            .accessibilityLabel("Cleanup candidates")
            Divider()
            HStack {
                Text("SAFE \(fmtGB(store.safeTotal)) · REVIEW \(fmtGB(store.reviewTotal))")
                    .font(.callout).foregroundStyle(.secondary)
                Spacer()
                Text(store.statusLine).font(.callout).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
                Button("Dry Run") { store.dryRun() }.disabled(store.isScanning)
                Button("Move to Trash") { store.trash() }.disabled(!store.canTrash)
            }
            .padding(8)
        }
        .toolbar { Button("Rescan") { store.dryRun() } }
        .onAppear { if store.rows.isEmpty { store.dryRun() } }
    }
}

private struct SafetyBadge: View {
    let safety: String
    var body: some View {
        Text(safety)
            .font(.caption.bold())
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(
                safety == "SAFE" ? Color.green.opacity(0.2)
                    : safety == "REVIEW" ? Color.yellow.opacity(0.25) : Color.red.opacity(0.2)
            )
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .accessibilityLabel("Safety \(safety)")
    }
}
