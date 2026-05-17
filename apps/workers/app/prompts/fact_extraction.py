"""Fact extraction prompt (CLAUDE.md §7.2 + §6.2 + §9.4.1).

Extracts durable facts from a user's chat turn. Output shape matches
packages/shared/src/schemas/llm/fact_extraction.ts — both must change
together.

Design choices in the prompt:
  - "0 to 5 facts per message" caps the noise from chatty turns.
  - Categories enumerate exactly the values §6.2 CHECK constraint accepts.
  - Third-person past-tense framing makes contradiction detection
    (Phase C step 16) easier — opposing claims are textually visible.
  - supersedes_fact_id is reserved for the supersession pass (not wired
    yet); for now the extractor always returns null.
"""

FACT_EXTRACTION_PROMPT = """You extract durable facts from a user's chat message for long-term memory.

Read the user message. Return a JSON object:
{
  "facts": [
    {
      "fact": "third-person past-tense statement",
      "category": "belief" | "goal" | "preference" | "identity" | "history" | "commitment" | "rationalization",
      "confidence": 0.0-1.0,
      "supersedes_fact_id": null
    }
  ]
}

Rules:
- Extract 0 to 5 facts per message. Empty array if nothing durable.
- Skip transient state ("I'm tired today", "I just woke up").
- Skip questions, hypotheticals, and counterfactuals.
- Use third-person past-tense: "User said X", "User believes Y", "User committed to Z".
- Categories:
  - "belief": a claim about the world the user holds
  - "goal": something the user wants to achieve
  - "preference": a taste or stylistic choice
  - "identity": demographic, role, profession, relationship
  - "history": something that happened in the user's life
  - "commitment": a specific promise or wager the user made
  - "rationalization": a justification or excuse pattern
- confidence: how certain you are the user actually meant this, 0.0 (guess) to 1.0 (explicit).
- supersedes_fact_id: always null. Supersession is handled separately.

Output ONLY the JSON object. No prose."""
