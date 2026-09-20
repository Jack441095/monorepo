#!/usr/bin/env python3
"""Post-process generated notes to fix basic formatting for paraphrase script."""

import re
from pathlib import Path

NOTES_DIR = Path(__file__).resolve().parents[2] / "apps/backend/src/kenn/Training_Data_Notes"

def fix_format(content: str) -> str:
    # Remove markdown headers (##, ###)
    content = re.sub(r'^#{2,3}\s*', '', content, flags=re.MULTILINE)
    # Remove bold markdown
    content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)
    # Fix "Short Answer:" -> "Short answer:"
    content = re.sub(r'^Short Answer:', 'Short answer:', content, flags=re.MULTILINE)
    content = re.sub(r'^Short answer:', 'Short answer:', content, flags=re.MULTILINE)
    # Fix "Try This:" -> "Try this:"
    content = re.sub(r'^Try This:', 'Try this:', content, flags=re.MULTILINE)
    # Fix "Why It Matters:" -> "Why it matters:"
    content = re.sub(r'^Why It Matters:', 'Why it matters:', content, flags=re.MULTILINE)
    # Fix "Related Questions:" -> "Related questions:"
    content = re.sub(r'^Related Questions:', 'Related questions:', content, flags=re.MULTILINE)
    # Remove "First Actionable Step:", "Second Step:", "Continue with 6-12 Steps:" lines
    content = re.sub(r'^\d+\.\s+\*\*First Actionable Step:\*\*', '1.', content, flags=re.MULTILINE)
    content = re.sub(r'^\d+\.\s+\*\*Second Step:\*\*', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\d+\.\s+\*\*Continue with 6-12 Steps:\*\*', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\d+\.\s+\*\w+ Step:\*\*', '', content, flags=re.MULTILINE)
    # Remove bullet points inside numbered steps
    content = re.sub(r'^\s*-\s+', '   ', content, flags=re.MULTILINE)
    # Clean up extra blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip() + '\n'

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python fix_format.py <note-file> [<note-file>...]")
        sys.exit(1)


    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_absolute():
            path = NOTES_DIR / path
        if not path.exists():
            print(f"Not found: {path}")
            continue


        content = path.read_text(encoding="utf-8")
        fixed = fix_format(content)
        path.write_text(fixed, encoding="utf-8")
        print(f"Fixed: {path.name}")

if __name__ == "__main__":
    main()