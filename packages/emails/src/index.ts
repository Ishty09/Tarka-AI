export { default as WelcomeEmail } from "../templates/welcome";
export { renderEmail, type RenderedEmail } from "./render";

// As §14 templates land, re-export here. Workers consume via either:
//   - pre-rendered output (.out/ from `pnpm --filter @quarrel/emails export`)
//   - a small Node bridge that imports + renderEmail() per send.
//
// Order to migrate the 14 §14 templates:
//   1. welcome (DONE)
//   2. subscription_confirmed
//   3. subscription_canceled
//   4. payment_failed
//   5. wager_won / wager_lost
//   6. couples_invite
//   7. data_export_ready
//   8. account_deletion_grace_started
//   9. emergency_contact_notification
//  10. mirror_report_ready
//  11. eulogy_ready
//  12. moderation_rejection
//  13. beta_invite (workers/services/email.py already has Jinja version)
//  14. magic_link (uploaded directly into Supabase Auth dashboard)
