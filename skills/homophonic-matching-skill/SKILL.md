---
name: homophonic-matching-skill
description: Create or update workflows for English-to-Chinese homophonic matching that rely on phoneme/IPA (e.g., CMUdict) rather than spelling, including downgrade rules for missing sounds, candidate generation, scoring, and fallback mnemonics when confidence is low. Use when asked to design, implement, or improve homophonic mnemonic matching or related scoring/output formats.
---

# Homophonic Matching (Phoneme-First)

## Quick workflow

1) Convert English input to phonemes via CMUdict (ARPAbet) or IPA.
2) Map phonemes to approximate Mandarin pinyin with explicit downgrade rules for missing sounds.
3) Expand into multiple pinyin sequences (top-N) rather than a single path.
4) Generate multiple Chinese candidate phrases per sequence.
5) Score candidates by phoneme similarity and surface quality.
6) If confidence is low, switch to non-homophonic mnemonic modes.

## Rules of engagement

- Treat homophonic matching as "find the most similar pronunciation," not "generate a Chinese sentence."
- Avoid spelling-driven analogies (e.g., ambulance -> an-bu-lan-si). Prefer phoneme distance.
- Always output Top 3 candidates with labels for coverage, readability, and naturalness.
- If scores are weak, explicitly decline a homophonic result and offer alternate mnemonics.

## Scoring guidance

- Use weighted phoneme edit distance between source phonemes and reconstructed pinyin phonemes.
- Penalize illegal Mandarin syllable shapes or hard-to-read consonant clusters.
- Encourage common characters and natural phrase rhythm over exotic or rare characters.
- Prefer slight syllable expansion (insert schwa-like fillers) over illegal merges.

## Output template

Return three candidates:

1) Candidate: <phrase>
   Coverage: high/medium/low
   Readability: smooth/ok/rough
   Naturalness: phrase/fragment/awkward

If no candidate reaches medium coverage, return:

- "Homophone confidence low" plus 1-2 alternative mnemonic strategies.

## References

- Phoneme mapping and downgrade rules: `references/phoneme-mapping.md`
