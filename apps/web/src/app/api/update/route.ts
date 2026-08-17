import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const apiUrl = process.env.SIRIUS_INTERNAL_API_URL ?? "http://localhost:8000/api/v1";
  const apiKey = process.env.SIRIUS_API_KEY;
  const body = await request.text();
  const response = await fetch(`${apiUrl}/update-jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {})
    },
    body,
    cache: "no-store"
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" }
  });
}
