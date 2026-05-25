// Shared render helper. Workers call this to turn JSX templates into
// the HTML + plaintext pair that Resend expects.
//
// Usage from apps/workers email.py (over a bun/node bridge or via
// pre-rendered output): `pnpm --filter @quarrel/emails export` writes
// every template under .out/ as plain HTML + a JSON map of variables.

import { render } from "@react-email/render";
import type { ReactElement } from "react";

export interface RenderedEmail {
  html: string;
  text: string;
}

export async function renderEmail(jsx: ReactElement): Promise<RenderedEmail> {
  return {
    html: await render(jsx),
    text: await render(jsx, { plainText: true }),
  };
}
