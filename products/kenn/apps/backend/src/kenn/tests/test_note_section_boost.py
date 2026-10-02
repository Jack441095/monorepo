"""A note's own "Related questions" block must not outrank the sections that answer the question.

The block is a list of the note's own question phrasings, so it scores highest exactly when the producer
asks something the note covers. On the 4642-chunk index it took 391 of 2912 top-4 slots across 728 recorded
producer queries and every one of those slots was then discarded: llm_rewrite._clean_chunk_for_synthesis
returns "" for a Related-questions chunk because there is no answer in a question list. "Why does my bass
disappear when the kick plays?" left the model one usable excerpt out of four.
"""

from __future__ import annotations

from pathlib import Path

from kenn.core.chat_formatting import note_sections
from kenn.retrieval.build_index import (
    QUESTION_LIST_SECTION,
    Chunk,
    build_terms,
    iter_note_chunks,
)
from kenn.retrieval.retrieval import bm25_search

# The real note that produced the worst case, trimmed to the sections the indexer reads.
NOTE_TAGS = "attack bass compression release sidechain"
SIDE_CHAIN_NOTE = f"""# Sidechain Bass To Kick
Type: note
Status: Approved
Tags: {NOTE_TAGS}

Short answer:
Use a compressor on the bass with the kick as the sidechain input, 4:1, release 80-150 ms.

Try this:
1. Group the bass layers to a bus.
2. Enable Sidechain and pick the kick as the external source.

Related questions:
- Why does my bass disappear when the kick plays?
- What release time for sidechain compression?
"""


def _search(query: str, chunks: list[Chunk], limit: int = 4) -> list[tuple[float, str, str]]:
    records = [chunk.__dict__ for chunk in chunks]
    terms = build_terms(chunks)
    return [
        (score, chunk.get("section", ""), chunk.get("source", ""))
        for score, chunk in bm25_search(query, records, terms, limit=limit)
    ]


def test_a_notes_related_questions_section_does_not_outrank_its_own_body_sections_for_a_query_it_echoes(
    tmp_path: Path,
) -> None:
    """The question list echoed the query almost verbatim and still won the top slot.

    "Why does my bass disappear when the kick plays?" is a literal line in the block, so under the old
    doubled title-and-tag boost every section of the note scored alike and the shortest one — the question
    list — took rank 1 with three of four slots gone. It cannot recur because the block is not a
    retrievable chunk at all.
    """
    note = tmp_path / "sidechain-bass-to-kick.md"
    note.write_text(SIDE_CHAIN_NOTE, encoding="utf-8")

    chunks = iter_note_chunks(note)
    sections = [chunk.section for chunk in chunks]
    assert QUESTION_LIST_SECTION not in sections, \
        f"the question list is back in the index: {sections}"

    results = _search("Why does my bass disappear when the kick plays?", chunks)
    assert results, "the note must still be retrievable"
    assert all(section != QUESTION_LIST_SECTION for _score, section, _source in results)
    assert results[0][0] > 0
    assert results[0][1] in {"Short answer", "Try this"}, \
        f"the top hit should be a body section, got {results}"


def _chunk(section: str, body: str, tags: str = NOTE_TAGS) -> Chunk:
    """The chunk shape iter_note_chunks builds, so the boost can be tested on its own."""
    return Chunk(
        id=f"sidechain-bass-to-kick-note-{section}",
        source="sidechain-bass-to-kick.md",
        page=0,
        text=(
            "# Sidechain Bass To Kick\nType: note\nStatus: Approved\n"
            f"Tags: {tags}\n\nSection: {section}\n{section}:\n{body}"
        ),
        kind="note",
        title="Sidechain Bass To Kick",
        section=section,
    )


def test_the_boost_weighs_a_sections_own_body_over_the_metadata_every_section_of_a_note_shares() -> None:
    """Guard the boost on its own: only the body can tell two sections of one note apart.

    "external" appears only in this section's body and "attack" only in the tag string that every section
    of the note carries. The old boost doubled the tag string, so a word carrying no information about
    which section it came from outweighed the one word that does — that uniform lift is what let the note's
    question list score like the steps that answer it. Now the body word counts 3 and the tag word 2.

    This is not on its own enough to keep a question list out of the top four: a block holding the query
    verbatim still outscores the section answering it at any body weight, which is why iter_note_chunks
    stopped indexing it. The test is here because build_terms also runs at query time for a candidate
    index, so the boost has to discriminate there too and not only in the next full rebuild.
    """
    steps = _chunk("Try this", "1. Enable Sidechain and pick the kick as the external source.")
    counts = build_terms([steps])["term_counts"][0]

    assert counts["external"] > counts["attack"], (
        "a word in the note's shared tag string must not outweigh one in this section's body: "
        f"external={counts['external']} attack={counts['attack']}"
    )


def test_the_boost_still_lifts_a_note_whose_tags_and_title_match_the_query() -> None:
    """Dropping the doubled title and tags must not flatten note-level matching to nothing.

    The "Glue Compressor Bus" section below barely repeats the query in its body, while the unrelated delay
    note repeats the query words eight times in a long paragraph. Tag and title matching is what has to
    break that tie, exactly as it did before — the fix moved the weight onto the section body, it did not
    remove the note-level signal.
    """
    on_topic = Chunk(
        id="glue-compressor-note-1",
        source="glue-compressor-bus.md",
        page=0,
        text=(
            "# Glue Compressor Bus\nType: note\nStatus: Approved\n"
            "Tags: bus compression glue sidechain bass mixing\n\n"
            "Section: Short answer\nShort answer:\nKey it from the kick and set 2 dB of reduction."
        ),
        kind="note",
        title="Glue Compressor Bus",
        section="Short answer",
    )
    off_topic = Chunk(
        id="ping-pong-delay-note-1",
        source="ping-pong-delay.md",
        page=0,
        text=(
            "# Ping Pong Delay\nType: note\nStatus: Approved\nTags: delay echoes ambience tempo\n\n"
            "Section: Short answer\nShort answer:\n"
            + " ".join(
                [
                    "sidechain compression bass",
                    "A ping pong delay repeats the tail across the stereo field, and the delay time",
                    "sidechain compression bass echoes should sit behind the vocal, while bass sidechain",
                    "compression on a bus keeps the low end out of the way of the delay repeats.",
                ]
            )
        ),
        kind="note",
        title="Ping Pong Delay",
        section="Short answer",
    )

    results = _search("how do I use sidechain compression on bass", [off_topic, on_topic])
    assert results[0][2] == on_topic.source, \
        f"tag and title matching stopped carrying weight, top hit is {results[0]}"


def test_a_body_chunk_still_supplies_the_note_question_list_to_the_followup_prompts() -> None:
    """Removing the chunk must not remove the feature: the bullets come from the note file, not the chunk.

    suggestions._build_pool globs the notes directory and chat_formatting.load_note_text re-reads
    NOTES_DIR/<source>, so a "Short answer" chunk still yields the related-question prompts. Dropping the
    chunk is only safe while that is how both read them.
    """
    notes_dir = Path(__file__).resolve().parents[1] / "Training_Data_Notes"
    note_path = next(
        (
            path
            for path in sorted(notes_dir.glob("*.md"))
            if f"\n{QUESTION_LIST_SECTION}:" in path.read_text(encoding="utf-8", errors="replace")
        ),
        None,
    )
    assert note_path is not None, "no approved note carries a Related questions section"

    chunks = iter_note_chunks(note_path)
    assert chunks, f"{note_path.name} produced no chunks"
    assert all(chunk.section != QUESTION_LIST_SECTION for chunk in chunks)

    results = [(100.0, chunk.__dict__) for chunk in chunks[:1]]
    sections = note_sections(f"How do I apply {note_path.stem.replace('-', ' ')}?", results)
    assert sections["related"], f"related-question prompts vanished with the chunk: {sections}"
