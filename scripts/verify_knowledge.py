import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("deepseek_client", ROOT / "bot" / "deepseek_client.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

store = module.KnowledgeStore("barrier")
count = store.load(str(ROOT / "knowledge" / "barrier"))
assert count == 48, f"expected 48 entries, got {count}"

queries = [
    ("как открыть шлагбаум через диспетчера", "доступ_1"),
    ("сколько стоит установка", "оплата_3"),
    ("три машины на квартиру", "автомобили_и_реестр_4"),
    ("почта для оплаты 5к5", "оплата_7"),
]

for query, expected_id in queries:
    results = store.search(query)
    assert results, f"no results for: {query}"
    first = results[0]
    assert first.startswith("["), first
    entry = json.loads((ROOT / "knowledge" / "barrier" / "knowledge.json").read_text(encoding="utf-8"))
    expected_title = next(e["title"] for e in entry["entries"] if e["id"] == expected_id)
    assert expected_title in first, f"query={query!r} expected {expected_id}, got {first[:80]!r}"

print("All checks passed")
