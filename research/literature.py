"""Bounded metadata-only academic research radar (Crossref REST).

A result is a *candidate to read*, never independently verified evidence of
a performance claim. Network use is limited to public Crossref metadata.
No model API, paid credentials, scraping full text or repository writes.
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

API = "https://api.crossref.org/works"
QUERIES = (
    "database adaptive indexing physical design",
    "database crash consistency transaction recovery",
    "incremental view maintenance correctness databases",
    "database buffer cache eviction storage",
)
DOI = re.compile(r"^10\.\d{4,9}/\S{1,150}$", re.I)


def _published(record):
    for key in ("published", "published-online", "published-print", "issued"):
        parts = record.get(key, {}).get("date-parts")
        if parts and parts[0]:
            ymd = list(parts[0])[:3]
            if len(ymd) < 3:
                ymd.extend([1]*(3-len(ymd)))
            try:
                return dt.date(*map(int, ymd)).isoformat()
            except (ValueError, TypeError):
                continue
    return None


def parse_candidates(payload, topic, cutoff):
    if not isinstance(payload, dict):
        raise ValueError("Crossref response is not a JSON object")
    entries = payload.get("message", {}).get("items")
    if not isinstance(entries, list):
        raise ValueError("Crossref response missing message.items")
    out = []
    for record in entries:
        if not isinstance(record, dict):
            continue
        doi = record.get("DOI")
        if not isinstance(doi, str) or not DOI.fullmatch(doi):
            continue
        title_list = record.get("title") or []
        title = title_list[0] if isinstance(title_list, list) and title_list else ""
        date = _published(record)
        if not title or not isinstance(title, str) or not date or date < cutoff:
            continue
        out.append({"doi": doi, "title": " ".join(title.split())[:240],
                    "publication_date": date, "topic": topic,
                    "url": "https://doi.org/" + quote(doi, safe="/")})
    return out


def fetch_json(topic, cutoff, timeout=8):
    params = urlencode({
        "query.bibliographic": topic,
        "filter": "from-pub-date:" + cutoff,
        "rows": 8,
        "select": "DOI,title,published,published-online,published-print,issued",
    })
    url = API + "?" + params
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "OpDB-Foundry-LiteratureRadar/0.1 (https://github.com/mel2003ru-code/OpDB)",
    })
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read(2_000_000).decode("utf-8"))


def run_radar(days=120, today=None, fetcher=fetch_json):
    if not 1 <= days <= 3650:
        raise ValueError("days must be 1..3650")
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cutoff = (today - dt.timedelta(days=days)).isoformat()
    items = {}
    failures = []
    for topic in QUERIES:
        try:
            payload = fetcher(topic,cutoff)
            for candidate in parse_candidates(payload,topic,cutoff):
                items.setdefault(candidate["doi"].lower(),candidate)
        except Exception as exc:
            failures.append({"topic":topic,"error":type(exc).__name__ + ": " + str(exc)[:200]})
    return {
        "date_utc": today.isoformat(), "cutoff": cutoff,
        "status": "UNAVAILABLE" if len(failures)==len(QUERIES) else (
            "PARTIAL" if failures else "COMPLETE"
        ),
        "service": "Crossref REST (metadata only)",
        "queries": list(QUERIES),
        "results": sorted(items.values(),key=lambda v:(v["publication_date"],v["doi"]),reverse=True),
        "failures": failures,
        "disclaimer": "Candidate bibliography only. DOI and metadata must be verified at primary publishers; relevance, novelty and empirical claims have NOT been checked."
    }


def render_markdown(data):
    lines = [
        "# OpDB weekly literature radar — " + data["date_utc"], "",
        "Status: **" + data["status"] + "**. Public Crossref bibliographic metadata since " +
        data["cutoff"] + ".", "",
        "**CANDIDATES ONLY:** no paper was read or independently reproduced. Publication dates",
        "and DOI metadata may be incomplete; inspect original papers before citing claims.", "",
        "| Date | Work | DOI | Topic |", "|---|---|---|---|"
    ]
    for item in data["results"][:30]:
        title = item["title"].replace("|","\\|").replace("[","\\[").replace("]","\\]")
        topic = item["topic"].replace("|","\\|")
        lines.append("| %s | %s | [%s](%s) | %s |" % (
            item["publication_date"], title, item["doi"], item["url"], topic
        ))
    if not data["results"]:
        lines.append("| — | No candidates confirmed by metadata query | — | — |")
    if data["failures"]:
        lines.extend(["", "## Metadata collection errors"])
        for fail in data["failures"]:
            lines.append("- %s: %s" % (fail["topic"],fail["error"]))
    return "\n".join(lines) + "\n"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=120)
    p.add_argument("--json",default="literature-radar.json")
    p.add_argument("--markdown",default="literature-radar.md")
    args=p.parse_args()
    report=run_radar(args.days)
    Path(args.json).write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    md=render_markdown(report)
    Path(args.markdown).write_text(md,encoding="utf-8")
    print(md)
    return 1 if report["status"]=="UNAVAILABLE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
