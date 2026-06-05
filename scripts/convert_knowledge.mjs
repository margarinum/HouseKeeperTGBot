import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputPath = path.join(__dirname, "..", "_tmp_docx", "extracted_text.txt");
const outPath = path.join(__dirname, "..", "knowledge", "barrier", "knowledge.json");

const lines = fs.readFileSync(inputPath, "utf8").split(/\r?\n/);

let docTitle = "";
const entries = [];
let current = null;
let phase = "idle";

function finishEntry(entry) {
  if (!entry) return;

  let content = entry.contentLines.join(" ").replace(/\s+/g, " ").trim();
  content = content.replace(/номермавтомобиля/g, "номер автомобиля");
  content = content.replace(/отписыватся/g, "отписывается");
  if (content && /^[а-яё]/i.test(content)) {
    content = content[0].toUpperCase() + content.slice(1);
  }

  let title = entry.title;
  if (title === "Вопросы.") title = "Вопросы";

  const kwText = entry.keywordLines.join(" ").replace(/^Ключевые слова:\s*/i, "");
  const keywords = kwText
    .split(",")
    .map((s) => s.trim().replace(/\.$/, ""))
    .filter(Boolean);

  entries.push({ title, topic: entry.topic, keywords, content });
}

for (const line of lines) {
  const trim = line.trim();
  if (!trim) continue;

  const docMatch = trim.match(/^#\s+(.+)/);
  if (docMatch) {
    if (current) finishEntry(current);
    current = null;
    phase = "idle";
    docTitle = docMatch[1];
    continue;
  }

  const sectionMatch = trim.match(/^##\s+(.+)/);
  if (sectionMatch) {
    if (current) finishEntry(current);
    current = { title: sectionMatch[1], topic: "", contentLines: [], keywordLines: [] };
    phase = "content";
    continue;
  }

  if (!current) continue;

  const topicMatch = trim.match(/^Тема:\s*(.+)/);
  if (topicMatch) {
    if (current.topic && current.topic === topicMatch[1]) continue;
    current.topic = topicMatch[1];
    phase = "keywords_pending";
    continue;
  }

  const kwMatch = trim.match(/^Ключевые слова:\s*(.*)/);
  if (kwMatch) {
    if (current.keywordLines.length > 0) continue;
    current.keywordLines.push(trim);
    phase = "keywords";
    continue;
  }

  if (phase === "content") {
    current.contentLines.push(trim);
  } else if (phase === "keywords" || phase === "keywords_pending") {
    if (phase === "keywords_pending") {
      current.keywordLines.push(`Ключевые слова: ${trim}`);
      phase = "keywords";
    } else {
      current.keywordLines.push(trim);
    }
  }
}
if (current) finishEntry(current);

const topicCounters = {};
const finalEntries = entries.map((e) => {
  topicCounters[e.topic] = (topicCounters[e.topic] || 0) + 1;
  return {
    id: `${e.topic}_${topicCounters[e.topic]}`,
    title: e.title,
    topic: e.topic,
    keywords: e.keywords,
    content: e.content,
  };
});

const payEntry = finalEntries.find((e) => e.title === "Подтверждение оплаты");
if (payEntry) {
  for (const kw of ["3к4", "5к2", "5к3", "5к5"]) {
    if (!payEntry.keywords.includes(kw)) payEntry.keywords.push(kw);
  }
}

const result = {
  title: docTitle,
  version: "2026-06-05",
  entries: finalEntries,
};

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(result, null, 2) + "\n", "utf8");

console.log(`Entries: ${finalEntries.length}`);
console.log(`Written: ${outPath}`);
const nullContent = finalEntries.filter((e) => !e.content).length;
const nullKw = finalEntries.filter((e) => !e.keywords.length).length;
console.log(`Empty content: ${nullContent}, empty keywords: ${nullKw}`);
