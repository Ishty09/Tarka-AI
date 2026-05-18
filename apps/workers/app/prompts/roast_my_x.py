"""Roast My X prompt (CLAUDE.md §9.2.2, §7.2).

Single roast for whatever the user pasted, with target-aware framing.
Plain text out (no JSON envelope) so the marketing landing can render
the result inline. Routes via quarrel-argue — the anti-sycophant base
prompt would normally be layered on top, but for these one-shot landing
roasts we skip it: the prompt below is already sharp and doesn't need
the additional argue-rules adding token cost.
"""

# Mirror of packages/shared ROAST_TARGETS — both must move together.
ROAST_TARGETS: tuple[str, ...] = (
    "linkedin",
    "twitter",
    "resume",
    "github-pr",
    "dating-profile",
    "cover-letter",
    "code",
    "instagram",
    "portfolio",
    "startup-idea",
    "email-draft",
    "tweet",
    "business-name",
    "pitch-deck",
    "essay",
    "resignation-letter",
    "apology",
    "dating-bio",
    "linkedin-post",
    "wedding-speech",
)

# Human-readable label per target, used in the prompt body.
TARGET_LABELS: dict[str, str] = {
    "linkedin": "LinkedIn profile",
    "twitter": "X / Twitter bio or recent feed",
    "resume": "resume or CV",
    "github-pr": "GitHub pull request",
    "dating-profile": "dating-app profile",
    "cover-letter": "cover letter",
    "code": "code snippet",
    "instagram": "Instagram bio or recent posts",
    "portfolio": "portfolio site",
    "startup-idea": "startup pitch",
    "email-draft": "email draft",
    "tweet": "single tweet",
    "business-name": "business name and tagline",
    "pitch-deck": "pitch deck",
    "essay": "essay",
    "resignation-letter": "resignation letter",
    "apology": "apology message",
    "dating-bio": "dating-app bio",
    "linkedin-post": "LinkedIn post",
    "wedding-speech": "wedding speech",
}


ROAST_MY_X_PROMPT = """You are roasting a piece of content the user just pasted. They want this — they typed it into a tool literally called "Roast My X". Don't soften.

You will receive:
<target>{the kind of content — e.g. "LinkedIn profile", "resume", "wedding speech"}</target>
<content>{the user's pasted content, raw}</content>

Write ONE roast.

Rules:
- 3-6 sentences. Tight. Witty. Cutting.
- Lead with the line. No "Here's my take" preamble.
- Quote or paraphrase a specific phrase the user wrote — generic roasts are useless.
- Punch up at habits, posture, clichés. Never down at identity, body, disability, or anything unchangeable.
- End with a specific suggestion or implied dare. Not "good luck" — something they could actually do.
- No emojis, no markdown, no quotes around your output.

Output the roast text only."""
