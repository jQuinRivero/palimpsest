# Diff engine

How palimpsest turns two canonical `Document`s into a block-aligned, word-level collation that understands moved, split, and merged passages.

**Status:** Draft

**Related:** [Normalization](./03-normalization.md) · [Data schema](./05-data-schema.md) · [Performance and scale](./11-performance-and-scale.md) · [Edge cases](./12-edge-cases.md) · [ADR-0001](./adr/0001-diff-match-patch-fork.md) · [ADR-0004](./adr/0004-server-side-diff-computation.md)

---

## Why a plain diff is not enough

`diff-match-patch` produces an excellent *linear* diff: a flat sequence of equalities, insertions, and deletions. Run it over two manuscripts and it will faithfully report every character that changed. It will also report that a paragraph moved from chapter two to chapter nine as a large deletion followed, several thousand tokens later, by a large insertion — which is true, and useless. A scholar looking at that output learns nothing about the structural evolution of the text, which is frequently the whole point of the comparison.

The same failure appears at smaller scale. Split one long paragraph into two and a linear diff sees a deletion and two insertions. Merge two into one and it sees the reverse. Re-paragraph a chapter without changing a single word and a line-oriented tool reports a total rewrite.

palimpsest therefore runs the diff in **two stages**:

1. **Alignment** establishes which block in Manuscript A corresponds to which block in Manuscript B, and classifies each correspondence — matched, moved, split, merged, inserted, or deleted.
2. **Token diffing** runs `diff-match-patch` at word granularity *within* each aligned pair, and only within it.

Stage 1 is where the structural intelligence lives and is entirely our own; stage 2 is a proven library doing what it is good at. This division is the project's answer to the "don't reinvent the wheel" constraint: we do not write a diff algorithm, we write the alignment that makes a diff algorithm meaningful for prose.

```
Document A ─┐
            ├─► tokenize ─► align blocks ─► diff aligned pairs ─► metrics ─► ComparisonResult
Document B ─┘              (stage 1)        (stage 2)
```

---

## Tokenization

The unit of diffing is the **token**. Under the default `Granularity.WORD`, a token is *a run of non-whitespace characters together with the whitespace that follows it*.

```python
def tokenize(text: str) -> list[str]:
    """Split into word tokens, each carrying its trailing whitespace."""
    return re.findall(r"\S+\s*", text)
```

Carrying the trailing whitespace inside the token matters more than it appears to. It means the concatenation of a block's tokens reconstructs the block's text exactly — no separator bookkeeping, no lost spacing — which in turn means the client can render `a_tokens` and `b_tokens` by simple concatenation and get back the original prose. That reconstruction property is asserted as an invariant in [testing](./13-testing-strategy.md).

The exactness guarantee applies to `a_tokens` and `b_tokens`. The unified `tokens` stream is a third rendering: it interleaves runs that were never adjacent in either witness, so it must insert separators to stop words fusing, and it therefore matches each pane word for word rather than byte for byte. See [data schema](./05-data-schema.md).

`Granularity.CHARACTER` is available as a `DiffOptions` override, where each token is a single character. It is appropriate for scripts without word separators (see [edge cases](./12-edge-cases.md) on CJK) and for close orthographic study, and it is substantially more expensive.

Tokenization runs on the **normalized** block text produced by [normalization](./03-normalization.md). The diff engine never sees raw parser output.

### Comparison keys

Some `DiffOptions` change how tokens *compare* without changing how they *render*. `ignore_case`, `ignore_punctuation`, and `normalize_whitespace` are applied to a derived **comparison key** for each token; the original surface form is what gets returned in the payload. A researcher who enables `ignore_case` sees the manuscript's real capitalisation on screen while the engine treats `The` and `the` as equal.

```python
def comparison_key(token: str, options: DiffOptions) -> str:
    key = token
    if options.normalize_whitespace: key = key.strip() + " "
    if options.ignore_case:          key = key.casefold()
    if options.ignore_punctuation:   key = strip_punctuation(key)
    return key
```

---

## Stage 2 first: word-level diffing with `diff-match-patch`

It is easier to explain stage 2 before stage 1, because stage 1 is defined partly in terms of the cost of stage 2.

### The word-mode remapping

`diff-match-patch` diffs **characters**. Applied naively to prose it produces character-level output — `sat` versus `set` becomes an equality, a deletion, an insertion, and an equality inside a single word — which is visually intolerable in long-form reading and semantically wrong for textual scholarship. What we want is *word-level* output.

The library ships the machinery for this in `diff_linesToChars` and `diff_charsToLines`, which map each unique line to a single Unicode code point, diff the resulting compact strings, and map back. The technique is not restricted to lines: it works for any tokenization. We apply it at word granularity.

Retaining access to these two helpers is the reason [ADR-0001](./adr/0001-diff-match-patch-fork.md) selects the pure-Python community fork over the much faster C++ binding, whose simplified API omits them.

```python
def diff_tokens(a_tokens: list[str], b_tokens: list[str],
                options: DiffOptions) -> list[Token]:
    vocabulary: dict[str, str] = {}
    def encode(tokens: list[str]) -> str:
        out = []
        for t in tokens:
            key = comparison_key(t, options)
            if key not in vocabulary:
                vocabulary[key] = chr(len(vocabulary) + 1)
            out.append(vocabulary[key])
        return "".join(out)

    dmp = diff_match_patch()
    diffs = dmp.diff_main(encode(a_tokens), encode(b_tokens), checklines=False)
    dmp.diff_cleanupSemantic(diffs)
    return decode_to_tokens(diffs, a_tokens, b_tokens)
```

Each unique token type is assigned one code point, the two token sequences become two short strings, and `diff_main` runs its Myers diff over an alphabet of words rather than letters. Decoding walks the returned operations and re-emits the *original* surface tokens — consuming from `a_tokens` for equalities and deletions, from `b_tokens` for insertions — so the output preserves the manuscript exactly.

`diff_cleanupSemantic` is applied and `diff_cleanupEfficiency` is not. The former coalesces small scattered edits into larger human-meaningful ones, which is precisely what a reader wants; the latter optimises for patch size, which is irrelevant here since we never produce patches.

### Worked example

Manuscript A: `The cat sat on the mat.`
Manuscript B: `The black cat sat upon the mat.`

| Step | Manuscript A | Manuscript B |
|---|---|---|
| Tokens | `["The ", "cat ", "sat ", "on ", "the ", "mat."]` | `["The ", "black ", "cat ", "sat ", "upon ", "the ", "mat."]` |
| Vocabulary | `The `→`\u0001`, `cat `→`\u0002`, `sat `→`\u0003`, `on `→`\u0004`, `the `→`\u0005`, `mat.`→`\u0006`, `black `→`\u0007`, `upon `→`\u0008` | |
| Encoded | `\u0001\u0002\u0003\u0004\u0005\u0006` | `\u0001\u0007\u0002\u0003\u0008\u0005\u0006` |

`diff_main` over those two strings returns:

```
EQUAL  \u0001          DELETE \u0004
INSERT \u0007          INSERT \u0008
EQUAL  \u0002\u0003    EQUAL  \u0005\u0006
```

Decoded back to surface tokens:

```json
[
  { "text": "The ",     "status": "UNCHANGED" },
  { "text": "black ",   "status": "INSERTION" },
  { "text": "cat sat ", "status": "UNCHANGED" },
  { "text": "on ",      "status": "DELETION"  },
  { "text": "upon ",    "status": "INSERTION" },
  { "text": "the mat.", "status": "UNCHANGED" }
]
```

Note what did *not* happen: `on` → `upon` was not reported as an insertion of the two characters `up`. At word granularity it is a deletion and an insertion of whole words, which is how a reader perceives it and how an editor would describe it.

### The three token streams

Every `DiffBlock` carries three token arrays, all derived from the single diff above:

| Field | Contents | Consumed by |
|---|---|---|
| `tokens` | The full unified stream — `UNCHANGED`, `INSERTION`, and `DELETION` interleaved | Unified view |
| `a_tokens` | `UNCHANGED` + `DELETION` only | Manuscript A pane in synoptic view |
| `b_tokens` | `UNCHANGED` + `INSERTION` only | Manuscript B pane in synoptic view |

They are computed on the server rather than derived on the client because filtering is cheap but *getting it wrong* is a subtle rendering bug, and because it keeps the client a pure renderer ([ADR-0004](./adr/0004-server-side-diff-computation.md)). Concatenating `a_tokens[*].text` must reproduce Manuscript A's block text exactly, and likewise for B.

### Vocabulary ceiling

The remapping assigns one code point per unique token type, so the ceiling is the Unicode range — 1,114,111 distinct types. A 100,000-word English manuscript has on the order of 10,000–20,000 distinct word types, so the ceiling is not a practical concern. It is nonetheless checked: exceeding it raises `DIFF_BUDGET_EXCEEDED` rather than producing corrupt output.

---

## Stage 1: block alignment

Alignment decides, for every block in A, which block or blocks in B it corresponds to. This is a sequence-alignment problem over blocks, and a naive treatment is quadratic: 2,000 blocks against 2,000 blocks is four million similarity computations. The pipeline below is ordered specifically to make the expensive step operate on as few candidate pairs as possible.

### Similarity

Block similarity is `rapidfuzz.fuzz.ratio` over the normalized block texts, scaled to `0.0–1.0`. `fuzz.ratio` is a normalized Indel similarity and is **order-sensitive**, which is required: `token_set_ratio` and friends discard word order and would happily match a paragraph against its own scrambled rewrite.

`rapidfuzz` is used rather than `python-Levenshtein` on licence grounds — MIT against GPL-2.0, which is disqualifying in an Apache-2.0 project ([ADR-0002](./adr/0002-pdfplumber-over-pymupdf.md) sets the general rule).

### The pipeline

**1 — Anchor on exact matches.** Hash the normalized text of every block in both witnesses. Blocks whose hashes match uniquely are anchored immediately at zero comparison cost. In realistic manuscript revisions the large majority of blocks are untouched, so this single step typically resolves most of the document and pins the sequence.

**2 — Confine search to the gaps.** Anchors partition both witnesses into corresponding regions. An unmatched A block lying between anchors *i* and *j* can only sensibly align with an unmatched B block lying between the same two anchors. The quadratic problem collapses into a series of small independent sub-problems, each solvable in isolation — and, being independent, parallelisable.

**3 — Prefilter on length.** Within a gap, reject candidate pairs whose token-count ratio falls outside a plausible band before computing any similarity. A 40-token paragraph cannot be a revision of a 900-token one. This is an integer comparison discarding candidates that a string metric would spend real time rejecting.

**4 — Score the survivors.** `rapidfuzz.process.cdist` computes the remaining pairwise scores as a matrix, with `score_cutoff` set to `align_threshold` so sub-threshold pairs are discarded inside the C++ layer and never materialise in Python.

**5 — Assign.** Greedy best-first: take the highest-scoring available pair, commit it, remove both blocks from consideration, repeat until no pair scores at or above `align_threshold` (default `0.50`). Optimal assignment via the Hungarian algorithm is *not* used. Gap sub-problems are small, greedy and optimal agree on almost all of them, and greedy is stable, explicable, and cheap. When a scholar asks why two paragraphs were matched, "they were each other's best remaining candidate at 0.83" is an answer; a global optimum over a cost matrix is not.

**6 — Detect splits and merges.** See below.

**7 — Detect moves.** See below.

**8 — Classify the remainder.** Any A block still unmatched is `DELETED`; any B block still unmatched is `INSERTED`.

### Split and merge detection

A split is invisible to pairwise matching. If A's block 12 became B's blocks 12 and 13, then `similarity(a12, b12)` and `similarity(a12, b13)` are each roughly half of what a match needs, and both may fall below threshold — so the engine would report one deletion and two insertions, which is exactly the failure this stage exists to prevent.

The test is on the **concatenation**. For each unmatched A block, take the runs of consecutive unmatched B blocks in the same gap and score the A block against their joined text:

```python
def detect_split(a_block, b_run, options) -> bool:
    joined = " ".join(b.text for b in b_run)
    combined = similarity(a_block.text, joined)
    best_individual = max(similarity(a_block.text, b.text) for b in b_run)
    return combined >= options.align_threshold and combined > best_individual + SPLIT_MARGIN
```

Both conditions are load-bearing. The first establishes that the concatenation is a real match. The second — that the concatenation beats the best individual member by a margin — prevents a spurious split when one member is already a good match on its own and the others are unrelated text that merely happened to sit next to it.

All blocks participating in a split share a `group_id` and are emitted with `BlockStatus.SPLIT`; the client uses `group_id` to draw a single connector spanning the group. Merge detection is the mirror image, with the roles of A and B exchanged, producing `BlockStatus.MERGED`.

#### Worked example: a split, and how it differs from a rewrite

**Manuscript A, block 12:**
> It was a long crossing. The waves were grey from the first morning to the last, and he remembered almost nothing of the voyage itself.

**Manuscript B, block 12:**
> It was a long crossing.

**Manuscript B, block 13:**
> The waves were grey from the first morning to the last, and he remembered almost nothing of the voyage itself.

Pairwise scoring gives `similarity(a12, b12) ≈ 0.21` and `similarity(a12, b13) ≈ 0.85`. Under pairwise matching alone, `b12` would be reported as an insertion and `a12`/`b13` as a heavily edited pair — a plausible-looking but wrong reading of what the author did.

The concatenation test gives `similarity(a12, b12 + b13) ≈ 1.00`, which clears the threshold and beats the best individual score of `0.85` by well over the margin. The engine emits `b12` and `b13` as `SPLIT` sharing one `group_id`, with the word-level diff showing no token changes at all. The summary reports a structural change and zero edits — which is the true account: the author changed the paragraphing and not one word.

Now contrast a genuine rewrite where A's block 12 was replaced by two unrelated paragraphs. The concatenation scores near zero, no split is declared, and the engine reports one `DELETED` and two `INSERTED` blocks. The two cases are distinguished by evidence rather than by guesswork.

### Move detection

After assignment, every matched pair has an A ordinal and a B ordinal. Read the B ordinals in A order and the question becomes: which of these are out of sequence?

The principled answer is the **longest increasing subsequence**. Blocks belonging to the LIS are in their original relative order and are *not* moved; blocks outside it are exactly the minimal set whose displacement explains the reordering. LIS runs in O(n log n), and choosing the minimal set matters — a naive "compare each block's index to its neighbour's" approach flags a whole chapter as moved when a single paragraph was lifted out of it.

```python
def detect_moves(pairs: list[tuple[int, int]], options: DiffOptions) -> set[int]:
    if not options.detect_moves:
        return set()
    in_place = longest_increasing_subsequence([b for _, b in pairs])
    return {a for i, (a, _) in enumerate(pairs) if i not in in_place}
```

A moved block is emitted with `BlockStatus.MOVED` and a `move_distance` giving the signed displacement in block ordinals — negative for a passage moved earlier in the text, positive for later. A block that was both moved and edited is reported as `MOVED`; the structural fact dominates, and its `metrics` still carry the token-level edit counts so nothing is hidden.

**Move detection has a quality ceiling and the specification is honest about it.** Highly repetitive text — verse refrains, litanies, legal boilerplate, epistolary formulae — produces blocks that are legitimately near-identical to several candidates, and the alignment may pair the wrong ones and then report a flurry of moves that no author made. Two mitigations apply. `move_threshold` (default `0.75`) is deliberately higher than `align_threshold` (default `0.50`), so a pair must be a strong match before its displacement will be reported as a move at all. And `detect_moves` is exposed to the reader as `?moves=off`, because sometimes the right answer is to let the scholar switch off a heuristic that is fighting the text.

---

## Metrics

Metrics are computed at block level and aggregated to the document. Every definition below is normative; the client formats these numbers and does not compute them.

### Block metrics

| Field | Definition |
|---|---|
| `similarity` | `rapidfuzz.fuzz.ratio` of the two block texts, `0.0–1.0`. For `INSERTED` and `DELETED` blocks it is `0.0` |
| `insertions` | Count of `INSERTION` tokens |
| `deletions` | Count of `DELETION` tokens |
| `edit_count` | `insertions + deletions` |
| `churn` | `edit_count / max(1, len(a_tokens) + len(b_tokens))`, `0.0–1.0` |

### Document metrics

| Field | Definition |
|---|---|
| `insertions`, `deletions`, `unchanged_tokens` | Sums over all blocks |
| `edit_count` | `insertions + deletions` |
| `similarity` | `2 × unchanged_tokens / (a_word_count + b_word_count)` — a Dice coefficient over tokens, `1.0` for identical witnesses |
| `churn` | `edit_count / max(1, a_word_count + b_word_count)` |
| `blocks_moved`, `blocks_split`, `blocks_merged` | Counts of blocks bearing each `BlockStatus` |
| `a_word_count`, `b_word_count` | Token counts per witness |

Document `similarity` is defined as a token-weighted Dice coefficient rather than a mean of block similarities, because averaging block scores lets a one-line heading count as much as a thousand-word chapter. Two identical witnesses score exactly `1.0`; two witnesses sharing no vocabulary score `0.0`.

The structural counts are reported separately from `edit_count` and never folded into it. A re-paragraphing with no word changed must read as *high structural change, zero edits* — collapsing those into one number would destroy the distinction the whole engine exists to draw.

---

## Options

| Option | Default | Effect |
|---|---|---|
| `granularity` | `WORD` | `WORD` or `CHARACTER` tokenization |
| `detect_moves` | `true` | Run LIS move detection; when false, displaced blocks report as `MODIFIED` or `UNCHANGED` in place |
| `align_threshold` | `0.50` | Minimum similarity for two blocks to be considered a pair |
| `move_threshold` | `0.75` | Minimum similarity before a displaced pair is reported as `MOVED` |
| `ignore_case` | `false` | Case-insensitive comparison keys; surface forms preserved |
| `ignore_punctuation` | `false` | Punctuation-insensitive comparison keys; surface forms preserved |
| `normalize_whitespace` | `true` | Whitespace runs collapse for comparison purposes |

Options are echoed back in `ComparisonResult.options` so that a stored comparison is self-describing and a shared URL is reproducible.

---

## Determinism

The engine is a pure function of `(Document A, Document B, DiffOptions)`. Given the same inputs it must produce a byte-identical `ComparisonResult`, ignoring the id and timestamp fields. Nothing in the pipeline may depend on dictionary iteration order, set ordering, wall-clock time, or hash randomisation — where ties occur in greedy assignment they are broken by the lower A ordinal, then the lower B ordinal, and never arbitrarily.

Determinism is not fastidiousness. The golden-corpus regression suite in [testing](./13-testing-strategy.md) is the only practical defence against silent quality drift in a system whose output is partly a matter of judgement, and that suite is worthless if the engine is not reproducible.

---

## Complexity

| Stage | Complexity | Notes |
|---|---|---|
| Tokenization | O(n) | Linear in characters |
| Anchoring | O(n + m) | Hash table over blocks |
| Gap scoring | O(Σ gᵢ × hᵢ) | Product of unmatched blocks per gap, not of the whole document — this is the point of anchoring |
| Assignment | O(k log k) per gap | Sorting candidate pairs |
| Split/merge | O(Σ gᵢ × w) | `w` is the bounded concatenation window |
| Move detection | O(p log p) | LIS over matched pairs |
| Token diffing | O(Σ dᵢ log dᵢ) | Myers diff per aligned pair, over *block-sized* inputs rather than the whole document |

The decisive property is that stage 2 never sees the whole manuscript. Running `diff_main` over two 120,000-token documents would be punishing; running it over a few thousand independent paragraph pairs of a hundred tokens each is trivial, and embarrassingly parallel besides. Alignment is what buys that, which is why [performance and scale](./11-performance-and-scale.md) treats stage 1 as the component to watch and defines the degradation ladder in terms of it.
