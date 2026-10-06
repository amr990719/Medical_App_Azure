// Azure Static Web Apps configuration (public/staticwebapp.config.json, copied to dist/ by Vite).
// The SPA and Django share one origin through the linked backend (PROMPT.md §4.1), so the
// fallback must never swallow /api, and the headers protect the SPA document itself.
import indexHtml from "../index.html?raw";
import config from "../public/staticwebapp.config.json";

type Route = { route: string; headers?: Record<string, string>; allowedRoles?: string[] };

const headers = config.globalHeaders as Record<string, string>;
const routes = config.routes as Route[];

function cspDirective(name: string): string[] {
  const csp = headers["Content-Security-Policy"] ?? "";
  const directive = csp
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name} `) || part === name);
  return directive ? directive.split(/\s+/).slice(1) : [];
}

describe("staticwebapp.config.json", () => {
  it("rewrites client-side routes to index.html but never /api or built assets", () => {
    expect(config.navigationFallback.rewrite).toBe("/index.html");
    expect(config.navigationFallback.exclude).toEqual(
      expect.arrayContaining(["/api/*", "/assets/*"]),
    );
  });

  it("leaves authorization of /api to Django (no Static Web Apps roles)", () => {
    for (const route of routes) {
      expect(route.allowedRoles).toBeUndefined();
    }
  });

  it("sends a strict CSP without inline or eval script", () => {
    expect(cspDirective("default-src")).toEqual(["'self'"]);
    expect(cspDirective("script-src")).toEqual(["'self'"]);
    expect(cspDirective("object-src")).toEqual(["'none'"]);
    expect(cspDirective("frame-ancestors")).toEqual(["'none'"]);
    expect(cspDirective("base-uri")).toEqual(["'self'"]);
    expect(cspDirective("form-action")).toEqual(["'self'"]);
    expect(cspDirective("connect-src")).toEqual(["'self'"]);
    expect(headers["Content-Security-Policy"]).not.toMatch(/unsafe-(inline|eval)/);
  });

  it("allows every external host index.html loads (Cairo from Google Fonts, Q-T10)", () => {
    const stylesheetHosts = [...indexHtml.matchAll(/rel="stylesheet"\s+href="(https:\/\/[^/"]+)/g)].map(
      (match) => match[1],
    );
    expect(stylesheetHosts).toContain("https://fonts.googleapis.com");
    for (const host of stylesheetHosts) {
      expect(cspDirective("style-src")).toContain(host);
    }
    expect(cspDirective("font-src")).toContain("https://fonts.gstatic.com");
  });

  it("lets document thumbnails and the admin PDF viewer load from the same origin only", () => {
    expect(cspDirective("img-src")).toEqual(expect.arrayContaining(["'self'", "data:", "blob:"]));
    expect(cspDirective("frame-src")).toEqual(["'self'"]);
  });

  it("sets the other security headers", () => {
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Referrer-Policy"]).toBe("same-origin");
    expect(headers["Cross-Origin-Opener-Policy"]).toBe("same-origin");
    expect(headers["Strict-Transport-Security"]).toMatch(/max-age=31536000/);
    expect(headers["Permissions-Policy"]).toMatch(/geolocation=\(\)/);
  });

  it("never caches index.html and caches hashed assets for a year", () => {
    const indexRoute = routes.find((route) => route.route === "/index.html");
    const assetRoute = routes.find((route) => route.route === "/assets/*");
    expect(indexRoute?.headers?.["Cache-Control"]).toBe("no-cache");
    expect(assetRoute?.headers?.["Cache-Control"]).toBe("public, max-age=31536000, immutable");
  });
});
