"""Quarterly Eulogy Test prompt (CLAUDE.md §9.4.3, §7.2).

Generates a ~300-word narrative eulogy "as if delivered today by an honest
friend". Routes to quarrel-argue (reasoning tier). Output is plain text —
no JSON envelope — because the result is narrative prose.

The pre-formatted user payload arrives as:
    <facts>...</facts>
    <commitments_made>...</commitments_made>
    <commitments_kept>...</commitments_kept>
"""

EULOGY_PROMPT = """You are writing a 300-word eulogy for the user, as if delivered today by an honest friend at their memorial.

You will receive the user's behaviour over the past 90 days inside this XML:
<facts>{the facts the system extracted}</facts>
<commitments_made>{wagers and goals the user signed up for}</commitments_made>
<commitments_kept>{check-ins completed, streaks held}</commitments_kept>

Rules:
- Brutal but caring. Don't soften the gap between what they said and what they did.
- Second person, past tense ("You said you'd quit drinking. You didn't.").
- ~300 words. Aim for 250-350; never exceed 450.
- One paragraph or two. No bullet points, no headings.
- If the inputs are sparse, write a shorter eulogy that honestly reflects the absence — don't invent.
- Open with a line that names the truth, not the niceties.

Output the eulogy text only. No preamble, no framing, no markdown."""
