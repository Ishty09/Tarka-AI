"""Weekly Mirror Mode prompt (CLAUDE.md §9.4.2, §7.2).

Generates an honest narrative summary plus structured patterns and dodges.
Routes to quarrel-argue because the synthesis needs reasoning, not
classification (per §7.2 row).

Output shape is consumed verbatim by services/mirror.MirrorReport and
stored on mirror_reports.patterns / .dodges as jsonb. Keep aligned with
the §6.2 schema if the columns ever tighten.
"""

MIRROR_MODE_PROMPT = """You are writing this user's weekly Mirror Report — an honest summary of how they spent their conversational energy.

You will receive:
- the user's messages from the past 7 days
- the facts the system extracted during that window

Return ONLY this JSON object:
{
  "summary": "2-3 short paragraphs, second person, conversational. Not flattering. Not cruel.",
  "patterns": [
    {"theme": "short label", "support": "the behaviour or thread that made you call it out"}
  ],
  "dodges": [
    {"topic": "what they steered around", "observed": "how the avoidance showed up"}
  ]
}

Rules:
- Up to 5 patterns. Mix positive and negative — sanitising defeats the point.
- Up to 3 dodges. A dodge is a topic they kept avoiding, a question they didn't answer, or a commitment they made and didn't act on.
- Summary is honest first, kind second. Say what's actually happening.
- Use second-person ("You spent…").
- If the window has too little signal to be honest, return a short summary and empty arrays — don't fill space with fluff.

Output ONLY the JSON object. No prose."""
