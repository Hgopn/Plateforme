"use strict";

const fs = require("node:fs");
const path = require("node:path");

const raw = process.env.INTERARCADE_SERVER_URL;
if (!raw) throw new Error("INTERARCADE_SERVER_URL is required");
const url = new URL(raw);
if (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname))) {
  throw new Error("Remote InterArcade servers must use HTTPS");
}
if (process.env.INTERARCADE_BUILD_CHANNEL === "production" && url.protocol !== "https:") {
  throw new Error("Production packages require an HTTPS server");
}
if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
  throw new Error("Use only the server origin, without credentials or paths");
}
fs.writeFileSync(path.join(__dirname, "server.json"), `${JSON.stringify({ serverUrl: url.origin }, null, 2)}\n`);
