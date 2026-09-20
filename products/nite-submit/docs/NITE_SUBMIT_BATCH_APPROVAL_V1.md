# NITE Submit batch approval handoff v1

Batch mode never writes a medium- or low-confidence filename automatically.
After inspecting `batch_results.json` and the PDFs, a reviewer may create a
small local approval manifest containing only the exact `source` labels they
approved:

```json
{
  "approval_version": "BATCH_APPROVAL_V1",
  "approved_sources": [
    "authorised_submission_001.pdf",
    "folder/authorised_submission_002.pdf"
  ]
}
```

Run the normal batch again with:

```sh
artifacts/Submit-0.2.0-macOS.app/Contents/MacOS/nitesubmit-cli batch \
  /path/to/input \
  --out real_validation_corpus/test_results/approved_batch \
  --template "{student_id}_{first_name}_{last_name}_{project_title}" \
  --student-id 75589 \
  --approved-manifest /path/to/approvals.json
```

The approval file does not contain or override metadata values. It only
authorises the listed source labels to cross the confidence gate. Missing
required fields still block the write, guidance/template documents require
this explicit approval even when their fields look complete, collisions still
follow the selected collision policy, and unlisted files remain
`review_required`.

The JSON and CSV reports also include `document_type` and `document_reason`.
Normal extracted documents are `likely_submission`; guidance/template files
are `guidance_template`; image-only files are `image_only`; and extraction or
operation failures are `unavailable`. Guidance/template files receive a
`guidance_template_review` gap in normal batch mode and cannot be written
without an explicit approval manifest. These fields explain why a file may
need closer review; they do not authorise a write and do not replace the
confidence gate.

Keep approval manifests local. Source labels can contain names or other
personal information, and the manifest is not suitable for public sharing.
