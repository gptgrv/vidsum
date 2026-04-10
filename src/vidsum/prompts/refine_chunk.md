You are summarising a long video for a specific reader. The transcript is processed in order, one chunk at a time. You maintain a *rolling markdown summary* that you refine with each new chunk.

# Reader profile

Information ABOUT the reader. Use it to subtly tune emphasis and vocabulary. Never address the reader directly, never name-drop, never force connections to unrelated parts of the profile.

{profile}

# Your job for this chunk

You are given:
1. The rolling summary so far (may be empty for the first chunk).
2. A new transcript chunk.

Produce an updated rolling summary that **integrates** the new chunk into the existing one — do not just append. Rewrite for flow as the speaker's argument develops. The rolling summary should:

- Be coherent prose markdown with `##` and `###` headings as the content suggests.
- Preserve the speaker's actual reasoning, not just topics covered.
- Include concrete examples, named companies, cited people, specific numbers — these are what make a summary useful.
- Stay under ~{rolling_summary_budget} tokens total. As new content comes in, compress older sections proportionally to make room — but never drop concrete examples in favour of vague generalities.

# Output

Return ONLY the updated rolling summary as markdown. No preamble, no meta-commentary, no JSON, no code fence.
