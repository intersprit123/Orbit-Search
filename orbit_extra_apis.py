#!/usr/bin/env python3
"""Additional public-data APIs for Orbit Search.

This module deliberately integrates documented public endpoints that do not
normally require developer API keys. Public does not mean unlimited: respect
each provider's rate limits, attribution rules, licences, and acceptable-use
policies. Network calls are restricted to fixed provider hosts; there is no
arbitrary URL-fetch endpoint here.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

USER_AGENT = "OrbitSearch/1.0 (open-source educational search; https://github.com/intersprit123/Orbit-Search)"
MAX_RESPONSE_BYTES = 4_000_000

EXTRA_CATALOG: list[dict[str, str]] = [
    {"route": "GET /api/scholarly/openalex/{works,authors,sources,institutions,topics,publishers}?q=...", "provider": "OpenAlex", "description": "Search open scholarly metadata; keyless basic use, limits apply."},
    {"route": "GET /api/scholarly/openalex/work?id=W...", "provider": "OpenAlex", "description": "Look up one OpenAlex work by identifier."},
    {"route": "GET /api/scholarly/crossref/{works,journals,funders,members}?q=...", "provider": "Crossref", "description": "Search publication, journal, funder and member metadata."},
    {"route": "GET /api/scholarly/crossref/doi?doi=10....", "provider": "Crossref", "description": "Resolve a DOI to public bibliographic metadata."},
    {"route": "GET /api/scholarly/europepmc?q=...", "provider": "Europe PMC", "description": "Search biomedical literature metadata and abstracts."},
    {"route": "GET /api/scholarly/europepmc/article?id=...", "provider": "Europe PMC", "description": "Look up a PMID, PMCID or DOI."},
    {"route": "GET /api/health/clinicaltrials?q=...", "provider": "ClinicalTrials.gov", "description": "Search registered clinical studies."},
    {"route": "GET /api/health/clinicaltrials/study?nct=NCT...", "provider": "ClinicalTrials.gov", "description": "Retrieve one public clinical-study record."},
    {"route": "GET /api/health/openfda?dataset=drug-label&q=...", "provider": "openFDA", "description": "Search selected public FDA datasets; not medical advice."},
    {"route": "GET /api/health/openfda/datasets", "provider": "openFDA", "description": "List supported openFDA datasets."},
    {"route": "GET /api/education/trivia?amount=10&difficulty=medium", "provider": "Open Trivia DB", "description": "Fetch quiz questions."},
    {"route": "GET /api/education/dictionary?word=...", "provider": "Free Dictionary API", "description": "Definitions, phonetics, etymology and examples."},
    {"route": "GET /api/education/synonyms?word=...", "provider": "Free Dictionary API", "description": "Extract synonyms for a word."},
    {"route": "GET /api/education/antonyms?word=...", "provider": "Free Dictionary API", "description": "Extract antonyms for a word."},
    {"route": "GET /api/developer/github/repos?q=...", "provider": "GitHub REST API", "description": "Search public repositories; anonymous rate limits apply."},
    {"route": "GET /api/developer/github/repo?name=owner/repo", "provider": "GitHub REST API", "description": "Repository details."},
    {"route": "GET /api/developer/github/{releases,commits,issues,contributors,languages}?repo=owner/repo", "provider": "GitHub REST API", "description": "Inspect public repository activity and metadata."},
    {"route": "GET /api/developer/github/user?username=...", "provider": "GitHub REST API", "description": "Public GitHub user profile."},
    {"route": "GET /api/developer/github/user-repos?username=...", "provider": "GitHub REST API", "description": "List public repositories for a user."},
    {"route": "GET /api/developer/gitlab/projects?q=...", "provider": "GitLab API", "description": "Search public GitLab projects."},
    {"route": "GET /api/developer/gitlab/project?path=group/project", "provider": "GitLab API", "description": "Look up a public GitLab project."},
    {"route": "GET /api/developer/gitlab/releases?path=group/project", "provider": "GitLab API", "description": "List releases for a public GitLab project."},
    {"route": "GET /api/developer/stackoverflow/search?q=...&site=stackoverflow", "provider": "Stack Exchange API", "description": "Search public Q&A posts."},
    {"route": "GET /api/ai/huggingface/{models,datasets,spaces}?q=...", "provider": "Hugging Face Hub", "description": "Search public AI models, datasets or Spaces."},
    {"route": "GET /api/ai/huggingface/model?id=org/name", "provider": "Hugging Face Hub", "description": "Public model metadata."},
    {"route": "GET /api/ai/huggingface/dataset?id=org/name", "provider": "Hugging Face Hub", "description": "Public dataset metadata."},
    {"route": "GET /api/ai/huggingface/space?id=org/name", "provider": "Hugging Face Hub", "description": "Public Space metadata."},
    {"route": "GET /api/packages/search?q=...", "provider": "npm, crates.io, Maven Central, RubyGems", "description": "Federated package search with partial results."},
    {"route": "GET /api/packages/npm/search?q=...", "provider": "npm Registry", "description": "Search JavaScript packages."},
    {"route": "GET /api/packages/npm/package?name=...", "provider": "npm Registry", "description": "Get package metadata."},
    {"route": "GET /api/packages/pypi/project?name=...", "provider": "PyPI", "description": "Get Python package metadata and releases."},
    {"route": "GET /api/packages/pypi/release?name=...&version=...", "provider": "PyPI", "description": "Get one Python release's metadata."},
    {"route": "GET /api/packages/crates/search?q=...", "provider": "crates.io", "description": "Search Rust crates."},
    {"route": "GET /api/packages/crates/package?name=...", "provider": "crates.io", "description": "Get Rust crate metadata."},
    {"route": "GET /api/packages/maven/search?q=...", "provider": "Maven Central", "description": "Search Java artifacts."},
    {"route": "GET /api/packages/rubygems/search?q=...", "provider": "RubyGems", "description": "Search Ruby gems."},
    {"route": "GET /api/packages/rubygems/gem?name=...", "provider": "RubyGems", "description": "Get gem metadata."},
    {"route": "GET /api/packages/nuget/search?q=...", "provider": "NuGet", "description": "Search .NET packages."},
    {"route": "GET /api/knowledge/{summary,page,random,categories}", "provider": "Wikipedia REST/Action API", "description": "Look up page summaries, extracts, random pages and categories."},
    {"route": "GET /api/knowledge/wikidata/{search,entity}", "provider": "Wikidata", "description": "Search entities and resolve Q identifiers."},
    {"route": "GET /api/archives/search?q=...", "provider": "Internet Archive", "description": "Search public archive metadata."},
    {"route": "GET /api/archives/metadata?id=...", "provider": "Internet Archive", "description": "Retrieve metadata for an archive item."},
    {"route": "GET /api/archives/wayback?url=https://...", "provider": "Internet Archive Wayback Machine", "description": "Find available snapshots of a URL."},
    {"route": "GET /api/open-data/library-of-congress/search?q=...", "provider": "Library of Congress", "description": "Search public catalogue records and digital collections."},
    {"route": "GET /api/science/earthquakes?period=day&min_magnitude=2.5", "provider": "USGS", "description": "Query recent earthquake events."},
    {"route": "GET /api/science/species?q=...", "provider": "GBIF", "description": "Search taxonomic names."},
    {"route": "GET /api/science/occurrences?taxon_key=...", "provider": "GBIF", "description": "Search public species occurrence records."},
    {"route": "GET /api/science/space/news?q=...", "provider": "Spaceflight News API", "description": "Search spaceflight articles."},
    {"route": "GET /api/science/space/launches?limit=10", "provider": "Spaceflight News API", "description": "List published launch records."},
    {"route": "GET /api/media/itunes/search?term=...&entity=song", "provider": "Apple iTunes Search API", "description": "Search music, books, podcasts, films or apps."},
    {"route": "GET /api/media/itunes/lookup?id=...", "provider": "Apple iTunes Search API", "description": "Look up an Apple catalogue item."},
    {"route": "GET /api/media/musicbrainz/search?q=...&type=artist", "provider": "MusicBrainz", "description": "Search public music metadata."},
    {"route": "GET /api/entertainment/tv/search?q=...", "provider": "TVmaze", "description": "Search television shows."},
    {"route": "GET /api/entertainment/tv/show?id=...", "provider": "TVmaze", "description": "Retrieve a television show."},
    {"route": "GET /api/entertainment/tv/episodes?id=...", "provider": "TVmaze", "description": "List a show's episodes."},
    {"route": "GET /api/games/pokemon/search?q=...", "provider": "PokéAPI", "description": "Search Pokémon names."},
    {"route": "GET /api/games/pokemon/details?name=...", "provider": "PokéAPI", "description": "Retrieve Pokémon stats and type."},
    {"route": "GET /api/games/pokemon/{ability,type,item}?name=...", "provider": "PokéAPI", "description": "Look up Pokémon abilities, types and items."},
    {"route": "GET /api/food/search?q=...", "provider": "Open Food Facts", "description": "Search public food product records."},
    {"route": "GET /api/food/product?barcode=...", "provider": "Open Food Facts", "description": "Retrieve a product by barcode."},
    {"route": "GET /api/economy/worldbank/countries?q=...", "provider": "World Bank", "description": "Search country metadata."},
    {"route": "GET /api/economy/worldbank/indicator?country=IND&indicator=NY.GDP.MKTP.CD", "provider": "World Bank", "description": "Retrieve a country indicator time series."},
    {"route": "GET /api/economy/worldbank/indicators?q=...", "provider": "World Bank", "description": "Search public indicator metadata."},
    {"route": "GET /api/network/dns?name=example.com&type=A", "provider": "Cloudflare DNS over HTTPS", "description": "Query DNS records."},
    {"route": "GET /api/network/domain?name=example.com", "provider": "RDAP", "description": "Retrieve public domain registration data where available."},
    {"route": "GET /api/network/certificates?domain=example.com", "provider": "crt.sh", "description": "Find public TLS certificate transparency records."},
]


def _value(params: dict[str, list[str]], key: str, default: str = "") -> str:
    return str(params.get(key, [default])[0]).strip()


def _int_param(params: dict[str, list[str]], key: str, default: int, maximum: int) -> int:
    try:
        value = int(_value(params, key, str(default)))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be an integer.")
    return max(1, min(value, maximum))


def _required(params: dict[str, list[str]], key: str, max_length: int = 300) -> str:
    value = _value(params, key)[:max_length]
    if not value:
        raise ValueError(f"Missing required query parameter: {key}.")
    return value


def _url(base: str, values: dict[str, Any] | list[tuple[str, Any]]) -> str:
    items = list(values.items()) if isinstance(values, dict) else values
    return base + "?" + urllib.parse.urlencode([(k, v) for k, v in items if v is not None])


def _json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 15,
          max_bytes: int = MAX_RESPONSE_BYTES) -> Any:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Provider response exceeded the configured size limit.")
    return json.loads(raw.decode("utf-8", "replace"))


def _normal_results(provider: str, query: str, results: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True, "provider": provider, "query": query,
        "count": len(results), "results": results,
    }
    payload.update(extra)
    return payload


def _domain(params: dict[str, list[str]], key: str = "domain") -> str:
    value = _required(params, key, 253).lower().rstrip(".")
    if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
        raise ValueError(f"{key} must be a public DNS domain name.")
    return value


def _repo(params: dict[str, list[str]], key: str = "repo") -> tuple[str, str]:
    value = _required(params, key, 200).strip("/")
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", value)
    if not match or match.group(1) in {".", ".."} or match.group(2) in {".", ".."}:
        raise ValueError(f"{key} must be in owner/repository form.")
    return match.group(1), match.group(2)


def _github(url: str) -> Any:
    return _json(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})


def _github_repo_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "name": row.get("full_name"), "description": row.get("description"),
        "url": row.get("html_url"), "api_url": row.get("url"),
        "stars": row.get("stargazers_count"), "forks": row.get("forks_count"),
        "language": row.get("language"), "license": (row.get("license") or {}).get("spdx_id"),
        "updated_at": row.get("updated_at"), "archived": row.get("archived"),
    } for row in rows]


def _openalex(entity: str, q: str, limit: int) -> dict[str, Any]:
    allowed = {"works", "authors", "sources", "institutions", "topics", "publishers"}
    if entity not in allowed:
        raise ValueError("Unsupported OpenAlex entity.")
    data = _json(_url("https://api.openalex.org/" + entity, {
        "search": q, "per-page": limit,
    }))
    rows = []
    for item in data.get("results", []) or []:
        identifier = item.get("id", "")
        title = item.get("display_name") or item.get("title") or identifier
        rows.append({
            "title": title, "url": identifier, "id": identifier,
            "description": item.get("description"), "type": item.get("type"),
            "publication_year": item.get("publication_year"),
            "cited_by_count": item.get("cited_by_count"),
            "works_count": item.get("works_count"), "country_code": item.get("country_code"),
            "doi": item.get("doi"), "source": "OpenAlex",
        })
    return _normal_results("OpenAlex", q, rows, meta=data.get("meta", {}))


def _crossref(entity: str, q: str, limit: int) -> dict[str, Any]:
    allowed = {"works", "journals", "funders", "members"}
    if entity not in allowed:
        raise ValueError("Unsupported Crossref entity.")
    data = _json(_url("https://api.crossref.org/" + entity, {
        "query": q, "rows": limit,
    }))
    message = data.get("message", {})
    rows = []
    for item in message.get("items", []) or []:
        titles = item.get("title") or item.get("name") or []
        title = titles[0] if isinstance(titles, list) and titles else str(titles or item.get("DOI") or "")
        rows.append({
            "title": title, "doi": item.get("DOI"),
            "url": item.get("URL") or (("https://doi.org/" + item["DOI"]) if item.get("DOI") else ""),
            "authors": item.get("author", []), "published": item.get("published") or item.get("created"),
            "journal": item.get("container-title"), "publisher": item.get("publisher"),
            "type": item.get("type"), "source": "Crossref",
        })
    return _normal_results("Crossref", q, rows, total=message.get("total"))


def _europepmc(q: str, limit: int) -> dict[str, Any]:
    data = _json(_url("https://www.ebi.ac.uk/europepmc/webservices/rest/search", {
        "query": q, "format": "json", "pageSize": limit, "resultType": "core",
    }))
    rows = []
    for item in (data.get("resultList", {}) or {}).get("result", []) or []:
        doi = item.get("doi")
        pmid = item.get("pmid")
        pmcid = item.get("pmcid")
        link = ("https://doi.org/" + doi if doi else
                "https://europepmc.org/articles/" + pmcid if pmcid else
                "https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/" if pmid else "")
        rows.append({
            "title": item.get("title"), "url": link, "doi": doi, "pmid": pmid, "pmcid": pmcid,
            "authors": item.get("authorString"), "journal": item.get("journalTitle"),
            "published": item.get("firstPublicationDate"), "abstract": item.get("abstractText"),
            "source": "Europe PMC",
        })
    return _normal_results("Europe PMC", q, rows, hit_count=data.get("hitCount"))


def _clinical_trials(q: str, limit: int) -> dict[str, Any]:
    data = _json(_url("https://clinicaltrials.gov/api/v2/studies", {
        "query.term": q, "pageSize": limit, "format": "json",
    }))
    rows = []
    for study in data.get("studies", []) or []:
        p = study.get("protocolSection", {})
        ident = p.get("identificationModule", {})
        status = p.get("statusModule", {})
        design = p.get("designModule", {})
        nct = ident.get("nctId")
        rows.append({
            "title": ident.get("briefTitle") or ident.get("officialTitle"),
            "url": "https://clinicaltrials.gov/study/" + str(nct) if nct else "",
            "nct_id": nct, "status": status.get("overallStatus"),
            "start_date": (status.get("startDateStruct") or {}).get("date"),
            "completion_date": (status.get("completionDateStruct") or {}).get("date"),
            "study_type": design.get("studyType"), "source": "ClinicalTrials.gov",
        })
    return _normal_results("ClinicalTrials.gov", q, rows, total=data.get("totalCount"))


FDA_DATASETS = {
    "drug-label": ("drug", "label"),
    "drug-event": ("drug", "event"),
    "food-enforcement": ("food", "enforcement"),
    "device-event": ("device", "event"),
    "device-recall": ("device", "recall"),
}


def _openfda(dataset: str, q: str, limit: int) -> dict[str, Any]:
    if dataset not in FDA_DATASETS:
        raise ValueError("dataset must be one of: " + ", ".join(FDA_DATASETS))
    category, endpoint = FDA_DATASETS[dataset]
    params: dict[str, Any] = {"limit": limit}
    if q:
        params["search"] = q
    data = _json(_url(f"https://api.fda.gov/{category}/{endpoint}.json", params))
    rows = data.get("results", []) or []
    return _normal_results("openFDA", q, rows, dataset=dataset,
                           total=(data.get("meta", {}).get("results") or {}).get("total"))


def _trivia(params: dict[str, list[str]]) -> dict[str, Any]:
    amount = _int_param(params, "amount", 10, 50)
    values: dict[str, Any] = {"amount": amount}
    category = _value(params, "category")
    difficulty = _value(params, "difficulty").lower()
    question_type = _value(params, "type").lower()
    if category:
        if not category.isdigit():
            raise ValueError("category must be a numeric Open Trivia DB category ID.")
        values["category"] = category
    if difficulty:
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("difficulty must be easy, medium, or hard.")
        values["difficulty"] = difficulty
    if question_type:
        if question_type not in {"multiple", "boolean"}:
            raise ValueError("type must be multiple or boolean.")
        values["type"] = question_type
    data = _json(_url("https://opentdb.com/api.php", values))
    results = []
    for row in data.get("results", []) or []:
        results.append({
            "category": html.unescape(row.get("category", "")),
            "type": row.get("type"), "difficulty": row.get("difficulty"),
            "question": html.unescape(row.get("question", "")),
            "correct_answer": html.unescape(row.get("correct_answer", "")),
            "incorrect_answers": [html.unescape(v) for v in row.get("incorrect_answers", [])],
        })
    return {"ok": True, "provider": "Open Trivia DB", "response_code": data.get("response_code"),
            "count": len(results), "results": results}


def _dictionary(word: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z][A-Za-z'-]{0,79}", word):
        raise ValueError("word must contain only letters, apostrophes or hyphens.")
    data = _json("https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(word, safe=""))
    entries = []
    synonyms: set[str] = set()
    antonyms: set[str] = set()
    for entry in data if isinstance(data, list) else []:
        meanings = []
        for meaning in entry.get("meanings", []) or []:
            definitions = []
            for d in meaning.get("definitions", []) or []:
                definitions.append({"definition": d.get("definition"), "example": d.get("example"),
                                    "synonyms": d.get("synonyms", []), "antonyms": d.get("antonyms", [])})
                synonyms.update(d.get("synonyms", []))
                antonyms.update(d.get("antonyms", []))
            synonyms.update(meaning.get("synonyms", []))
            antonyms.update(meaning.get("antonyms", []))
            meanings.append({"part_of_speech": meaning.get("partOfSpeech"), "definitions": definitions,
                             "synonyms": meaning.get("synonyms", []), "antonyms": meaning.get("antonyms", [])})
        entries.append({"word": entry.get("word"), "phonetics": entry.get("phonetics", []),
                        "origin": entry.get("origin"), "meanings": meanings})
    return {"ok": True, "provider": "Free Dictionary API", "word": word,
            "entries": entries, "synonyms": sorted(synonyms), "antonyms": sorted(antonyms)}


def _github_api(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    base = "https://api.github.com"
    if path == "/api/developer/github/repos":
        q = _required(params, "q")
        data = _github(_url(base + "/search/repositories", {"q": q, "per_page": limit, "sort": "stars"}))
        rows = _github_repo_rows(data.get("items", []))
        return _normal_results("GitHub", q, rows, total=data.get("total_count"), incomplete=data.get("incomplete_results"))
    if path == "/api/developer/github/user":
        username = _required(params, "username", 100)
        if not re.fullmatch(r"[A-Za-z0-9-]+", username):
            raise ValueError("username contains unsupported characters.")
        data = _github(base + "/users/" + urllib.parse.quote(username, safe=""))
        return {"ok": True, "provider": "GitHub", "result": {
            "login": data.get("login"), "name": data.get("name"), "bio": data.get("bio"),
            "url": data.get("html_url"), "followers": data.get("followers"),
            "following": data.get("following"), "public_repos": data.get("public_repos"),
            "location": data.get("location"), "created_at": data.get("created_at"),
        }}
    if path == "/api/developer/github/user-repos":
        username = _required(params, "username", 100)
        if not re.fullmatch(r"[A-Za-z0-9-]+", username):
            raise ValueError("username contains unsupported characters.")
        data = _github(_url(base + "/users/" + urllib.parse.quote(username, safe="") + "/repos",
                            {"per_page": limit, "sort": "updated", "type": "public"}))
        return _normal_results("GitHub", username, _github_repo_rows(data))
    if path in {"/api/developer/github/repo", "/api/developer/github/releases",
                "/api/developer/github/commits", "/api/developer/github/issues",
                "/api/developer/github/contributors", "/api/developer/github/languages"}:
        owner, name = _repo(params, "name" if path.endswith("/repo") else "repo")
        root = base + "/repos/" + urllib.parse.quote(owner, safe="") + "/" + urllib.parse.quote(name, safe="")
        if path.endswith("/repo"):
            data = _github(root)
            return {"ok": True, "provider": "GitHub", "result": {
                "name": data.get("full_name"), "description": data.get("description"),
                "url": data.get("html_url"), "homepage": data.get("homepage"),
                "stars": data.get("stargazers_count"), "watchers": data.get("watchers_count"),
                "forks": data.get("forks_count"), "open_issues": data.get("open_issues_count"),
                "language": data.get("language"), "license": (data.get("license") or {}).get("spdx_id"),
                "default_branch": data.get("default_branch"), "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"), "archived": data.get("archived"),
            }}
        suffix = path.rsplit("/", 1)[-1]
        if suffix == "languages":
            data = _github(root + "/languages")
            return {"ok": True, "provider": "GitHub", "repository": owner + "/" + name, "languages": data}
        query: dict[str, Any] = {"per_page": limit}
        if suffix == "issues":
            state = _value(params, "state", "open")
            if state not in {"open", "closed", "all"}:
                raise ValueError("state must be open, closed or all.")
            query["state"] = state
            url = _url(root + "/issues", query)
            data = _github(url)
            rows = [{"title": x.get("title"), "url": x.get("html_url"), "number": x.get("number"),
                     "state": x.get("state"), "created_at": x.get("created_at"),
                     "updated_at": x.get("updated_at"), "user": (x.get("user") or {}).get("login"),
                     "pull_request": bool(x.get("pull_request"))} for x in data if not x.get("pull_request")]
        else:
            endpoint = {"releases": "releases", "commits": "commits", "contributors": "contributors"}[suffix]
            data = _github(_url(root + "/" + endpoint, query))
            if suffix == "releases":
                rows = [{"tag": x.get("tag_name"), "title": x.get("name"), "url": x.get("html_url"),
                         "published_at": x.get("published_at"), "draft": x.get("draft"),
                         "prerelease": x.get("prerelease")} for x in data]
            elif suffix == "commits":
                rows = [{"sha": x.get("sha"), "url": x.get("html_url"),
                         "message": ((x.get("commit") or {}).get("message") or "").splitlines()[0],
                         "author": ((x.get("commit") or {}).get("author") or {}).get("name"),
                         "date": ((x.get("commit") or {}).get("author") or {}).get("date")} for x in data]
            else:
                rows = [{"login": x.get("login"), "url": x.get("html_url"),
                         "contributions": x.get("contributions")} for x in data]
        return _normal_results("GitHub", owner + "/" + name, rows)
    return None


def _gitlab(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    base = "https://gitlab.com/api/v4"
    if path == "/api/developer/gitlab/projects":
        q = _required(params, "q")
        data = _json(_url(base + "/projects", {"search": q, "simple": "true", "per_page": limit,
                                                "order_by": "star_count", "sort": "desc"}))
        rows = [{"name": x.get("path_with_namespace"), "description": x.get("description"),
                 "url": x.get("web_url"), "stars": x.get("star_count"),
                 "forks": x.get("forks_count"), "last_activity": x.get("last_activity_at"),
                 "default_branch": x.get("default_branch")} for x in data]
        return _normal_results("GitLab", q, rows)
    if path in {"/api/developer/gitlab/project", "/api/developer/gitlab/releases"}:
        repo = _required(params, "path", 200).strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", repo) or ".." in repo.split("/"):
            raise ValueError("path must be a GitLab namespace/project path.")
        project_url = base + "/projects/" + urllib.parse.quote(repo, safe="")
        if path.endswith("/project"):
            x = _json(project_url)
            return {"ok": True, "provider": "GitLab", "result": {
                "name": x.get("path_with_namespace"), "description": x.get("description"),
                "url": x.get("web_url"), "stars": x.get("star_count"), "forks": x.get("forks_count"),
                "issues_enabled": x.get("issues_enabled"), "default_branch": x.get("default_branch"),
                "last_activity": x.get("last_activity_at"),
            }}
        data = _json(_url(project_url + "/releases", {"per_page": limit}))
        rows = [{"name": x.get("name"), "tag": x.get("tag_name"), "description": x.get("description"),
                 "url": x.get("_links", {}).get("self"), "released_at": x.get("released_at")} for x in data]
        return _normal_results("GitLab", repo, rows)
    return None


def _stackoverflow(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path != "/api/developer/stackoverflow/search":
        return None
    q = _required(params, "q")
    site = _value(params, "site", "stackoverflow").lower()
    allowed = {"stackoverflow", "superuser", "serverfault", "askubuntu", "unix", "math", "dba", "gis"}
    if site not in allowed:
        raise ValueError("site must be one of: " + ", ".join(sorted(allowed)))
    data = _json(_url("https://api.stackexchange.com/2.3/search/advanced", {
        "site": site, "q": q, "order": "desc", "sort": "relevance", "pagesize": limit,
        "filter": "default",
    }))
    rows = [{"title": html.unescape(x.get("title", "")), "url": x.get("link"),
             "score": x.get("score"), "answer_count": x.get("answer_count"),
             "is_answered": x.get("is_answered"), "created_at": x.get("creation_date"),
             "tags": x.get("tags", []), "owner": (x.get("owner") or {}).get("display_name")}
            for x in data.get("items", []) or []]
    return _normal_results("Stack Exchange", q, rows, quota=data.get("quota_remaining"),
                           site=site, has_more=data.get("has_more"))


def _huggingface(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    map_paths = {
        "/api/ai/huggingface/models": "models",
        "/api/ai/huggingface/datasets": "datasets",
        "/api/ai/huggingface/spaces": "spaces",
    }
    detail_paths = {
        "/api/ai/huggingface/model": "models",
        "/api/ai/huggingface/dataset": "datasets",
        "/api/ai/huggingface/space": "spaces",
    }
    base = "https://huggingface.co/api/"
    if path in map_paths:
        q = _required(params, "q")
        typ = map_paths[path]
        data = _json(_url(base + typ, {"search": q, "limit": limit, "sort": "downloads", "direction": "-1"}))
        rows = [{"id": x.get("id"), "title": x.get("id"), "url": "https://huggingface.co/" + typ.rstrip("s") + "/" + str(x.get("id", "")),
                 "downloads": x.get("downloads"), "likes": x.get("likes"),
                 "last_modified": x.get("lastModified"), "pipeline_tag": x.get("pipeline_tag"),
                 "library_name": x.get("library_name"), "tags": x.get("tags", [])} for x in data]
        return _normal_results("Hugging Face Hub", q, rows, entity=typ)
    if path in detail_paths:
        identifier = _required(params, "id", 200).strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", identifier):
            raise ValueError("id must be in owner/name form.")
        typ = detail_paths[path]
        data = _json(base + typ + "/" + urllib.parse.quote(identifier, safe="/"))
        return {"ok": True, "provider": "Hugging Face Hub", "entity": typ, "result": data}
    return None


def _npm_search(q: str, limit: int) -> list[dict[str, Any]]:
    data = _json(_url("https://registry.npmjs.org/-/v1/search", {"text": q, "size": limit}))
    return [{"name": (x.get("package") or {}).get("name"),
             "title": (x.get("package") or {}).get("name"),
             "description": (x.get("package") or {}).get("description"),
             "url": (x.get("package") or {}).get("links", {}).get("npm"),
             "version": (x.get("package") or {}).get("version"),
             "publisher": (x.get("package") or {}).get("publisher", {}).get("username"),
             "downloads": x.get("score", {}).get("detail", {}).get("popularity"),
             "source": "npm"} for x in data.get("objects", []) or []]


def _crates_search(q: str, limit: int) -> list[dict[str, Any]]:
    data = _json(_url("https://crates.io/api/v1/crates", {"q": q, "per_page": limit}))
    return [{"name": x.get("name"), "title": x.get("name"), "description": x.get("description"),
             "url": "https://crates.io/crates/" + str(x.get("id", "")),
             "version": x.get("newest_version"), "downloads": x.get("downloads"),
             "source": "crates.io"} for x in data.get("crates", []) or []]


def _maven_search(q: str, limit: int) -> list[dict[str, Any]]:
    data = _json(_url("https://search.maven.org/solrsearch/select", {"q": q, "rows": limit, "wt": "json"}))
    return [{"name": str(x.get("g", "")) + ":" + str(x.get("a", "")),
             "title": str(x.get("g", "")) + ":" + str(x.get("a", "")),
             "description": None, "url": "https://search.maven.org/artifact/" + str(x.get("g", "")) + "/" + str(x.get("a", "")) + "/" + str(x.get("latestVersion", "")) + "/jar",
             "version": x.get("latestVersion"), "packaging": x.get("p"), "source": "Maven Central"}
            for x in data.get("response", {}).get("docs", []) or []]


def _rubygems_search(q: str, limit: int) -> list[dict[str, Any]]:
    data = _json(_url("https://rubygems.org/api/v1/search.json", {"query": q}))
    return [{"name": x.get("name"), "title": x.get("name"), "description": x.get("info"),
             "url": x.get("project_uri") or x.get("gem_uri"),
             "version": x.get("version"), "downloads": x.get("downloads"),
             "source": "RubyGems"} for x in (data or [])[:limit]]


def _packages(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/packages/search":
        q = _required(params, "q")
        results: list[dict[str, Any]] = []
        providers = []
        for name, fn in (("npm", _npm_search), ("crates.io", _crates_search),
                         ("Maven Central", _maven_search), ("RubyGems", _rubygems_search)):
            try:
                rows = fn(q, min(limit, 8))
                results.extend(rows)
                providers.append({"name": name, "ok": True, "count": len(rows)})
            except Exception as exc:
                providers.append({"name": name, "ok": False, "error": type(exc).__name__})
        if not any(x["ok"] for x in providers):
            raise RuntimeError("All package providers failed.")
        return _normal_results("Orbit package search", q, results, providers=providers,
                               partial=any(not x["ok"] for x in providers))
    if path == "/api/packages/npm/search":
        q = _required(params, "q")
        return _normal_results("npm", q, _npm_search(q, limit))
    if path == "/api/packages/npm/package":
        name = _required(params, "name", 214)
        if not re.fullmatch(r"(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+", name):
            raise ValueError("Invalid npm package name.")
        data = _json("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@/"))
        latest = data.get("dist-tags", {}).get("latest")
        version = data.get("versions", {}).get(latest, {}) if latest else {}
        return {"ok": True, "provider": "npm", "name": name, "latest": latest,
                "description": version.get("description"), "homepage": version.get("homepage"),
                "repository": version.get("repository"), "license": version.get("license"),
                "versions": list((data.get("versions") or {}).keys())[:100],
                "url": "https://www.npmjs.com/package/" + name}
    if path in {"/api/packages/pypi/project", "/api/packages/pypi/release"}:
        name = _required(params, "name", 200)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Invalid PyPI package name.")
        version = _value(params, "version", "")
        if path.endswith("/release"):
            version = _required(params, "version", 80)
            if not re.fullmatch(r"[A-Za-z0-9_.+!-]+", version):
                raise ValueError("Invalid PyPI version.")
            url = f"https://pypi.org/pypi/{urllib.parse.quote(name, safe='')}/{urllib.parse.quote(version, safe='')}/json"
        else:
            url = f"https://pypi.org/pypi/{urllib.parse.quote(name, safe='')}/json"
        data = _json(url)
        info = data.get("info", {})
        return {"ok": True, "provider": "PyPI", "name": info.get("name"), "version": info.get("version"),
                "summary": info.get("summary"), "description": info.get("description", "")[:4000],
                "author": info.get("author"), "license": info.get("license"),
                "requires_python": info.get("requires_python"), "classifiers": info.get("classifiers", []),
                "project_urls": info.get("project_urls", {}), "releases": list((data.get("releases") or {}).keys())[:200],
                "url": info.get("project_url")}
    if path == "/api/packages/crates/search":
        q = _required(params, "q")
        return _normal_results("crates.io", q, _crates_search(q, limit))
    if path == "/api/packages/crates/package":
        name = _required(params, "name", 200)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid crate name.")
        data = _json("https://crates.io/api/v1/crates/" + urllib.parse.quote(name, safe=""),
                     headers={"User-Agent": USER_AGENT + " (mailto:maintainers@example.invalid)"})
        item = data.get("crate", {})
        return {"ok": True, "provider": "crates.io", "result": item}
    if path == "/api/packages/maven/search":
        q = _required(params, "q")
        return _normal_results("Maven Central", q, _maven_search(q, limit))
    if path == "/api/packages/rubygems/search":
        q = _required(params, "q")
        return _normal_results("RubyGems", q, _rubygems_search(q, limit))
    if path == "/api/packages/rubygems/gem":
        name = _required(params, "name", 200)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Invalid RubyGem name.")
        data = _json("https://rubygems.org/api/v2/rubygems/" + urllib.parse.quote(name, safe="") + ".json")
        return {"ok": True, "provider": "RubyGems", "result": data}
    if path == "/api/packages/nuget/search":
        q = _required(params, "q")
        data = _json(_url("https://azuresearch-usnc.nuget.org/query", {"q": q, "take": limit}))
        rows = [{"name": x.get("id"), "title": x.get("id"), "description": x.get("description"),
                 "version": x.get("version"), "downloads": x.get("totalDownloads"),
                 "url": "https://www.nuget.org/packages/" + str(x.get("id", "")), "source": "NuGet"}
                for x in data.get("data", []) or []]
        return _normal_results("NuGet", q, rows, total=data.get("totalHits"))
    return None


def _wikipedia(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/knowledge/summary":
        title = _required(params, "title", 300)
        lang = _value(params, "lang", "en").lower()
        if not re.fullmatch(r"[a-z-]{2,12}", lang):
            raise ValueError("lang must be a language code such as en.")
        data = _json("https://" + lang + ".wikipedia.org/api/rest_v1/page/summary/" +
                     urllib.parse.quote(title.replace(" ", "_"), safe=""))
        return {"ok": True, "provider": "Wikipedia", "result": {
            "title": data.get("title"), "description": data.get("description"),
            "extract": data.get("extract"), "url": (data.get("content_urls") or {}).get("desktop", {}).get("page"),
            "thumbnail": (data.get("thumbnail") or {}).get("source"),
            "type": data.get("type"), "revision": data.get("revision"),
        }}
    if path in {"/api/knowledge/page", "/api/knowledge/categories"}:
        title = _required(params, "title", 300)
        prop = "extracts|info|categories" if path.endswith("/categories") else "extracts|info|pageimages"
        values = {"action": "query", "titles": title, "prop": prop, "format": "json",
                  "redirects": 1, "explaintext": 1, "inprop": "url", "cllimit": limit}
        data = _json(_url("https://en.wikipedia.org/w/api.php", values))
        pages = list((data.get("query") or {}).get("pages", {}).values())
        if not pages:
            return {"ok": True, "provider": "Wikipedia", "result": None}
        page = pages[0]
        if path.endswith("/categories"):
            cats = [x.get("title", "").removeprefix("Category:") for x in page.get("categories", [])]
            return {"ok": True, "provider": "Wikipedia", "title": page.get("title"),
                    "url": page.get("fullurl"), "categories": cats}
        return {"ok": True, "provider": "Wikipedia", "result": {
            "title": page.get("title"), "extract": page.get("extract"), "url": page.get("fullurl"),
            "thumbnail": (page.get("thumbnail") or {}).get("source"),
        }}
    if path == "/api/knowledge/random":
        data = _json(_url("https://en.wikipedia.org/w/api.php", {
            "action": "query", "generator": "random", "grnnamespace": 0, "grnlimit": 1,
            "prop": "extracts|info", "explaintext": 1, "inprop": "url", "format": "json",
        }))
        pages = list((data.get("query") or {}).get("pages", {}).values())
        page = pages[0] if pages else {}
        return {"ok": True, "provider": "Wikipedia", "result": {
            "title": page.get("title"), "extract": page.get("extract"), "url": page.get("fullurl")}}
    if path == "/api/knowledge/wikidata/search":
        q = _required(params, "q")
        data = _json(_url("https://www.wikidata.org/w/api.php", {
            "action": "wbsearchentities", "search": q, "language": _value(params, "lang", "en"),
            "uselang": _value(params, "lang", "en"), "format": "json", "limit": limit,
        }))
        rows = [{"id": x.get("id"), "title": x.get("label"), "description": x.get("description"),
                 "url": x.get("concepturi"), "aliases": x.get("aliases", [])}
                for x in data.get("search", []) or []]
        return _normal_results("Wikidata", q, rows)
    if path == "/api/knowledge/wikidata/entity":
        entity_id = _required(params, "id", 30).upper()
        if not re.fullmatch(r"Q[1-9][0-9]*", entity_id):
            raise ValueError("id must be a Wikidata Q identifier, such as Q42.")
        data = _json(_url("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": entity_id, "props": "labels|descriptions|aliases|sitelinks",
            "languages": _value(params, "lang", "en"), "format": "json",
        }))
        return {"ok": True, "provider": "Wikidata", "result": data.get("entities", {}).get(entity_id)}
    return None


def _archives(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/archives/search":
        q = _required(params, "q")
        fl = [("q", q), ("output", "json"), ("rows", limit),
              ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "description"),
              ("fl[]", "mediatype"), ("fl[]", "year"), ("page", 1)]
        data = _json(_url("https://archive.org/advancedsearch.php", fl))
        docs = data.get("response", {}).get("docs", []) or []
        rows = [{"title": x.get("title"), "url": "https://archive.org/details/" + str(x.get("identifier", "")),
                 "identifier": x.get("identifier"), "description": x.get("description"),
                 "mediatype": x.get("mediatype"), "year": x.get("year"), "source": "Internet Archive"}
                for x in docs]
        return _normal_results("Internet Archive", q, rows, total=data.get("response", {}).get("numFound"))
    if path == "/api/archives/metadata":
        identifier = _required(params, "id", 200)
        if not re.fullmatch(r"[A-Za-z0-9._-]+", identifier):
            raise ValueError("id contains unsupported characters.")
        data = _json("https://archive.org/metadata/" + urllib.parse.quote(identifier, safe=""))
        meta = data.get("metadata", {})
        return {"ok": True, "provider": "Internet Archive", "identifier": identifier,
                "metadata": meta, "files": [{"name": x.get("name"), "size": x.get("size"),
                    "format": x.get("format"), "source": x.get("source")} for x in data.get("files", [])[:100]],
                "url": "https://archive.org/details/" + identifier}
    if path == "/api/archives/wayback":
        target = _required(params, "url", 2000)
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be a valid http or https URL.")
        data = _json(_url("https://web.archive.org/cdx/search/cdx", {
            "url": target, "output": "json", "filter": "statuscode:200",
            "filter2": "mimetype:text/html", "collapse": "digest",
            "fl": "timestamp,original,statuscode,mimetype", "limit": limit,
        }))
        rows = []
        for line in data[1:] if isinstance(data, list) and data else []:
            if isinstance(line, list) and len(line) >= 2:
                rows.append({"timestamp": line[0], "original_url": line[1],
                             "url": "https://web.archive.org/web/" + line[0] + "/" + line[1],
                             "status": line[2] if len(line) > 2 else None,
                             "mime_type": line[3] if len(line) > 3 else None})
        return _normal_results("Internet Archive Wayback Machine", target, rows)
    return None


def _loc_search(q: str, limit: int) -> dict[str, Any]:
    data = _json(_url("https://www.loc.gov/search/", {"q": q, "fo": "json", "c": limit}))
    rows = []
    for x in data.get("results", []) or []:
        image = None
        if x.get("image_url"):
            image = x["image_url"][0] if isinstance(x["image_url"], list) and x["image_url"] else x["image_url"]
        rows.append({"title": x.get("title"), "url": x.get("id") or x.get("url"),
                     "date": x.get("date"), "description": x.get("description"),
                     "image": image, "type": x.get("original_format"), "source": "Library of Congress"})
    return _normal_results("Library of Congress", q, rows, total=data.get("pagination", {}).get("total"))


def _usgs_earthquakes(params: dict[str, list[str]], limit: int) -> dict[str, Any]:
    period = _value(params, "period", "day").lower()
    if period not in {"hour", "day", "week", "month"}:
        raise ValueError("period must be hour, day, week or month.")
    try:
        minimum = float(_value(params, "min_magnitude", "0"))
    except ValueError:
        raise ValueError("min_magnitude must be numeric.")
    if not -2 <= minimum <= 10:
        raise ValueError("min_magnitude must be between -2 and 10.")
    ago = {"hour": 1, "day": 24, "week": 24 * 7, "month": 24 * 30}[period]
    start = (datetime.now(timezone.utc) - timedelta(hours=ago)).isoformat(timespec="seconds").replace("+00:00", "Z")
    data = _json(_url("https://earthquake.usgs.gov/fdsnws/event/1/query", {
        "format": "geojson", "starttime": start, "minmagnitude": minimum,
        "orderby": "time", "limit": min(limit, 200),
    }))
    rows = []
    for feature in data.get("features", []) or []:
        p = feature.get("properties", {})
        coords = (feature.get("geometry") or {}).get("coordinates", [])
        rows.append({"id": feature.get("id"), "title": p.get("title"), "url": p.get("url"),
                     "magnitude": p.get("mag"), "place": p.get("place"),
                     "time_ms": p.get("time"), "depth_km": coords[2] if len(coords) > 2 else None,
                     "longitude": coords[0] if len(coords) > 0 else None,
                     "latitude": coords[1] if len(coords) > 1 else None,
                     "tsunami": p.get("tsunami"), "felt": p.get("felt")})
    return _normal_results("USGS Earthquake Hazards Program", period, rows, metadata=data.get("metadata", {}))


def _gbif(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/science/species":
        q = _required(params, "q")
        data = _json(_url("https://api.gbif.org/v1/species/search", {"q": q, "limit": limit}))
        rows = [{"title": x.get("scientificName"), "url": "https://www.gbif.org/species/" + str(x.get("key", "")),
                 "key": x.get("key"), "rank": x.get("rank"), "kingdom": x.get("kingdom"),
                 "phylum": x.get("phylum"), "class": x.get("class"), "order": x.get("order"),
                 "family": x.get("family"), "genus": x.get("genus"), "status": x.get("taxonomicStatus")}
                for x in data.get("results", []) or []]
        return _normal_results("GBIF", q, rows, total=data.get("count"))
    if path == "/api/science/occurrences":
        taxon_key = _required(params, "taxon_key", 30)
        if not taxon_key.isdigit():
            raise ValueError("taxon_key must be a numeric GBIF taxon key.")
        data = _json(_url("https://api.gbif.org/v1/occurrence/search", {
            "taxonKey": taxon_key, "limit": limit, "hasCoordinate": "true",
        }))
        rows = [{"key": x.get("key"), "scientific_name": x.get("scientificName"),
                 "event_date": x.get("eventDate"), "country": x.get("country"),
                 "latitude": x.get("decimalLatitude"), "longitude": x.get("decimalLongitude"),
                 "basis_of_record": x.get("basisOfRecord"),
                 "url": "https://www.gbif.org/occurrence/" + str(x.get("key", ""))}
                for x in data.get("results", []) or []]
        return _normal_results("GBIF", taxon_key, rows, total=data.get("count"))
    return None


def _spaceflight(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path not in {"/api/science/space/news", "/api/science/space/launches"}:
        return None
    if path.endswith("/news"):
        q = _required(params, "q")
        url = _url("https://api.spaceflightnewsapi.net/v4/articles/", {"search": q, "limit": limit})
        provider = "Spaceflight News API"
    else:
        q = ""
        url = _url("https://api.spaceflightnewsapi.net/v4/launches/", {"limit": limit, "ordering": "-net"})
        provider = "Spaceflight News API"
    data = _json(url)
    rows = data.get("results", []) if isinstance(data, dict) else []
    if path.endswith("/news"):
        results = [{"title": x.get("title"), "url": x.get("url"), "summary": x.get("summary"),
                    "image": x.get("image_url"), "published": x.get("published_at"),
                    "updated": x.get("updated_at"), "news_site": (x.get("news_site") or {}).get("name"),
                    "source": provider} for x in rows]
    else:
        results = [{"title": x.get("name"), "url": x.get("url"), "status": (x.get("status") or {}).get("name"),
                    "net": x.get("net"), "window_start": x.get("window_start"),
                    "window_end": x.get("window_end"), "launch_service_provider": (x.get("launch_service_provider") or {}).get("name"),
                    "source": provider} for x in rows]
    return _normal_results(provider, q, results, total=data.get("count") if isinstance(data, dict) else None)


def _itunes(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/media/itunes/search":
        term = _required(params, "term")
        entity = _value(params, "entity", "")
        allowed = {"song", "album", "musicArtist", "podcast", "ebook", "movie", "software", "audiobook", "allTrack"}
        if entity and entity not in allowed:
            raise ValueError("Unsupported iTunes entity. Choose song, album, musicArtist, podcast, ebook, movie, software, audiobook or allTrack.")
        values: dict[str, Any] = {"term": term, "limit": limit, "country": _value(params, "country", "us")}
        if entity:
            values["entity"] = entity
        data = _json(_url("https://itunes.apple.com/search", values))
        rows = [{"title": x.get("trackName") or x.get("collectionName") or x.get("artistName"),
                 "url": x.get("trackViewUrl") or x.get("collectionViewUrl") or x.get("artistViewUrl"),
                 "artist": x.get("artistName"), "album": x.get("collectionName"),
                 "kind": x.get("kind"), "genre": x.get("primaryGenreName"),
                 "release_date": x.get("releaseDate"), "artwork": x.get("artworkUrl100"),
                 "price": x.get("trackPrice"), "currency": x.get("currency"), "source": "Apple iTunes"}
                for x in data.get("results", []) or []]
        return _normal_results("Apple iTunes Search API", term, rows, total=data.get("resultCount"))
    if path == "/api/media/itunes/lookup":
        identifier = _required(params, "id", 30)
        if not identifier.isdigit():
            raise ValueError("id must be a numeric iTunes catalogue ID.")
        data = _json(_url("https://itunes.apple.com/lookup", {"id": identifier, "country": _value(params, "country", "us")}))
        return {"ok": True, "provider": "Apple iTunes Search API", "count": data.get("resultCount"),
                "results": data.get("results", [])}
    return None


def _musicbrainz(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path != "/api/media/musicbrainz/search":
        return None
    q = _required(params, "q")
    entity = _value(params, "type", "artist")
    if entity not in {"artist", "release", "recording", "release-group", "work", "label"}:
        raise ValueError("type must be artist, release, recording, release-group, work or label.")
    data = _json(_url("https://musicbrainz.org/ws/2/" + entity + "/", {
        "query": q, "fmt": "json", "limit": min(limit, 25),
    }))
    key = {"artist": "artists", "release": "releases", "recording": "recordings",
           "release-group": "release-groups", "work": "works", "label": "labels"}[entity]
    rows = []
    for x in data.get(key, []) or []:
        mbid = x.get("id")
        rows.append({"title": x.get("name") or x.get("title"), "id": mbid,
                     "url": "https://musicbrainz.org/" + entity + "/" + str(mbid),
                     "disambiguation": x.get("disambiguation"), "country": x.get("country"),
                     "date": x.get("first-release-date") or x.get("life-span", {}).get("begin"),
                     "score": x.get("score"), "source": "MusicBrainz"})
    return _normal_results("MusicBrainz", q, rows, entity=entity)


def _tvmaze(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/entertainment/tv/search":
        q = _required(params, "q")
        data = _json(_url("https://api.tvmaze.com/search/shows", {"q": q}))
        rows = []
        for item in (data or [])[:limit]:
            x = item.get("show", {})
            rows.append({"id": x.get("id"), "title": x.get("name"), "url": x.get("url"),
                         "summary": re.sub(r"<[^>]*>", " ", x.get("summary") or "").strip(),
                         "language": x.get("language"), "genres": x.get("genres", []),
                         "status": x.get("status"), "premiered": x.get("premiered"),
                         "ended": x.get("ended"), "network": (x.get("network") or {}).get("name"),
                         "image": (x.get("image") or {}).get("medium"), "score": item.get("score")})
        return _normal_results("TVmaze", q, rows)
    if path in {"/api/entertainment/tv/show", "/api/entertainment/tv/episodes"}:
        identifier = _required(params, "id", 20)
        if not identifier.isdigit():
            raise ValueError("id must be a numeric TVmaze show ID.")
        suffix = "/episodes" if path.endswith("/episodes") else ""
        data = _json("https://api.tvmaze.com/shows/" + identifier + suffix)
        if suffix:
            return _normal_results("TVmaze", identifier, [
                {"id": x.get("id"), "title": x.get("name"), "season": x.get("season"),
                 "number": x.get("number"), "airdate": x.get("airdate"), "url": x.get("url"),
                 "summary": re.sub(r"<[^>]*>", " ", x.get("summary") or "").strip()}
                for x in (data or [])[:limit]])
        return {"ok": True, "provider": "TVmaze", "result": data}
    return None


def _pokemon(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    root = "https://pokeapi.co/api/v2/"
    if path == "/api/games/pokemon/search":
        q = _required(params, "q").lower()
        data = _json(_url(root + "pokemon", {"limit": 2000}))
        rows = [{"title": x.get("name"), "name": x.get("name"), "url": x.get("url")}
                for x in data.get("results", []) if q in x.get("name", "").lower()][:limit]
        return _normal_results("PokéAPI", q, rows)
    endpoint_map = {
        "/api/games/pokemon/details": "pokemon",
        "/api/games/pokemon/ability": "ability",
        "/api/games/pokemon/type": "type",
        "/api/games/pokemon/item": "item",
    }
    if path in endpoint_map:
        name = _required(params, "name", 100).lower()
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("name contains unsupported characters.")
        data = _json(root + endpoint_map[path] + "/" + urllib.parse.quote(name, safe=""))
        if path.endswith("/details"):
            data = {"id": data.get("id"), "name": data.get("name"),
                    "height": data.get("height"), "weight": data.get("weight"),
                    "base_experience": data.get("base_experience"),
                    "types": [x.get("type", {}).get("name") for x in data.get("types", [])],
                    "abilities": [x.get("ability", {}).get("name") for x in data.get("abilities", [])],
                    "stats": [{"name": x.get("stat", {}).get("name"), "base_stat": x.get("base_stat")}
                              for x in data.get("stats", [])],
                    "sprites": data.get("sprites", {}).get("front_default")}
        return {"ok": True, "provider": "PokéAPI", "result": data}
    return None


def _food(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    base = "https://world.openfoodfacts.org"
    if path == "/api/food/search":
        q = _required(params, "q")
        data = _json(_url(base + "/cgi/search.pl", {
            "search_terms": q, "search_simple": 1, "action": "process", "json": 1, "page_size": limit,
            "fields": "code,product_name,brands,categories,countries,ingredients_text,nutriscore_grade,nova_group,image_front_url",
        }), headers={"User-Agent": USER_AGENT})
        rows = [{"title": x.get("product_name"), "url": "https://world.openfoodfacts.org/product/" + str(x.get("code", "")),
                 "barcode": x.get("code"), "brands": x.get("brands"), "categories": x.get("categories"),
                 "countries": x.get("countries"), "ingredients": x.get("ingredients_text"),
                 "nutriscore": x.get("nutriscore_grade"), "nova_group": x.get("nova_group"),
                 "image": x.get("image_front_url"), "source": "Open Food Facts"}
                for x in data.get("products", []) or []]
        return _normal_results("Open Food Facts", q, rows, total=data.get("count"))
    if path == "/api/food/product":
        barcode = _required(params, "barcode", 32)
        if not re.fullmatch(r"[0-9]{6,14}", barcode):
            raise ValueError("barcode must contain 6 to 14 digits.")
        fields = "code,product_name,brands,categories,countries,ingredients_text,nutriscore_grade,nova_group,nutriments,allergens,image_front_url"
        data = _json(_url(base + "/api/v2/product/" + barcode, {"fields": fields}))
        if data.get("status") != 1 or not data.get("product"):
            return {"ok": True, "provider": "Open Food Facts", "found": False, "barcode": barcode, "product": None}
        return {"ok": True, "provider": "Open Food Facts", "found": True,
                "barcode": barcode, "product": data.get("product"),
                "note": "Crowdsourced label data can be incomplete or inaccurate; not medical or dietary advice."}
    return None


def _worldbank(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    base = "https://api.worldbank.org/v2"
    if path == "/api/economy/worldbank/countries":
        q = _value(params, "q").lower()
        data = _json(_url(base + "/country", {"format": "json", "per_page": 300}))
        rows = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
        output = []
        for x in rows:
            name = (x.get("name") or "").lower()
            code = (x.get("id") or "").lower()
            if not q or q in name or q == code or q in (x.get("capitalCity") or "").lower():
                output.append({"code": x.get("id"), "iso2": x.get("iso2Code"), "title": x.get("name"),
                               "region": (x.get("region") or {}).get("value"),
                               "income_level": (x.get("incomeLevel") or {}).get("value"),
                               "capital": x.get("capitalCity"), "latitude": x.get("latitude"),
                               "longitude": x.get("longitude"), "url": "https://data.worldbank.org/country/" + str(x.get("id", ""))})
        return _normal_results("World Bank", q, output[:limit])
    if path == "/api/economy/worldbank/indicator":
        country = _value(params, "country", "IND").upper()
        indicator = _value(params, "indicator", "NY.GDP.MKTP.CD")
        if not re.fullmatch(r"[A-Z0-9]{2,3}", country):
            raise ValueError("country must be an ISO or World Bank country code.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{2,80}", indicator):
            raise ValueError("indicator contains unsupported characters.")
        date_range = _value(params, "date", "")
        if date_range and not re.fullmatch(r"\d{4}(?::\d{4})?", date_range):
            raise ValueError("date must be YYYY or YYYY:YYYY.")
        values: dict[str, Any] = {"format": "json", "per_page": min(limit, 100)}
        if date_range:
            values["date"] = date_range
        data = _json(_url(base + "/country/" + country + "/indicator/" + indicator, values))
        rows = []
        if isinstance(data, list) and len(data) > 1:
            for x in data[1] or []:
                rows.append({"country": (x.get("country") or {}).get("value"),
                             "country_code": (x.get("country") or {}).get("id"),
                             "indicator": (x.get("indicator") or {}).get("value"),
                             "indicator_code": indicator, "year": x.get("date"), "value": x.get("value"),
                             "unit": x.get("unit"), "source": "World Bank"})
        return _normal_results("World Bank", country + ":" + indicator, rows)
    if path == "/api/economy/worldbank/indicators":
        q = _required(params, "q")
        data = _json(_url(base + "/indicator", {"format": "json", "per_page": 200}))
        rows = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
        selected = [x for x in rows if q.casefold() in (x.get("name") or "").casefold()
                    or q.casefold() in (x.get("id") or "").casefold()]
        return _normal_results("World Bank", q, [
            {"title": x.get("name"), "id": x.get("id"), "url": "https://data.worldbank.org/indicator/" + str(x.get("id", "")),
             "source": (x.get("source") or {}).get("value"), "topics": [t.get("value") for t in x.get("topics", [])]}
            for x in selected[:limit]])
    return None


def _network(path: str, params: dict[str, list[str]], limit: int) -> dict[str, Any] | None:
    if path == "/api/network/dns":
        name = _domain(params, "name")
        record_type = _value(params, "type", "A").upper()
        allowed = {"A", "AAAA", "CNAME", "MX", "NS", "TXT", "CAA", "SOA", "HTTPS", "SVCB"}
        if record_type not in allowed:
            raise ValueError("Unsupported DNS record type.")
        data = _json(_url("https://cloudflare-dns.com/dns-query", {"name": name, "type": record_type}),
                     headers={"Accept": "application/dns-json"})
        return {"ok": True, "provider": "Cloudflare DNS over HTTPS", "name": name,
                "type": record_type, "status": data.get("Status"),
                "records": [{"name": x.get("name"), "type": x.get("type"),
                             "ttl": x.get("TTL"), "data": x.get("data")} for x in data.get("Answer", []) or []],
                "authority": data.get("Authority", [])}
    if path == "/api/network/domain":
        name = _domain(params, "name")
        data = _json("https://rdap.org/domain/" + urllib.parse.quote(name, safe=""))
        events = [{"action": x.get("eventAction"), "date": x.get("eventDate")} for x in data.get("events", []) or []]
        nameservers = [x.get("ldhName") for x in data.get("nameservers", []) or []]
        registrar = None
        for entity in data.get("entities", []) or []:
            vcard = entity.get("vcardArray", [])
            if "registrar" not in entity.get("roles", []) or len(vcard) < 2:
                continue
            for field in vcard[1] or []:
                if isinstance(field, list) and len(field) >= 4 and field[0] == "fn":
                    registrar = field[3]
                    break
            if registrar:
                break
        return {"ok": True, "provider": "RDAP", "domain": name, "handle": data.get("handle"),
                "status": data.get("status", []), "events": events, "nameservers": nameservers,
                "registrar": registrar}
    if path == "/api/network/certificates":
        name = _domain(params, "domain")
        data = _json(_url("https://crt.sh/", {"q": "%." + name, "output": "json"}), max_bytes=2_000_000)
        seen: set[str] = set()
        rows = []
        for x in (data or []):
            key = str(x.get("id") or "")
            if key in seen:
                continue
            seen.add(key)
            rows.append({"id": x.get("id"), "common_name": x.get("common_name"),
                         "name_value": x.get("name_value"), "issuer": x.get("issuer_name"),
                         "not_before": x.get("not_before"), "not_after": x.get("not_after"),
                         "url": "https://crt.sh/?id=" + key})
            if len(rows) >= limit:
                break
        return _normal_results("crt.sh Certificate Transparency", name, rows)
    return None


def handle_extra_api(path: str, params: dict[str, list[str]]) -> tuple[int, dict[str, Any]] | None:
    """Handle expanded API paths. Returns None for paths owned by other modules."""
    limit = _int_param(params, "limit", 10, 50)
    try:
        if path.startswith("/api/scholarly/openalex/"):
            entity = path.rsplit("/", 1)[-1]
            if entity == "work":
                identifier = _required(params, "id", 120).strip()
                identifier = identifier.removeprefix("https://openalex.org/")
                if not re.fullmatch(r"W[1-9][0-9]*", identifier):
                    raise ValueError("id must be an OpenAlex work ID such as W2741809807.")
                return 200, {"ok": True, "provider": "OpenAlex", "result":
                             _json("https://api.openalex.org/works/" + identifier)}
            q = _required(params, "q")
            return 200, _openalex(entity, q, min(limit, 25))
        if path.startswith("/api/scholarly/crossref/"):
            entity = path.rsplit("/", 1)[-1]
            if entity == "doi":
                doi = _required(params, "doi", 300).removeprefix("https://doi.org/").removeprefix("http://doi.org/")
                if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
                    raise ValueError("doi must look like 10.xxxx/identifier.")
                data = _json("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""))
                return 200, {"ok": True, "provider": "Crossref", "result": data.get("message", {})}
            return 200, _crossref(entity, _required(params, "q"), min(limit, 20))
        if path == "/api/scholarly/europepmc":
            return 200, _europepmc(_required(params, "q"), min(limit, 25))
        if path == "/api/scholarly/europepmc/article":
            identifier = _required(params, "id", 200)
            if not re.fullmatch(r"(?:PMC[0-9]+|[0-9]+|10\.\d{4,9}/\S+)", identifier, re.I):
                raise ValueError("id must be a PMID, PMCID or DOI.")
            query = "EXT_ID:" + identifier
            payload = _europepmc(query, 1)
            return 200, {"ok": True, "provider": "Europe PMC", "query": query,
                         "found": bool(payload["results"]), "results": payload["results"]}
        if path == "/api/health/clinicaltrials":
            return 200, _clinical_trials(_required(params, "q"), min(limit, 20))
        if path == "/api/health/clinicaltrials/study":
            nct = _required(params, "nct", 30).upper()
            if not re.fullmatch(r"NCT\d{8}", nct):
                raise ValueError("nct must look like NCT01234567.")
            data = _json("https://clinicaltrials.gov/api/v2/studies/" + nct)
            return 200, {"ok": True, "provider": "ClinicalTrials.gov", "result": data}
        if path == "/api/health/openfda/datasets":
            return 200, {"ok": True, "provider": "openFDA",
                         "datasets": [{"id": k, "route": "/api/health/openfda?dataset=" + k + "&q=...",
                                       "api_path": "/" + "/".join(v) + ".json"} for k, v in FDA_DATASETS.items()],
                         "note": "Public regulatory data; records may be incomplete and are not medical advice."}
        if path == "/api/health/openfda":
            dataset = _value(params, "dataset", "drug-label")
            return 200, _openfda(dataset, _value(params, "q"), min(limit, 20))
        if path == "/api/education/trivia":
            return 200, _trivia(params)
        if path in {"/api/education/dictionary", "/api/education/synonyms", "/api/education/antonyms"}:
            word = _required(params, "word", 80)
            data = _dictionary(word)
            if path.endswith("/synonyms"):
                return 200, {"ok": True, "provider": data["provider"], "word": word, "synonyms": data["synonyms"]}
            if path.endswith("/antonyms"):
                return 200, {"ok": True, "provider": data["provider"], "word": word, "antonyms": data["antonyms"]}
            return 200, data

        github = _github_api(path, params, min(limit, 30))
        if github is not None:
            return 200, github
        gitlab = _gitlab(path, params, min(limit, 30))
        if gitlab is not None:
            return 200, gitlab
        stack = _stackoverflow(path, params, min(limit, 30))
        if stack is not None:
            return 200, stack
        hf = _huggingface(path, params, min(limit, 30))
        if hf is not None:
            return 200, hf
        packages = _packages(path, params, min(limit, 20))
        if packages is not None:
            return 200, packages
        wiki = _wikipedia(path, params, min(limit, 50))
        if wiki is not None:
            return 200, wiki
        archives = _archives(path, params, min(limit, 25))
        if archives is not None:
            return 200, archives
        if path == "/api/open-data/library-of-congress/search":
            return 200, _loc_search(_required(params, "q"), min(limit, 30))
        if path == "/api/science/earthquakes":
            return 200, _usgs_earthquakes(params, min(limit, 200))
        gbif = _gbif(path, params, min(limit, 25))
        if gbif is not None:
            return 200, gbif
        space = _spaceflight(path, params, min(limit, 20))
        if space is not None:
            return 200, space
        itunes = _itunes(path, params, min(limit, 50))
        if itunes is not None:
            return 200, itunes
        music = _musicbrainz(path, params, min(limit, 25))
        if music is not None:
            return 200, music
        tv = _tvmaze(path, params, min(limit, 50))
        if tv is not None:
            return 200, tv
        pokemon = _pokemon(path, params, min(limit, 50))
        if pokemon is not None:
            return 200, pokemon
        food = _food(path, params, min(limit, 20))
        if food is not None:
            return 200, food
        worldbank = _worldbank(path, params, min(limit, 50))
        if worldbank is not None:
            return 200, worldbank
        network = _network(path, params, min(limit, 20))
        if network is not None:
            return 200, network
        return None
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except urllib.error.HTTPError as exc:
        status = 404 if exc.code == 404 else (429 if exc.code == 429 else 502)
        return status, {"ok": False, "error": "Public provider returned an HTTP error.",
                        "provider_status": exc.code, "provider": urllib.parse.urlsplit(exc.url).hostname if exc.url else None}
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return 502, {"ok": False, "error": "Public provider request failed.",
                     "detail": type(exc).__name__}
    except Exception as exc:
        return 502, {"ok": False, "error": "Expanded API request failed.",
                     "detail": type(exc).__name__}
