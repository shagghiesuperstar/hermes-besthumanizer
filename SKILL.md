---
name: humanize-and-score
description: Use when text must read as human, or when you must prove a rewrite helped. Score first, rewrite only what is broken, never ship a rewrite that scores lower.
---

# Humanizing without guessing

Two tools do the work, and the order matters: **measure, then rewrite, then measure again.**

## The loop

1. `score_text` on the passage. It returns `human_probability` (0-100, higher is more human)
   and `detected_patterns` — each entry names the rule and the span that fired it.
2. If the score is **75 or higher**, do not rewrite. The text already reads human; a rewrite
   buys nothing and risks flattening the rhythm that earned the score. Say so and stop.
3. Otherwise `humanize_text` with the right `mode` — `academic` for papers and reports,
   `general` for posts, email, docs. Pass `voice_sample` when you have two or three paragraphs
   of the author's own writing; it steers cadence, not vocabulary.
4. `score_text` on the output and report both numbers. If `scoreAfter` is not higher than
   `scoreBefore`, the honest answer is "this passage was already near the ceiling" — the
   server guarantees the output never scores lower, so an unchanged score is a real result.

## What the detector actually measures

Cadence and tells, not provenance. Prose with short, uneven sentences and no tell clusters
reads human whatever produced it; prose padded into uniform nominalised sentences reads
machine-like whatever edited it. So when you *write* rather than rewrite, the cheapest
insurance is: vary sentence length hard (some six-word sentences, some twenty-eight-word ones),
avoid the tell lexicon (`delve`, `leverage`, `robust`, `tapestry`, `cornerstone`, `seamless`,
`pivotal`, `underscore`), and keep nominalisations under about two per hundred words.

## Reading the output

- `scoreBefore` / `scoreAfter` — measured over the whole document, not per sentence.
- `llm` — which model ran and, when the server kept your text instead, why it reverted
  (`mechanical pass only`, or `already read human, left as written`). Quote that reason; it is
  the difference between "the rewrite failed" and "there was nothing to fix".
- `detected_patterns` — use these as the evidence when explaining *why* a passage read as
  machine-written. Name the rule, quote the span, do not editorialise.

## Cost

Scoring is free and non-metering: no model in the path, no words debited, same input always
gives the same number, so call it as often as you like. Only `humanize_text` meters, and it
meters the **input** word count. `premium` draws 3× on Free and Pro plans and 1× on Unlimited.

## X accounts

`score_x_account` scores a public account's recent original posts: median, distribution, and the
posts that carry the tells, plus a share URL that unfurls with the verdict. Deterministic and
free. Do not present a median as a judgement of the person — the verdict describes the writing.
