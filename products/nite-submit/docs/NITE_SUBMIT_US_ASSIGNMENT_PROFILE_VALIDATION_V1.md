# NITE Submit — US assignment-code profile validation v1

Validation date: 25 August 2026
Packaged build: NITE Submit 0.2.0

## Profile

Display name: **US assignment code (generic)**

Template:

```text
{last_name}_{assignment_code}
```

This is an editable starting point for coursework instructions resembling
`LASTNAME_A#`. It is not an official US-wide rule. A real assignment brief
always takes precedence.

## Safety validation

The available University of Washington/Tacoma fixture is official capstone
guidance rather than a student submission. The packaged CLI was run with the
profile and a supplied fallback student number:

```sh
artifacts/Submit-0.2.0-macOS.app/Contents/MacOS/nitesubmit-cli batch \
  <isolated-input> --out <isolated-output> --student-id 75589 \
  --template '{last_name}_{assignment_code}' --dry-run
```

Result:

- `document_type`: `guidance_template`
- `status`: `review_required`
- required gap: `assignment_code`
- output: none

This confirms that the profile does not turn institutional instructions into
a student filename, even when a fallback student number is supplied. A
positive write check remains intentionally pending until an authorised
student-owned or explicitly authorised US coursework PDF provides a confirmed
last name and assignment code.
