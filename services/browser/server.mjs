import http from "node:http";
import { chromium } from "playwright-core";

const port = Number(process.env.PORT || "3001");
const serviceToken = process.env.BROWSER_SERVICE_TOKEN || "";
const proxyToken = process.env.BROWSER_PROXY_TOKEN || "";
const proxyServer = process.env.BROWSER_PROXY_URL || "http://browser-proxy:8080";
const maxBodyBytes = 64 * 1024;
const maxTextChars = Number(process.env.BROWSER_MAX_TEXT_CHARS || "30000");
const maxHtmlChars = Number(process.env.BROWSER_MAX_HTML_CHARS || "2000000");
const maxRequests = Number(process.env.BROWSER_MAX_REQUESTS || "100");
const maxTransferBytes = Number(process.env.BROWSER_MAX_TRANSFER_BYTES || String(25 * 1024 * 1024));
const timeoutMs = Number(process.env.BROWSER_TIMEOUT_MS || "20000");

let browserPromise;

function browser() {
  if (!browserPromise) {
    browserPromise = chromium.launch({
      headless: true,
      proxy: {
        server: proxyServer,
        username: "browser",
        password: proxyToken,
      },
      args: [
        "--disable-background-networking",
        "--disable-breakpad",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-features=MediaRouter,WebRtcHideLocalIpsWithMdns",
        "--disable-sync",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-first-run",
      ],
    }).catch((error) => {
      browserPromise = undefined;
      throw error;
    });
  }
  return browserPromise;
}

function hostnameMatches(hostname, rule) {
  const host = hostname.toLowerCase().replace(/\.$/, "");
  const domain = String(rule || "").toLowerCase().replace(/^\./, "").replace(/\.$/, "");
  return Boolean(domain) && (host === domain || host.endsWith(`.${domain}`));
}

function validateUrl(value, blockedDomains) {
  const url = new URL(String(value || ""));
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("Only public HTTP and HTTPS pages can be browsed.");
  }
  if (url.username || url.password) {
    throw new Error("Browser URLs cannot include credentials.");
  }
  const defaultPort = url.protocol === "https:" ? "443" : "80";
  if (url.port && url.port !== defaultPort) {
    throw new Error("Browser requests are limited to standard web ports.");
  }
  if (blockedDomains.some((rule) => hostnameMatches(url.hostname, rule))) {
    throw new Error("The destination is blocked by the research policy.");
  }
  return url;
}

async function browse(payload) {
  const blockedDomains = Array.isArray(payload.blocked_domains)
    ? payload.blocked_domains.slice(0, 100)
    : [];
  const requested = validateUrl(payload.url, blockedDomains);
  const instance = await browser();
  const context = await instance.newContext({
    acceptDownloads: false,
    serviceWorkers: "block",
    javaScriptEnabled: true,
    ignoreHTTPSErrors: false,
  });
  const page = await context.newPage();
  const session = await context.newCDPSession(page);
  await session.send("Network.enable");
  let requestCount = 0;
  let transferredBytes = 0;
  let transferLimitExceeded = false;
  session.on("Network.dataReceived", ({ dataLength }) => {
    transferredBytes += Number(dataLength || 0);
    if (transferredBytes > maxTransferBytes && !transferLimitExceeded) {
      transferLimitExceeded = true;
      void page.close();
    }
  });
  await page.route("**/*", async (route) => {
    try {
      const request = route.request();
      requestCount += 1;
      if (requestCount > maxRequests) {
        await route.abort("blockedbyclient");
        return;
      }
      validateUrl(request.url(), blockedDomains);
      if (["image", "media", "font"].includes(request.resourceType())) {
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    } catch {
      await route.abort("blockedbyclient");
    }
  });
  page.on("download", (download) => download.cancel());
  try {
    let response;
    try {
      response = await page.goto(requested.href, {
        waitUntil: "domcontentloaded",
        timeout: timeoutMs,
      });
    } catch (error) {
      if (transferLimitExceeded) {
        throw new Error("Rendered page exceeded the configured network transfer limit.");
      }
      throw error;
    }
    await page.waitForTimeout(Math.min(1000, timeoutMs / 4));
    if (transferLimitExceeded) {
      throw new Error("Rendered page exceeded the configured network transfer limit.");
    }
    const finalUrl = page.url();
    validateUrl(finalUrl, blockedDomains);
    const htmlLength = await page.evaluate(() => document.documentElement.outerHTML.length);
    if (htmlLength > maxHtmlChars) {
      throw new Error("Rendered page exceeded the configured DOM size limit.");
    }
    const result = await page.evaluate(({ maxTextChars }) => {
      const text = (document.body?.innerText || "").trim();
      const meta = (names) => {
        for (const name of names) {
          const node = document.querySelector(
            `meta[name="${name}"], meta[property="${name}"]`,
          );
          const content = node?.getAttribute("content")?.trim();
          if (content) return content;
        }
        return "";
      };
      return {
        title: document.title.slice(0, 500),
        description: meta(["description", "og:description"]).slice(0, 1000),
        publisher: meta(["og:site_name", "article:publisher", "author"]).slice(0, 255),
        published_at: meta([
          "article:published_time",
          "og:published_time",
          "date",
          "datePublished",
        ]).slice(0, 100),
        canonical_url:
          document.querySelector('link[rel~="canonical"]')?.href || "",
        language: document.documentElement.lang.slice(0, 30),
        text: text.slice(0, maxTextChars),
        truncated: text.length > maxTextChars,
        headings: [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
          .slice(0, 30)
          .map((node) => ({
            level: Number(node.tagName.slice(1)),
            text: (node.textContent || "").trim().slice(0, 500),
          })),
        links: [...document.querySelectorAll("a[href]")]
          .slice(0, 50)
          .map((node) => ({
            text: (node.textContent || "").trim().slice(0, 300),
            url: node.href,
          })),
      };
    }, { maxTextChars });
    return {
      requested_url: requested.href,
      url: finalUrl,
      status_code: response?.status() || 200,
      content_type: "text/html",
      accessed_at: new Date().toISOString(),
      request_count: requestCount,
      transferred_bytes: transferredBytes,
      ...result,
    };
  } finally {
    await context.close();
  }
}

const server = http.createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(serviceToken && proxyToken ? 200 : 503, {
      "Content-Type": "application/json",
    });
    response.end(JSON.stringify({ status: serviceToken && proxyToken ? "ok" : "misconfigured" }));
    return;
  }
  if (
    request.method !== "POST" ||
    request.url !== "/browse" ||
    request.headers.authorization !== `Bearer ${serviceToken}`
  ) {
    response.writeHead(404).end();
    return;
  }
  let body = Buffer.alloc(0);
  request.on("data", (chunk) => {
    body = Buffer.concat([body, chunk]);
    if (body.length > maxBodyBytes) request.destroy();
  });
  request.on("end", async () => {
    try {
      const payload = JSON.parse(body.toString("utf8"));
      const result = await browse(payload);
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(result));
    } catch (error) {
      response.writeHead(400, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ error: String(error?.message || error) }));
    }
  });
});

server.listen(port, "0.0.0.0");

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, async () => {
    const instance = await browserPromise?.catch(() => undefined);
    await instance?.close();
    server.close(() => process.exit(0));
  });
}
