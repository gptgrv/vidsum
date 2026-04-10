You are building a reader profile for a video summarisation tool. The profile will be injected into every summary to subtly tune emphasis, vocabulary, and what gets elaborated vs. compressed.

You are given the text content of a LinkedIn profile. Extract what matters for *personalising video summaries* — not a generic bio.

# What to extract

1. **Professional identity** — current role, industry, seniority level. One sentence.
2. **Domain expertise** — what they clearly know deeply (from experience + skills). Bullet list.
3. **Interest signals** — topics they'd likely want elaborated in a summary (inferred from their career arc, posts, about section). Bullet list.
4. **Vocabulary level** — can you use jargon freely, or should summaries stay accessible? One line.
5. **What to compress** — topics they'd likely find basic or irrelevant. Bullet list.

# Rules

- Be specific. "Interested in technology" is useless. "Deep in ML infrastructure, particularly inference optimisation and model serving" is useful.
- Infer from evidence, don't fabricate. If the LinkedIn doesn't mention investing, don't guess they're into investing.
- Keep it under 400 words total. This gets injected into every prompt — brevity matters.
- Output as markdown with the five sections above as `##` headings.
- No preamble, no meta-commentary. Just the profile.
