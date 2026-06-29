/**
 * Next.js proxy — DevAssist AI (no-auth edition).
 *
 * Next.js 16+ renamed `middleware.ts` → `proxy.ts`.  The exported function
 * must also be named `proxy` (or be a default export); the old `middleware`
 * named-export is no longer recognised by the framework.
 *
 * This is a self-hosted tool meant to be locked behind a firewall or VPN.
 * No authentication middleware is needed. All routes are public to anyone
 * who can reach the host.
 *
 * The matcher below excludes Next.js internals and static assets so the
 * proxy doesn't fire on every image/font request unnecessarily.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function proxy(_request: NextRequest) {
  // Passthrough — no auth enforcement.
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
  ],
};
