const fs = require("node:fs");

const html = fs.readFileSync("app/web/index.html", "utf8");
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (!blocks.length) throw new Error("No inline script found");
for (const block of blocks) new Function(block[1]);
console.log("frontend-script-ok");
