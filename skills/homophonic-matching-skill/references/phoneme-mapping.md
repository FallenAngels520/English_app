# Phoneme Mapping and Downgrade Rules

Use these rules to map English phonemes (ARPAbet) to approximate Mandarin pinyin.
When a phoneme has no close Mandarin equivalent, apply the downgrade table.
Keep multiple candidates per phoneme and expand to multiple pinyin sequences.

## Consonant mapping (ARPAbet -> pinyin)

- P -> p
- B -> b
- T -> t
- D -> d
- K -> k
- G -> g
- CH -> q / ch
- JH -> j / zh
- SH -> sh / x
- ZH -> zh / j
- S -> s
- Z -> z
- F -> f
- V -> w / f
- TH -> s / f
- DH -> z / d
- HH -> h
- M -> m
- N -> n
- NG -> ng (prefer "eng/ing/ang" depending on vowel)
- L -> l
- R -> l / r (Mandarin r) / er
- Y -> y
- W -> w

## Vowel mapping (ARPAbet -> pinyin)

- AA -> a
- AE -> ai / a
- AH -> a / e
- AO -> ao / o
- AW -> ao / ou
- AY -> ai
- EH -> e
- ER -> er / e
- EY -> ei
- IH -> i
- IY -> yi / i
- OW -> ou / o
- OY -> oi / ui
- UH -> u / ou
- UW -> u / wu

## Cluster handling

- Break illegal clusters by inserting a light vowel (a/e/er).
- Word-final clusters like -ts/-dz/-kt -> split into separate syllables (te-si, de-zi, ke-te).
- Prefer extra syllables over illegal merges.

## Stress and rhythm

- Keep stress as a weak constraint only; do not force tones.
- If needed, mark stressed syllables with more common or open vowels for readability.

## Candidate expansion

- For each phoneme, keep 2-3 pinyin options.
- Combine into multiple sequences (top 5-10) before Chinese phrase generation.
- Reject sequences that produce impossible Mandarin syllables.

## Low-confidence fallback

If the best candidates still score low coverage, do not force a homophone.
Switch to other mnemonic styles: roots/affixes, imagery, or story association.
