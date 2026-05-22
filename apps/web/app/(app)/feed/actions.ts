"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";

// Roast feed voting (§9.2.5). Three-state toggle:
//   - no current vote, click up   → store vote=1, post.upvotes += 1
//   - vote=1, click up again       → delete vote, post.upvotes -= 1
//   - vote=-1, click up            → switch to 1, downvotes -= 1, upvotes += 1
//
// The post counters in roast_feed_posts are denormalised so we don't have
// to aggregate roast_feed_votes on every read. Race: two parallel votes
// from the same user could double-count; acceptable for launch traffic.
// §27 step 51 quota job will install a Postgres function that does this
// in one statement.

const voteSchema = z.object({
  post_id: z.string().uuid(),
  vote: z.union([z.literal(1), z.literal(-1)]),
});

export async function castVote(formData: FormData): Promise<void> {
  const parsed = voteSchema.safeParse({
    post_id: formData.get("post_id"),
    vote: Number(formData.get("vote")),
  });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { post_id, vote } = parsed.data;

  const { data: existing } = await supabase
    .from("roast_feed_votes")
    .select("vote")
    .eq("post_id", post_id)
    .eq("user_id", user.id)
    .maybeSingle();

  const { data: postData } = await supabase
    .from("roast_feed_posts")
    .select("upvotes, downvotes")
    .eq("id", post_id)
    .maybeSingle();
  if (!postData) return;
  let upvotes = postData.upvotes ?? 0;
  let downvotes = postData.downvotes ?? 0;

  if (!existing) {
    // First vote.
    await supabase.from("roast_feed_votes").insert({
      post_id,
      user_id: user.id,
      vote,
    });
    if (vote === 1) upvotes += 1;
    else downvotes += 1;
  } else if (existing.vote === vote) {
    // Toggling off — remove the row.
    await supabase
      .from("roast_feed_votes")
      .delete()
      .eq("post_id", post_id)
      .eq("user_id", user.id);
    if (vote === 1) upvotes = Math.max(0, upvotes - 1);
    else downvotes = Math.max(0, downvotes - 1);
  } else {
    // Switching direction.
    await supabase
      .from("roast_feed_votes")
      .update({ vote })
      .eq("post_id", post_id)
      .eq("user_id", user.id);
    if (vote === 1) {
      upvotes += 1;
      downvotes = Math.max(0, downvotes - 1);
    } else {
      downvotes += 1;
      upvotes = Math.max(0, upvotes - 1);
    }
  }

  await supabase
    .from("roast_feed_posts")
    .update({ upvotes, downvotes })
    .eq("id", post_id);

  if (vote === 1 && (!existing || existing.vote !== 1)) {
    await trackServer("roast_feed_post_upvoted", {
      user_id: hashUserId(user.id),
      post_id,
    });
  }
  revalidatePath("/feed");
}
