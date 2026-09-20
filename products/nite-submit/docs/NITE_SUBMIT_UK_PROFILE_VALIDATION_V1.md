# NITE Submit — UK Coursework Profile Validation v1

Validation date: 25 August 2026
Packaged build: NITE Submit 0.2.0

## Profile

Display name: **UK coursework (generic)**

Template:

`{module_code}_{student_id}_{project_title}`

The profile is a generic, editable module-code-first pattern. It is not an
official university-wide rule and must be replaced when a department gives a
different convention.

## Real UK PDF check

Input:

`real_validation_corpus/university_templates/edge_hill_hea3183_assignment_header.pdf`

The packaged CLI detected:

- module code: `HEA3183`
- saved student number: `75589`
- project-title candidate: `I have left margins of at least 4cm at the left hand side and 2 cm`
- document type: `guidance_template`

Dry-run preview:

`HEA3183_75589_I_have_left_margins_of_at_least_4cm_at_the_left_hand_side_and_2_cm.pdf`

The file remained `dry_run` and no PDF was written. The app showed the same
module-code-first preview, displayed the guidance/template warning, and kept
the approval gate active. This is the intended result for a public guidance
PDF: the profile is usable, but the user must not treat instructional prose as
their project title without review.

Results:

`real_validation_corpus/test_results/uk_profile_validation.2R7Wtw/`
