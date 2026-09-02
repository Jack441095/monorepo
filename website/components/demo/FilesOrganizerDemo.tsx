"use client";

import { useState } from "react";
import { DemoPipeline } from "@/components/demo/DemoPipeline";
import { DemoShell } from "@/components/demo/DemoShell";
import { ReadoutPanel, ReadoutRow } from "@/components/demo/Readout";
import { useSignalDemo } from "@/components/demo/useSignalDemo";

/* NITE Files Library Organizer demonstration (SIMULATION).
   Demonstrates local C++17 folder tree scanning, category pills,
   EXIF date sorting, ID3 music organization, and dry-run preview. */

const PRESETS = [
  {
    name: "Downloads_Unorganized/",
    kind: "Folder tree · 28 Files · 480 MB",
    rule: "Category Grouping",
    ruleDesc: "Groups files into Documents/, Audio/, Video/, Images/, Archives/, Code/",
    files: [
      { src: "Brief_2026.pdf", category: "Documents", target: "Documents/Brief_2026.pdf", status: "OK" },
      { src: "Vocals_Stem.wav", category: "Audio", target: "Audio/Vocals_Stem.wav", status: "OK" },
      { src: "Demo_Video.mp4", category: "Video", target: "Video/Demo_Video.mp4", status: "OK" },
      { src: "Screenshot_01.png", category: "Images", target: "Images/Screenshot_01.png", status: "OK" },
      { src: "Submission.7z", category: "Archives", target: "Archives/Submission.7z", status: "OK" },
      { src: "app_core.cpp", category: "Code", target: "Code/app_core.cpp", status: "OK" },
    ],
  },
  {
    name: "Camera_Roll_2026/",
    kind: "Photos · EXIF Metadata · 1.2 GB",
    rule: "EXIF Date Prefix",
    ruleDesc: "Parses EXIF capture timestamp and prefixes YYYY-MM-DD",
    files: [
      { src: "IMG_0042.jpg", category: "Images", target: "Images/2026-08-15_IMG_0042.jpg", status: "EXIF OK" },
      { src: "IMG_0043.jpg", category: "Images", target: "Images/2026-08-15_IMG_0043.jpg", status: "EXIF OK" },
      { src: "DSC_8901.raw", category: "Images", target: "Images/2026-08-16_DSC_8901.raw", status: "EXIF OK" },
      { src: "HEIC_9912.heic", category: "Images", target: "Images/2026-08-20_HEIC_9912.heic", status: "EXIF OK" },
    ],
  },
  {
    name: "Music_Library_Raw/",
    kind: "Audio Stems & Tracks · ID3 Tags · 850 MB",
    rule: "ID3 Artist/Album",
    ruleDesc: "Sorts audio files into {Artist}/{Album}/{Track}.ext subfolders",
    files: [
      { src: "Track_01.mp3", category: "Audio", target: "Audio/Synthwave_Artist/Neon_Album/Track_01.mp3", status: "ID3 OK" },
      { src: "Vocal_Take_02.flac", category: "Audio", target: "Audio/Studio_Session/Stems/Vocal_Take_02.flac", status: "ID3 OK" },
      { src: "Bassline.wav", category: "Audio", target: "Audio/Studio_Session/Stems/Bassline.wav", status: "ID3 OK" },
    ],
  },
] as const;

export function FilesOrganizerDemo() {
  const { phase, start, reset } = useSignalDemo({ scanMs: 1000, analysisMs: 600 });
  const [presetIdx, setPresetIdx] = useState(0);
  const [ruleMode, setRuleMode] = useState<"category" | "date" | "id3">("category");
  const preset = PRESETS[presetIdx];

  const scanning = phase === "scanning";
  const analysing = phase === "analysis";
  const ready = phase === "result";
  const started = phase !== "idle";

  return (
    <DemoShell
      label="simulation"
      title="NITE FILES // C++17 LIBRARY ORGANIZER"
      phase={phase}
      onReset={reset}
      ariaLabel="NITE Files library folder cleaner demonstration"
      footerNote="Simulated console demonstration. Folder scanning, category grouping, and metadata rules execute 100% locally."
    >
      <div className="p-5 sm:p-6 bg-surface flex flex-col gap-5">
        <DemoPipeline phase={phase} />

        {/* C++ Core Status Bar */}
        <div className="flex items-center justify-between gap-2 px-3.5 py-2 rounded bg-surface-raised/80 border border-border-strong/50 text-[10px] font-mono">
          <div className="flex items-center gap-2">
            <span className="dsp-led dsp-led--live" />
            <span className="text-foreground font-bold uppercase tracking-wider">C++17 CORE ENGINE</span>
          </div>
          <div className="flex items-center gap-3 text-muted-dim">
            <span className="text-brand-emerald font-bold">STD::FILESYSTEM</span>
            <span>0 BYTES UPLOADED</span>
          </div>
        </div>

        {/* Folder Preset Selector */}
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
              SELECT TARGET FOLDER PRESET
            </span>
            <div className="flex items-center gap-1.5">
              {(["category", "date", "id3"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setRuleMode(mode)}
                  className={`text-[9px] font-mono px-2 py-0.5 rounded uppercase font-bold border transition-colors cursor-pointer ${
                    ruleMode === mode
                      ? "bg-brand-blue/20 text-brand-blue-bright border-brand-blue/60"
                      : "bg-surface-raised text-muted-dim border-border/40 hover:border-border"
                  }`}
                >
                  {mode === "category" ? "By Category" : mode === "date" ? "EXIF Date" : "ID3 Tags"}
                </button>
              ))}
            </div>
          </div>

          {PRESETS.map((p, idx) => {
            const active = presetIdx === idx;
            return (
              <button
                key={p.name}
                type="button"
                onClick={() => {
                  setPresetIdx(idx);
                  start();
                }}
                aria-pressed={active}
                disabled={scanning || analysing}
                className={`demo-filechip flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-left transition-all cursor-pointer disabled:cursor-default ${
                  active
                    ? "border-brand-blue bg-brand-blue/10 shadow-[0_0_15px_rgba(0,240,255,0.12)]"
                    : "border-border/60 bg-surface/50 hover:border-border-strong"
                }`}
              >
                <span className="min-w-0">
                  <span className="block text-[12px] font-mono text-foreground font-bold truncate">{p.name}</span>
                  <span className="block text-[10px] font-sans text-muted-dim mt-0.5">{p.kind}</span>
                </span>
                <span
                  className="text-[10px] font-mono flex-none px-2.5 py-1 rounded bg-surface-raised border border-border/40 font-bold"
                  style={{ color: active ? "var(--brand-blue-bright)" : "var(--muted-dim)" }}
                >
                  {active && scanning
                    ? "SCANNING…"
                    : active && analysing
                      ? "PROCESSING…"
                      : active && ready
                        ? "PROPOSED"
                        : "SCAN FOLDER"}
                </span>
              </button>
            );
          })}
        </div>

        {/* Category Breakdown & Proposed Relocation Rack */}
        {!started ? (
          <div className="dsp-lcd-box p-6 text-center">
            <p className="text-[11px] font-mono text-muted-dim leading-relaxed">
              Select a target folder preset above to scan files, categorize extensions, and inspect proposed relocation rules.
            </p>
          </div>
        ) : (
          <div className="dsp-rack-panel p-4 rounded-lg flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
                PROPOSED ORGANIZER PLAN // C++ RULE ENGINE
              </span>
              <span className="text-[10px] font-mono text-muted-dim">{preset.rule}</span>
            </div>

            <ReadoutPanel ariaLabel="Organization plan actions">
              {scanning ? (
                <ReadoutRow label="FILESYSTEM SCAN" tone="pending">
                  <span className="text-muted-dim">Scanning directory tree with std::filesystem…</span>
                </ReadoutRow>
              ) : analysing ? (
                <ReadoutRow label="RULE GENERATION" tone="pending">
                  <span className="text-muted-dim">Parsing EXIF/ID3 metadata & evaluating collision policy…</span>
                </ReadoutRow>
              ) : (
                preset.files.map((item) => (
                  <ReadoutRow key={item.src} label={item.src} tone="ok">
                    <div className="flex items-center justify-between w-full gap-2 font-mono text-[11px]">
                      <span className="truncate text-foreground">➔ {item.target}</span>
                      <span className="text-[9px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex-none font-bold">
                        {item.status}
                      </span>
                    </div>
                  </ReadoutRow>
                ))
              )}
            </ReadoutPanel>
          </div>
        )}

        <p className="text-[11px] font-mono text-muted-dim leading-relaxed border-t border-border/30 pt-3">
          NITE Files organizes folders safely with mandatory dry-run previews and transactional undo history. Originals are never modified without explicit approval.
        </p>
      </div>
    </DemoShell>
  );
}

