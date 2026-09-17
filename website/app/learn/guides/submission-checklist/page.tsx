import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = pageMetadata({
  title: "Student Submission Checklist",
  description:
    "A free pre-submission checklist for students. Check filenames, metadata, formatting, and anonymisation before you upload.",
  path: "/learn/guides/submission-checklist",
});

const CHECKS = [
  {
    number: "01",
    title: "Filename format",
    question: "Does your filename match the department's required convention?",
    detail:
      "Common formats include StudentID_ModuleCode_Assignment1.pdf or Surname_Firstname_Essay.docx. Check your assignment brief for the exact format. Spaces, special characters, and very long filenames can cause upload errors on some portals.",
    fail: "A misnamed file can be rejected outright or filed under the wrong student. Some portals silently rename your file, which can break anonymisation.",
  },
  {
    number: "02",
    title: "File format and size",
    question: "Is it the right file type, and is it under the size limit?",
    detail:
      "Most submissions require PDF. If your brief says PDF, export from Word/Pages/LaTeX as PDF rather than renaming a .docx to .pdf (that doesn't convert it). Check the maximum file size, usually 20-40MB. If your file is too large, reduce image resolution or remove embedded fonts you don't need.",
    fail: "Uploading a .docx when a .pdf is required, or exceeding the size limit, triggers a rejection that you might not see until after the deadline.",
  },
  {
    number: "03",
    title: "PDF metadata",
    question: "Does the PDF's author/title metadata contain anything you don't want the marker to see?",
    detail:
      "Open your PDF in Preview (Mac) and press Cmd+I, or right-click > Properties on Windows. Check the Author, Title, and Subject fields. If the submission should be anonymous, your name should not appear in any of these fields. Word often auto-fills the Author field with your Microsoft account name.",
    fail: "Anonymous marking is compromised if your name is in the metadata. Most students never check this.",
  },
  {
    number: "04",
    title: "Page count and formatting",
    question: "Does it meet the page/word count requirements? Are margins, font size, and spacing correct?",
    detail:
      "Check your brief for specific formatting requirements: font (often Times New Roman 12pt or Arial 11pt), line spacing (often 1.5 or double), margins (often 2.54cm / 1 inch). Some departments specify a cover page format. If there's a word count, check it in your word processor before exporting to PDF.",
    fail: "Submitting with wrong formatting can lose presentation marks or trigger a resubmission request.",
  },
  {
    number: "05",
    title: "References and bibliography",
    question: "Is your reference list in the required citation style, and does every in-text citation have a matching entry?",
    detail:
      "Common styles: Harvard, APA 7th, IEEE, Chicago. Check your department's handbook, not just the assignment brief, as the required style is sometimes only stated there. Cross-check: every (Author, Year) in the text should appear in the reference list, and vice versa.",
    fail: "Missing or mismatched references can trigger plagiarism flags and lose marks for academic rigour.",
  },
  {
    number: "06",
    title: "Plagiarism self-check",
    question: "Have you run your own similarity check before the official one?",
    detail:
      "Many institutions allow you to submit a draft to Turnitin before the deadline to check your similarity score. Use this. A high similarity score doesn't always mean plagiarism (it flags direct quotes and common phrases too), but it's better to know before you submit than to be surprised afterwards.",
    fail: "A high similarity score with no self-review means you can't explain or justify flagged passages.",
  },
  {
    number: "07",
    title: "Supporting files",
    question: "Are all appendices, datasets, code files, or supplementary materials included and clearly labelled?",
    detail:
      "If your submission includes multiple files, check that you're uploading all of them. Name them consistently (e.g. Appendix_A_Dataset.xlsx). If the portal only accepts one file, you may need to merge everything into a single PDF or ZIP.",
    fail: "Missing appendices can't be submitted after the deadline in most cases.",
  },
  {
    number: "08",
    title: "Final read-through",
    question: "Have you read the entire document once more, on screen or printed, specifically looking for errors?",
    detail:
      "Read it differently from how you wrote it: change the font, print it out, or read it aloud. You're looking for missing words, broken sentences, formatting glitches (especially around images and tables), and anything that doesn't make sense on a cold read.",
    fail: "Typos and broken formatting in the final version are the most common source of lost presentation marks.",
  },
];

export default function SubmissionChecklistPage() {
  return (
    <>
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow text-brand-blue-bright">Free Guide</span>
          <h1 className="section-title mt-4 text-foreground">
            The Student Submission Checklist
          </h1>
          <p className="body-large mt-6">
            Eight checks to run before you hit submit. Takes five minutes.
            Catches the mistakes that lose marks at 11:58pm.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container" style={{ maxWidth: "42rem" }}>
          <Reveal>
            <div className="prose-custom">
              <p>
                This checklist covers the things that go wrong between "I've finished writing"
                and "I've submitted." It's not about your argument, your research, or your grammar.
                It's about the structural and technical details that can cause a rejection, a
                resubmission, or lost marks, and that most students don't check until it's too late.
              </p>
              <p>
                Print it, bookmark it, or just read through it once before your next deadline.
              </p>
            </div>
          </Reveal>

          <div className="mt-12 flex flex-col gap-8">
            {CHECKS.map((check) => (
              <Reveal key={check.number}>
                <div className="surface-card p-6 rounded-lg border border-border/40">
                  <div className="flex items-baseline gap-3">
                    <span
                      className="font-mono text-sm font-bold"
                      style={{ color: "var(--brand-blue-bright)" }}
                    >
                      {check.number}
                    </span>
                    <h2 className="text-base font-semibold text-foreground">
                      {check.title}
                    </h2>
                  </div>
                  <p
                    className="mt-3 text-sm font-medium"
                    style={{ color: "var(--foreground)" }}
                  >
                    {check.question}
                  </p>
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    {check.detail}
                  </p>
                  <p className="mt-3 text-xs leading-relaxed" style={{ color: "var(--state-error, #dc2626)" }}>
                    <strong>If you skip this:</strong> {check.fail}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal>
            <div className="mt-12 prose-custom">
              <h2>Want this automated?</h2>
              <p>
                Submit checks most of this for you automatically: filenames, metadata,
                formatting, anonymisation. It runs locally on your Mac, never touches your
                content, and gives you a verification receipt.
              </p>
              <div className="mt-6 flex flex-wrap gap-4">
                <Link href="/products/submit#join-waitlist" className="btn-primary">
                  Join the Submit waitlist
                </Link>
                <Link href="/products/submit" className="btn-secondary">
                  Learn more about Submit
                </Link>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
