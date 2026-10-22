"use strict";

const fs = require("node:fs");
const path = require("node:path");

const configured = JSON.parse(fs.readFileSync(path.join(__dirname, "server.json"), "utf8"));
const url = new URL(configured.serverUrl);
if (url.protocol !== "https:" && process.env.INTERARCADE_ALLOW_LOCAL_PACKAGE !== "1") {
  throw new Error("A public HTTPS server URL is required for a distributable package");
}
if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
  throw new Error("Configure only the public backend origin, without credentials or paths");
}
