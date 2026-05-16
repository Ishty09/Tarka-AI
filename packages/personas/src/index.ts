// 25 launch personas across 16 locales (en, bn, hi, es, pt, it, ru, ar, ko, ja,
// de, fr, zh, id, vi, he). See CLAUDE.md §10.
// Locale subfolders (en/, bn/, hi/, ...) will be populated in later phases.
export type PersonaCategory =
  | "argue"
  | "roast"
  | "mediate"
  | "council"
  | "productivity"
  | "cultural";

export type VoiceProvider = "chatterbox" | "elevenlabs" | "openai";

export interface Persona {
  slug: string;
  name: string;
  locale: string;
  country: string;
  cultural_tag: string;
  category: PersonaCategory;
  description: string;
  voice_provider: VoiceProvider;
  voice_id: string;
  system_prompt: string;
}
