#!/usr/bin/env node
/**
 * Fetch Stooq daily EOD CSVs through a real browser session (ADR 0007 follow-up).
 *
 * Stooq gates plain HTTP clients behind a JavaScript proof-of-work challenge,
 * so `bot refresh --prices` cannot reach /q/d/l/ directly. This recipe drives
 * the agent-browser Chrome session over CDP: the browser solves the challenge
 * once when a real quote page loads, and every subsequent same-origin fetch()
 * issued *inside that page* carries the trusted cookies — returning plain CSV.
 *
 * Prerequisites (one-time, before running):
 *   agent-browser open "https://stooq.com/q/d/?s=aapl.us"   # solves the challenge
 *   agent-browser wait --load networkidle
 *
 * Usage:
 *   node scripts/stooq_browser_fetch.mjs AAPL MSFT BRK.B          # explicit tickers
 *   node scripts/stooq_browser_fetch.mjs --universe path/to.csv   # ticker column of a universe CSV
 *   node scripts/stooq_browser_fetch.mjs AAPL --since 20260101    # d1 lower bound (YYYYMMDD)
 *   node scripts/stooq_browser_fetch.mjs AAPL --out .cache/stooq  # output dir (default .cache/stooq)
 *
 * Output: one <TICKER>.csv per ticker (Stooq's Date,Open,High,Low,Close,Volume
 * layout — exactly what bot.ingest.stooq.parse_stooq_csv reads). Tickers whose
 * response is not CSV (unknown symbol, or "Exceeded the daily hits limit") are
 * reported and skipped; the run continues.
 *
 * Politeness: sequential requests with a fixed delay. Stooq's daily hit limit
 * still applies to the browser session — on the limit marker this script stops
 * cleanly and tells you to resume tomorrow, mirroring StooqRateLimitError.
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const DELAY_MS = 1500;
const LIMIT_MARKER = "exceeded the daily hits limit";

function parseArgs(argv) {
  const args = { tickers: [], out: ".cache/stooq", since: null, universe: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") args.out = argv[++i];
    else if (a === "--since") args.since = argv[++i];
    else if (a === "--universe") args.universe = argv[++i];
    else args.tickers.push(a);
  }
  if (args.universe) {
    const rows = readFileSync(args.universe, "utf8")
      .trim()
      .split(/\r?\n/)
      .filter((r) => r.trim() && !r.trimStart().startsWith("#"));
    const header = rows[0].split(",").map((c) => c.trim().toLowerCase());
    const col = Math.max(header.indexOf("ticker"), 0);
    const skipHeader = header.includes("ticker") ? 1 : 0;
    for (const row of rows.slice(skipHeader)) {
      const t = row.split(",")[col]?.trim();
      if (t) args.tickers.push(t);
    }
  }
  if (!args.tickers.length) {
    console.error("usage: stooq_browser_fetch.mjs <TICKER...> [--universe csv] [--since YYYYMMDD] [--out dir]");
    process.exit(2);
  }
  return args;
}

function stooqSymbol(ticker) {
  // Mirror bot.ingest.stooq.stooq_symbol: lowercase, "." -> "-", ".us" suffix.
  return ticker.trim().toLowerCase().replaceAll(".", "-") + ".us";
}

function cdpBrowserUrl() {
  // Honor AGENT_BROWSER_SESSION so the recipe can run against a logged-in
  // session (a free Stooq account lifts the per-ticker daily hit limit).
  const session = process.env.AGENT_BROWSER_SESSION;
  const cmd = session ? ["--session", session, "get", "cdp-url"] : ["get", "cdp-url"];
  const out = execFileSync("agent-browser", cmd, { encoding: "utf8" }).trim();
  const line = out.split(/\s+/).find((w) => w.startsWith("ws://"));
  if (!line) throw new Error("agent-browser returned no CDP URL — is the daemon running?");
  return line;
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      }
    });
  }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((res, rej) => {
      ws.addEventListener("open", res, { once: true });
      ws.addEventListener("error", rej, { once: true });
    });
    return new Cdp(ws);
  }
  send(method, params = {}, sessionId = undefined) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
  close() {
    this.ws.close();
  }
}

async function attachToStooqPage(cdp) {
  const { targetInfos } = await cdp.send("Target.getTargets");
  const page = targetInfos.find((t) => t.type === "page" && t.url.includes("stooq.com"));
  if (!page) {
    throw new Error(
      'No stooq.com tab found. Run first:\n  agent-browser open "https://stooq.com/q/d/?s=aapl.us"\n  agent-browser wait --load networkidle'
    );
  }
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.targetId, flatten: true });
  return sessionId;
}

async function runInPage(cdp, sessionId, expression) {
  const result = await cdp.send(
    "Runtime.evaluate",
    { expression, awaitPromise: true, returnByValue: true },
    sessionId
  );
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description ?? "in-page fetch failed");
  }
  return result.result.value ?? "";
}

async function fetchCsvInPage(cdp, sessionId, symbol, since) {
  // Stooq authorizes the CSV endpoint per symbol: the symbol's quote page must
  // be requested by the trusted session first, or /q/d/l/ answers "Access
  // denied". One warm-up GET per ticker does it (its response is discarded).
  await runInPage(cdp, sessionId, `fetch('/q/d/?s=${symbol}').then(r => r.text()).then(() => true)`);
  let qs = `s=${symbol}&i=d`;
  if (since) {
    const today = new Date().toISOString().slice(0, 10).replaceAll("-", "");
    qs += `&d1=${since}&d2=${today}`; // d1 without d2 returns "No data"
  }
  return runInPage(cdp, sessionId, `fetch('/q/d/l/?${qs}').then(r => r.text())`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const args = parseArgs(process.argv.slice(2));
mkdirSync(args.out, { recursive: true });

const cdp = await Cdp.connect(cdpBrowserUrl());
const sessionId = await attachToStooqPage(cdp);

let saved = 0;
const skipped = [];
for (const ticker of args.tickers) {
  const body = await fetchCsvInPage(cdp, sessionId, stooqSymbol(ticker), args.since);
  const head = body.slice(0, 200).toLowerCase();
  if (head.includes(LIMIT_MARKER)) {
    console.error(`STOP: Stooq daily hit limit reached at ${ticker} (${saved} saved). Resume tomorrow.`);
    break;
  }
  if (!body.trim() || head.startsWith("no data") || head.includes("<html") || !head.startsWith("date,")) {
    skipped.push(ticker);
    console.error(`skip ${ticker}: not CSV (${JSON.stringify(body.slice(0, 60))})`);
  } else {
    const path = join(args.out, `${ticker.toUpperCase()}.csv`);
    writeFileSync(path, body);
    saved++;
    console.log(`${ticker} -> ${path} (${body.trim().split("\n").length - 1} bars)`);
  }
  await sleep(DELAY_MS);
}

console.log(`done: ${saved} saved, ${skipped.length} skipped${skipped.length ? " (" + skipped.join(", ") + ")" : ""}`);
cdp.close();
