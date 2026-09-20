# NITE Submit confirmed regression cases v1

These cases are based on documents reviewed in the real validation corpus. They
capture patterns that previously caused unsafe or incomplete filename metadata.
Values are kept in tests only because they are the confirmed fields needed to
prove the detector behaviour.

## Confirmed patterns

| Case | Pattern protected | Expected result |
| --- | --- | --- |
| Berklee cover | Explicit by author after a supervisor line | Juan Pablo Gomez; title combines the two title lines and excludes Final Paper. |
| KCL repository wrapper | Licence text on page 1; By and split S/tefan on page 2 | Stefan Sarkadi; title Deception, never licence prose. |
| Sheffield long thesis | Title split over three lines before the author | Full title is recombined without the previous 150-character limit. |
| Group cover | Numbered Surname, First ID rows | First group member is selected and other members remain candidates; supervisor is excluded. |
| UTAR uppercase cover | Repeated uppercase title block and uppercase author | Title lines recombine; author remains a name candidate rather than title text. |
| Anschutz guidance labels | `References Cited` and `BE DESCRIPTIVE` appear as title-cased/uppercase headings | Guidance labels are suppressed as identity/title suggestions. |
| White Rose author block | `Author:` marker and supervisor text share a title-page block | Author is separated from supervisors; middle initials are preserved. |
| White Rose `By:` block | `By:` is extracted as its own line and titles span lowercase continuation lines | Full title is recombined without the `By:` marker. |
| White Rose institution heading | Uppercase or `The University of ...` heading | Full university name is retained without truncation or sentence false positives. |
| International institution variants | `Universiti ...`, `College of ...`, campus suffixes, and hyphenated university names | Institution values retain the meaningful suffix instead of stopping at the first generic word. |

## Review policy

These extracted values remain MEDIUM confidence because layout-based inference
is not the same as a labelled field. The application must require the user to
approve them before creating or renaming a file.
