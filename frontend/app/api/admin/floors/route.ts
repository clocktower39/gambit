// Server-side proxy for the admin floors endpoint. Forwards the browser's Basic-Auth header to the
// Python backend (gambit/agui.py → GET /admin/floors), which validates it against ADMIN_USERS in .env.
// Routing through Next (server-side) keeps the secret floor data off any path the browser hits
// unauthenticated, and means nginx needs no new rule (the browser only ever talks to Next here).
import { NextRequest, NextResponse } from "next/server";

const AGUI_URL = process.env.AGUI_URL ?? "http://localhost:8000/";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";
  let res: Response;
  try {
    res = await fetch(new URL("admin/floors", AGUI_URL), {
      headers: auth ? { authorization: auth } : {},
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
