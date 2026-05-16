// CLAUDE.md §7.4 persona overlay. Two ways to use this module:
//
//   1. System personas already store their fully-rendered overlay in
//      personas.system_prompt (see supabase/seed.sql). For those, just inline
//      the column value between the anti-sycophant base prompt and the user
//      facts block.
//
//   2. User-created personas (§10.2) may store loosely-typed fields and let us
//      render the overlay on demand. Use `buildPersonaOverlay` for that path.

export interface PersonaOverlayFields {
  slug: string;
  name: string;
  locale: string;
  cultural_register: string;
  voice_description: string;
  speech_patterns: string;
  cultural_references: string;
  catchphrases: string;
  forbidden: string;
  character_anchors: string;
}

export function buildPersonaOverlay(p: PersonaOverlayFields): string {
  return `<persona>
Slug: ${p.slug}
Name: ${p.name}
Locale: ${p.locale}
Cultural register: ${p.cultural_register}
Voice description: ${p.voice_description}
Speech patterns: ${p.speech_patterns}
Cultural references to use: ${p.cultural_references}
Catchphrases (use sparingly): ${p.catchphrases}
Forbidden topics: ${p.forbidden}
Stays in character even when: ${p.character_anchors}
</persona>`;
}

// The literal §7.4 template — kept here for tooling that wants to template-fill
// from a different source than buildPersonaOverlay.
export const PERSONA_OVERLAY_TEMPLATE = `<persona>
Slug: {slug}
Name: {name}
Locale: {locale}
Cultural register: {cultural_register}
Voice description: {voice_description}
Speech patterns: {speech_patterns}
Cultural references to use: {cultural_references}
Catchphrases (use sparingly): {catchphrases}
Forbidden topics: {forbidden}
Stays in character even when: {character_anchors}
</persona>`;
