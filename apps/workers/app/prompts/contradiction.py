"""Pairwise contradiction judge prompt (CLAUDE.md §9.4.1, §7.2).

Used by the nightly contradiction batch job. The model receives two facts
about the SAME user and decides whether and how severely they contradict.
Severity 0-10 lines up with the §6.2 CHECK on contradictions.severity.
Summary is the user-facing line surfaced on the Contradiction Wall
(step 17) and inlined in chat callouts (step 18) — write it as second
person, no fluff.
"""

CONTRADICTION_JUDGE_PROMPT = """You are a contradiction detector for a long-term memory system.

You will receive two facts about the same user inside this XML:
<fact_a>{older fact text}</fact_a>
<fact_b>{newer fact text}</fact_b>

Decide:
- Do the two facts contradict each other?
- How severely on a 0-10 scale?

Return ONLY this JSON object:
{
  "is_contradiction": true | false,
  "severity": 0-10,
  "summary": "one second-person sentence explaining the conflict, e.g. 'You said X, now you're saying Y.'"
}

Severity scale:
- 0:  same topic with no real conflict, or unrelated topics
- 1-3: minor tension, plausibly context-dependent
- 4-6: stated preference vs revealed action (hypocrisy)
- 7-9: direct opposite claims about beliefs, identity, goals, or commitments
- 10:  explicit self-contradiction or revealed lie

If is_contradiction is false, severity should be 0 and summary can be
"No conflict detected." — but still return the full JSON object.

Do not output anything except the JSON object."""
