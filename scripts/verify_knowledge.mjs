import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const jsonPath = path.join(root, "knowledge", "barrier", "knowledge.json");
const data = JSON.parse(fs.readFileSync(jsonPath, "utf8"));

const entries = data.entries;
if (entries.length !== 48) throw new Error(`Expected 48 entries, got ${entries.length}`);

for (const e of entries) {
  if (!e.id || !e.title || !e.topic || !e.content) throw new Error(`Incomplete entry: ${JSON.stringify(e)}`);
  if (!Array.isArray(e.keywords) || e.keywords.length === 0) throw new Error(`No keywords: ${e.id}`);
}

const dupIds = entries.map((e) => e.id).filter((id, i, arr) => arr.indexOf(id) !== i);
if (dupIds.length) throw new Error(`Duplicate ids: ${dupIds.join(", ")}`);

const pulty = entries.filter((e) => e.title.includes("Пульты"));
if (pulty.length !== 1) throw new Error(`Expected 1 pulty entry, got ${pulty.length}`);

const registry = entries.find((e) => e.id === "автомобили_и_реестр_2");
if (!registry.content.includes("номер автомобиля")) throw new Error("Typo fix missing in registry entry");
if (registry.content.includes("номермавтомобиля")) throw new Error("Typo still present");

const pay = entries.find((e) => e.id === "оплата_7");
if (!pay.keywords.includes("5к5")) throw new Error("Missing 5к5 in payment keywords");

console.log("JSON validation passed:");
console.log(`  entries: ${entries.length}`);
console.log(`  topics: ${new Set(entries.map((e) => e.topic)).size}`);
