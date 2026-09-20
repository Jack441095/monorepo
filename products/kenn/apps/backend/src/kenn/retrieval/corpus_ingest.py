from __future__ import annotations

import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

FORMAT_IDS = ("html", "markdown", "txt", "pdf", "json", "youtube", "vtt", "srt")
