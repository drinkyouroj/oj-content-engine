import { NextRequest, NextResponse } from "next/server";

const TOKEN_COOKIE = "dashboard_token";

async function sha256(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  if (!pathname.startsWith("/dashboard") && !pathname.startsWith("/api")) {
    return NextResponse.next();
  }

  const token = process.env.DASHBOARD_TOKEN;
  if (!token) {
    return new NextResponse("DASHBOARD_TOKEN not configured", { status: 500 });
  }

  const expectedHash = await sha256(token);

  // Check query param token (sets cookie)
  const queryToken = searchParams.get("token");
  if (queryToken) {
    const providedHash = await sha256(queryToken);
    if (providedHash === expectedHash) {
      const url = request.nextUrl.clone();
      url.searchParams.delete("token");
      const response = NextResponse.redirect(url);
      response.cookies.set(TOKEN_COOKIE, expectedHash, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        maxAge: 30 * 24 * 60 * 60,
        path: "/",
      });
      return response;
    }
  }

  // Check header token
  const headerToken = request.headers.get("x-dashboard-token");
  if (headerToken) {
    const headerHash = await sha256(headerToken);
    if (headerHash === expectedHash) {
      return NextResponse.next();
    }
  }

  // Check cookie
  const cookie = request.cookies.get(TOKEN_COOKIE)?.value;
  if (cookie && cookie === expectedHash) {
    return NextResponse.next();
  }

  return new NextResponse("Unauthorized", { status: 401 });
}

export const config = {
  matcher: ["/dashboard/:path*", "/api/:path*"],
};
