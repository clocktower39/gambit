// Server-side proxy: has the seller closed this chat? The buyer UI polls this to hard-lock its input
// once the seller walks away. Routes through Next so nginx needs no new rule (browser hits Next only).
import { NextRequest, NextResponse } from "next/server";

const AGUI_URL = process.env.AGUI_URL ?? "http://localhost:8000/";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const runId = req.nextUrl.searchParams.get("run_id") ?? "";
  if (!runId) return NextResponse.json({ closed: false });
  try {
    const res = await fetch(new URL(`chat-status?run_id=${encodeURIComponent(runId)}`, AGUI_URL), {
      cache: "no-store",
    });
    if (!res.ok) return NextResponse.json({ closed: false });
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ closed: false });
  }
}
