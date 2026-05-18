// Content table for /roast/[target] programmatic-SEO pages (§9.2.2).
//
// Keep target slugs aligned with packages/shared/constants ROAST_TARGETS
// and apps/workers/app/prompts/roast_my_x.py ROAST_TARGETS. All three move
// together when the set changes.
//
// Each entry drives:
//   - title / meta — SEO + OG
//   - subhead — landing copy
//   - input — placeholder + label
//   - examples — 2-3 sample roasts shown above the form
//   - faq — 2-3 FAQ items for schema.org FAQPage markup

import { ROAST_TARGETS, type RoastTarget } from "@quarrel/shared/constants";

export interface RoastTargetContent {
  slug: RoastTarget;
  /** Used in H1 ("Roast My {title}") and metadata. */
  title: string;
  /** One-line pitch under the H1. */
  subhead: string;
  /** Input field label. */
  input_label: string;
  /** Input placeholder text. */
  input_placeholder: string;
  /** Sample roasts shown above the form. */
  examples: string[];
  faq: { q: string; a: string }[];
}

const ENTRIES: Record<RoastTarget, RoastTargetContent> = {
  linkedin: {
    slug: "linkedin",
    title: "LinkedIn Profile",
    subhead: "Drop your LinkedIn URL or paste your headline + about. Get the corporate corpse out of your bio.",
    input_label: "Paste your LinkedIn profile (headline + about + a few experience bullets)",
    input_placeholder: "Senior Product Manager | Driving customer-obsessed innovation at scale | Passionate about leveraging AI to unlock...",
    examples: [
      "Your headline has four buzzwords and a verb. The verb is 'leveraging'. Pick one thing you actually did, not three identities you're trying on.",
      "'Passionate about driving impact' is what you write when you can't name the impact. Try a number, a customer name, anything specific.",
      "Six jobs in eight years and each one was a 'transformation'. Either you are the angel of corporate death or your bullet points need editing.",
    ],
    faq: [
      {
        q: "Will this rewrite my LinkedIn for me?",
        a: "No. It tells you what's wrong. The rewrite is yours — you'll know exactly what to fix.",
      },
      {
        q: "Is this anonymous?",
        a: "Yes. You paste content. We don't crawl your profile or attach this to your LinkedIn identity.",
      },
    ],
  },
  twitter: {
    slug: "twitter",
    title: "Twitter / X Bio",
    subhead: "Paste your bio or your last 10 tweets. Get a read on what you're actually telling the timeline.",
    input_label: "Paste your bio + a few recent tweets",
    input_placeholder: "🧠 Thinking about systems | ex-Google | Building the future of vibes | NYC ⚡ Lagos",
    examples: [
      "Your bio is six emojis and three cities. Pick the one you actually live in and a verb you actually do.",
      "Three months ago you were 'building the future of fintech.' Now it's 'thinking about systems.' Either you're sabbaticaling on Twitter or you don't know what you're building yet.",
      "You quote-tweet to add 'this' as commentary. Twelve times this week. That isn't a take, it's a like with extra steps.",
    ],
    faq: [
      {
        q: "What if my bio is short?",
        a: "Short bios get roasted faster. Three words can carry a lot of posture.",
      },
      {
        q: "Do you save my tweets?",
        a: "Only what you paste. We don't read your timeline.",
      },
    ],
  },
  resume: {
    slug: "resume",
    title: "Resume",
    subhead: "Paste the text version of your resume. Get the honest read your career coach won't give you.",
    input_label: "Paste your resume text",
    input_placeholder: "Lead Software Engineer · Acme Corp · 2021 – Present\n- Architected scalable solutions...",
    examples: [
      "'Architected scalable solutions' is what you write when you don't want to say what you built. Name the system. Name the load. Name the trade-off you actually made.",
      "Six bullets per job and every one of them starts with 'Led'. Either you've been a manager since 2014 or your IC work is hiding behind verbs.",
      "Your most recent job is two lines; your 2018 job is six. The arc on this page bends the wrong direction.",
    ],
    faq: [
      {
        q: "What format should I paste?",
        a: "Plain text. Bullets are fine — keep the structure, drop the PDF formatting.",
      },
      {
        q: "Do you keep my resume?",
        a: "It's saved to your account so you can re-read the critique later. You can delete it any time.",
      },
    ],
  },
  "github-pr": {
    slug: "github-pr",
    title: "GitHub Pull Request",
    subhead: "Paste the PR description or diff summary. Get the review your senior engineer is too tired to give.",
    input_label: "Paste your PR title + description (and a short diff summary if relevant)",
    input_placeholder: "feat: refactor user auth flow\n\nThis PR refactors the auth flow to be more...",
    examples: [
      "Your PR description is one paragraph that says 'refactor' four times and explains nothing. Name the bug you fixed, the constraint that changed, or the cost you paid.",
      "1,400 lines, one commit, message reads 'wip'. Either you wrote this in one sitting and your reviewer will hate you, or you squashed history and your blame is now useless.",
      "Three tests touched, one of them deleted. The deleted one was probably the only test that actually exercised this path. You sure?",
    ],
    faq: [
      {
        q: "Should I paste the diff?",
        a: "A summary helps. Full diffs over a few hundred lines get truncated.",
      },
      {
        q: "Will this catch bugs?",
        a: "Sometimes. It's not a security review — it's the read your team would do if they cared enough.",
      },
    ],
  },
  "dating-profile": {
    slug: "dating-profile",
    title: "Dating Profile",
    subhead: "Paste your prompts, your bio, your one-liner. Get the read your friends are too polite to share.",
    input_label: "Paste your dating-app bio + a couple of prompts",
    input_placeholder: "I'm a foodie who loves to travel and is looking for someone to laugh with...",
    examples: [
      "'Foodie' and 'love to travel' is the dating-profile equivalent of being a registered voter. Pick one cuisine, one country, one actual thing.",
      "Three of your prompts mention coffee. We get it. Tell me something you'd argue about.",
      "Your bio ends with 'must love dogs.' You don't have a dog. Decide who you are before you decide who your partner is.",
    ],
    faq: [
      {
        q: "Will it rewrite my profile?",
        a: "It tells you what's hiding behind your prompts. The rewrite is the fun part — that's yours.",
      },
      {
        q: "Can I paste prompts from Hinge / Bumble / etc.?",
        a: "Yes. Paste the prompt + your answer for each one you want roasted.",
      },
    ],
  },
  "cover-letter": {
    slug: "cover-letter",
    title: "Cover Letter",
    subhead: "Paste the cover letter you're about to send. Get the read before the recruiter does.",
    input_label: "Paste your cover letter",
    input_placeholder: "Dear Hiring Manager,\n\nI am writing to express my interest in...",
    examples: [
      "'I am writing to express my interest' is the opener every cover letter has. You wasted your first line. Cut it; open on what you'd do in the first 90 days.",
      "Three paragraphs about you, half a sentence about them. Flip it. They don't care about your 'passion for innovation' — they care whether you understand their problem.",
      "You list five skills. None of them appear in the job posting. You're writing this for yourself, not them.",
    ],
    faq: [
      {
        q: "Should I paste the job description too?",
        a: "Yes if you want target-aware feedback. Otherwise we critique the letter on its own.",
      },
      {
        q: "Will it write a better one?",
        a: "It diagnoses. The rewrite is yours — you'll know exactly which parts to cut.",
      },
    ],
  },
  code: {
    slug: "code",
    title: "Code",
    subhead: "Paste the function you're about to ship. Get the senior-engineer read in 30 seconds.",
    input_label: "Paste a code snippet (any language)",
    input_placeholder: "function processUser(u) {\n  if (u.role === 'admin') {\n    // ...\n  }\n}",
    examples: [
      "Five booleans on the function signature. You're not writing code, you're writing a state machine. Pull it out into one.",
      "The error path returns null. The success path returns an object. Your caller has to type-check every result. They won't, and you know it.",
      "You named the variable 'data'. The variable is 'an array of authenticated users with their last login'. Name it that.",
    ],
    faq: [
      {
        q: "Which languages?",
        a: "Any. The critique focuses on structure and intent — language-specific gotchas might leak in but aren't the focus.",
      },
      {
        q: "Does this replace code review?",
        a: "No. It catches what a tired colleague would let slide.",
      },
    ],
  },
  instagram: {
    slug: "instagram",
    title: "Instagram Bio",
    subhead: "Paste your bio + a few captions. Get the read on what you're performing.",
    input_label: "Paste your bio + a few recent captions",
    input_placeholder: "📍 NYC | 🎨 Creator | ✨ Living my best life | Currently obsessed with...",
    examples: [
      "Your bio is three emojis and a verb in -ing form. You don't have a hobby, you have a posture. Pick something you actually finish.",
      "Every caption ends with 'grateful'. The word has stopped meaning anything in your feed. Try saying what you're actually feeling.",
      "Six selfies in a row, each one a 'casual candid'. Your audience has been onto you since post three. Lean into the staging or stop pretending.",
    ],
    faq: [
      {
        q: "Will this make me more interesting?",
        a: "It tells you which parts of you aren't landing. The interesting is your job.",
      },
      {
        q: "Should I include captions?",
        a: "Yes — that's where the real read is.",
      },
    ],
  },
  portfolio: {
    slug: "portfolio",
    title: "Portfolio Site",
    subhead: "Paste your homepage copy + a couple of project descriptions. Get the read your designer friend won't give.",
    input_label: "Paste your portfolio homepage text + 1-2 project blurbs",
    input_placeholder: "Hi, I'm Alex. I design products that solve real problems for real people.\n\nProject: Redesigned the onboarding flow for a fintech startup...",
    examples: [
      "'Designs products that solve real problems for real people' is what you write when you can't think of one. Real problem. Real person. Use them.",
      "Three case studies, all of them 'increased conversion by 30%'. Either you're a metrics wizard or you're using the same template. The reader can tell.",
      "Your homepage has zero work above the fold. Twenty seconds of scroll before I see anything you've made. Move a thumbnail up.",
    ],
    faq: [
      {
        q: "Should I link a project?",
        a: "Paste a project blurb — links work but text is what we read.",
      },
      {
        q: "Is this for designers only?",
        a: "Designers, devs, writers, anyone with a portfolio site.",
      },
    ],
  },
  "startup-idea": {
    slug: "startup-idea",
    title: "Startup Idea",
    subhead: "Pitch the idea in a paragraph. Get the read before your seed pitch.",
    input_label: "Pitch your startup idea in a few sentences",
    input_placeholder: "We're building an AI-powered platform for...",
    examples: [
      "'AI-powered platform for X' is the same sentence with X swapped. Replace 'AI-powered' with what the user actually does in your app and re-read it.",
      "You haven't named a customer. You've named a category. There's a difference, and your fundraising will reflect it.",
      "Your moat is 'better UX'. Better UX is a feature. Pick a wedge that doesn't dissolve the moment a faster team copies you.",
    ],
    faq: [
      {
        q: "Is this for fundraising?",
        a: "It's for the pitch before the pitch — the read your co-founder is too polite to give.",
      },
      {
        q: "What if my idea is early?",
        a: "Earlier means more pressure on the wedge. The critique pushes on that.",
      },
    ],
  },
  "email-draft": {
    slug: "email-draft",
    title: "Email Draft",
    subhead: "Paste the email you're about to send. Get the read before you hit send.",
    input_label: "Paste your email draft",
    input_placeholder: "Hi Sarah,\n\nI hope you're doing well. I wanted to follow up on...",
    examples: [
      "Your opener is two sentences of weather. Cut both. The reader skims to paragraph two anyway — promote it.",
      "You said 'just' three times. 'Just wanted to', 'just checking in', 'just a quick note'. Every 'just' is an apology for emailing. Drop them.",
      "The ask is in the last sentence. The reader will miss it on first read. Move it up, bold it if you have to, or rewrite the email around it.",
    ],
    faq: [
      {
        q: "Does this work for cold emails?",
        a: "Especially cold emails — those are where you lose most readers in the first two lines.",
      },
      {
        q: "Will it rewrite the email?",
        a: "It tells you what's wrong. You'll know exactly which lines to delete.",
      },
    ],
  },
  tweet: {
    slug: "tweet",
    title: "Single Tweet",
    subhead: "Paste the one tweet. Get the read before you post.",
    input_label: "Paste a single tweet (280 chars or less)",
    input_placeholder: "Hot take: most people don't actually know what...",
    examples: [
      "It's a hot take that everyone has had. Two more years and it'll be a Medium article.",
      "You hedged with 'most' and 'often' so you can't be wrong. You also can't be interesting. Pick a sharp claim.",
      "Length 278. Worth posting? Compress to 80. If it doesn't survive the cut, the tweet wasn't ready.",
    ],
    faq: [
      {
        q: "Does this score virality?",
        a: "No — virality isn't a thing you score. It catches what's vague, hedged, or already-said.",
      },
      {
        q: "Is one tweet enough?",
        a: "One is the whole point. If you're roasting a thread, use 'Roast My Twitter'.",
      },
    ],
  },
  "business-name": {
    slug: "business-name",
    title: "Business Name & Tagline",
    subhead: "Paste your name + tagline before you spend $400 on a logo.",
    input_label: "Paste your business name + tagline",
    input_placeholder: "Lumino Labs — Illuminating the future of work",
    examples: [
      "'Lumino Labs — Illuminating the future of work' is three startups in a trench coat. Either tighten the metaphor or drop it.",
      "Your name has two -ly suffixes and a missing vowel. Trendy in 2014. The next decade is going the other way.",
      "Tagline doesn't say what you do, what you sell, or who you serve. It says how you feel. Don't make customers do the work.",
    ],
    faq: [
      {
        q: "Will it suggest names?",
        a: "No — it tells you why the one you picked might not work.",
      },
      {
        q: "What about trademark / SEO?",
        a: "Not in scope. Use a proper trademark search before you commit.",
      },
    ],
  },
  "pitch-deck": {
    slug: "pitch-deck",
    title: "Pitch Deck",
    subhead: "Paste the text from your deck. Get the read your lead investor will give in ten seconds per slide.",
    input_label: "Paste your deck text (slide by slide, or as one long block)",
    input_placeholder: "Slide 1: Lumino Labs — Illuminating the future of work\nSlide 2: The Problem: Companies waste...",
    examples: [
      "Slide 4 is a TAM/SAM/SOM chart that says $50B. The number doesn't matter — the methodology behind it does, and yours is missing.",
      "Your traction slide is a hockey stick over four months. From 2 customers to 12. Investors can count.",
      "The 'why now' slide doesn't say why now. It says 'AI is transforming everything'. That answers 'why ever' — fix it.",
    ],
    faq: [
      {
        q: "How long should the paste be?",
        a: "Slide-by-slide text is ideal. We don't read decks visually, just the words.",
      },
      {
        q: "Will it suggest slide order?",
        a: "It'll tell you which slides are doing the wrong job.",
      },
    ],
  },
  essay: {
    slug: "essay",
    title: "Essay",
    subhead: "Paste your essay before you publish. Get the read your editor would give.",
    input_label: "Paste your essay (long-form, up to ~6k chars)",
    input_placeholder: "Why I think the future of X is...",
    examples: [
      "The thesis arrives in paragraph four. By then half your readers are gone. Move it up.",
      "You quoted four other people and named zero of your own examples. The essay is a meta-take on a take. Use one specific story from your own life.",
      "Your closing paragraph is a softening of everything you just argued. You earned the claim — let it stand.",
    ],
    faq: [
      {
        q: "What length works best?",
        a: "1-3k words pastes well. Longer gets truncated.",
      },
      {
        q: "What about style and voice?",
        a: "We focus on argument structure, not prose style. A grammar tool catches the rest.",
      },
    ],
  },
  "resignation-letter": {
    slug: "resignation-letter",
    title: "Resignation Letter",
    subhead: "Paste it before you click send. Get the read before HR does.",
    input_label: "Paste your resignation letter",
    input_placeholder: "Dear [Manager],\n\nIt is with mixed emotions that I write to inform you...",
    examples: [
      "Three paragraphs of gratitude, one line of resignation, no end date. The HR reader will scan for the date and miss it. Lead with the line.",
      "'Mixed emotions' is the standard opener and tells the reader you've decided to soften the truth. Either own the leaving or take the softness out.",
      "You offered four weeks and your contract says two. You don't owe a counter-offer. Stick with two unless you want to.",
    ],
    faq: [
      {
        q: "Is this legal advice?",
        a: "No. Check your contract and local labour law.",
      },
      {
        q: "Will this make my exit easier?",
        a: "It makes your letter clearer. The exit itself is people work.",
      },
    ],
  },
  apology: {
    slug: "apology",
    title: "Apology",
    subhead: "Paste the apology you're about to send. Get the read on whether it apologises for anything.",
    input_label: "Paste your apology message",
    input_placeholder: "I'm really sorry if you felt that what I said was hurtful...",
    examples: [
      "'I'm sorry if you felt' is not an apology. It's a complaint about how they felt. Replace it with 'I'm sorry I did X'.",
      "You named your intent three times and what you did once. The other person doesn't need your intent — they need acknowledgement of impact.",
      "The last line asks them for forgiveness. That's a follow-up ask. Apologise without it first; let them decide on their timeline.",
    ],
    faq: [
      {
        q: "Will this fix my relationship?",
        a: "No. It will make your apology actually be one.",
      },
      {
        q: "What if the situation is complex?",
        a: "Most apologies are simpler than the person writing them thinks.",
      },
    ],
  },
  "dating-bio": {
    slug: "dating-bio",
    title: "Dating Bio",
    subhead: "Paste only the bio (no prompts). Get the cleanest possible read.",
    input_label: "Paste your dating bio (short — no prompts)",
    input_placeholder: "Loves hiking, dogs, and pretending to read more than I do.",
    examples: [
      "'Pretending to read more than I do' is a hedge against being asked what you've read. Pick one book.",
      "Three nouns, no verbs. A bio is what you do, not what you collect.",
      "You included your height. Nobody who liked your photos cares; everyone who didn't still won't.",
    ],
    faq: [
      {
        q: "What's the difference from 'Roast My Dating Profile'?",
        a: "Bio is just the one-liner. Profile is bio + prompts + photos context.",
      },
      {
        q: "Should I include my age?",
        a: "Up to you. Most apps show it separately — including it in the bio is filler.",
      },
    ],
  },
  "linkedin-post": {
    slug: "linkedin-post",
    title: "LinkedIn Post",
    subhead: "Paste a single LinkedIn post. Get the read before you push the line-break button 12 times.",
    input_label: "Paste a single LinkedIn post",
    input_placeholder: "I want to share something that happened last week.\n\nIt started when...",
    examples: [
      "Eight one-sentence paragraphs. You've trained yourself to write for the algorithm, not the reader. Compress.",
      "The setup is 'a junior employee asked me a question'. The reveal is a leadership lesson. We saw the turn coming from line two.",
      "You ended with three reflection bullets. They're three rewrites of the same point. Pick one.",
    ],
    faq: [
      {
        q: "Does this score engagement?",
        a: "No. It tells you when the post is engagement-bait instead of a real take.",
      },
      {
        q: "What about a carousel?",
        a: "Paste the text of each slide as paragraphs.",
      },
    ],
  },
  "wedding-speech": {
    slug: "wedding-speech",
    title: "Wedding Speech",
    subhead: "Paste your draft before the rehearsal. Get the read your best friend would give.",
    input_label: "Paste your wedding-speech draft",
    input_placeholder: "When [Name] first told me they were getting married, I...",
    examples: [
      "Two minutes of inside jokes. The bride's grandmother will not understand. Cut one.",
      "Your big moment is a story where you're the hero, not them. Flip it — the couple should be the centre of every story you tell.",
      "You ended with 'so let's raise a glass to'. Generic toast wording. Land somewhere specific they'll remember.",
    ],
    faq: [
      {
        q: "How long should a wedding speech be?",
        a: "3-5 minutes. We don't time the paste, but we'll point out if your draft is going to overrun.",
      },
      {
        q: "Will it tell me which stories to cut?",
        a: "Yes — and which one to keep.",
      },
    ],
  },
};

export function getRoastTargetContent(slug: string): RoastTargetContent | null {
  if (!isRoastTarget(slug)) return null;
  return ENTRIES[slug];
}

export function isRoastTarget(slug: string): slug is RoastTarget {
  return (ROAST_TARGETS as readonly string[]).includes(slug);
}

export function allRoastTargets(): RoastTargetContent[] {
  return ROAST_TARGETS.map((s) => ENTRIES[s]);
}
