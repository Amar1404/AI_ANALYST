---
name: business-context
description: >
  Interactive browser for your organization's knowledge system. Explore terms,
  products, metrics, objectives, and team structure. Also crawl Notion workspaces
  to extract and populate business context. Triggered when users say "/business",
  "browse business context", "/notion-ingest", or "crawl notion workspace".
---

# Skill: Business Context Browser

> Interactive browser for your organization's knowledge system. Explore terms,
> products, metrics, objectives, and team structure. Also optionally crawl Notion
> workspaces to extract and populate business context.

## Trigger
Invoked as `/business` or `/business {subcommand}` or `/notion-ingest`

## Prerequisites
- Organization context must exist at `<workspace>/knowledge/organizations/{org}/`
- Read `<workspace>/knowledge/setup-state.yaml` to find active organization
- If no org configured: "No organization context found. Run `/setup` Phase 3 to configure business context, or create one manually at `<workspace>/knowledge/organizations/{name}/`."

## Subcommands

### `/business` (no args) — Overview
Display a summary of available business context:

```
Business Context: {org_name}

  Glossary:    {n} terms defined
  Products:    {n} products cataloged
  Metrics:     {n} metrics specified
  Objectives:  {n} OKRs/goals tracked
  Teams:       {n} teams mapped

Type /business {category} for details.
```

**Implementation:**
1. Read `<workspace>/knowledge/organizations/{org}/manifest.yaml` for org name
2. Use `helpers/business_context.py` → `load_business_context(org_path)`
3. Count entries in each category
4. Display summary table

### `/business glossary` — Browse Terms
Display all business term definitions:

```
Glossary ({n} terms)

  Term              | Definition                          | Category
  ──────────────────|─────────────────────────────────────|──────────
  Active User       | User with ≥1 session in last 30d    | Engagement
  Churn             | No activity for 60+ days            | Retention
  ...
```

**Implementation:**
1. Load from `business/glossary/terms.yaml`
2. Sort alphabetically
3. Show first 20 terms; offer "Show all" if more
4. If empty: "No glossary terms defined. Add terms to `<workspace>/knowledge/organizations/{org}/business/glossary/terms.yaml`."

### `/business products` — View Product Catalog
Display product hierarchy:

```
Products ({n} total)

  Product           | Category    | Status    | Key Metrics
  ──────────────────|─────────────|───────────|────────────
  Core Platform     | SaaS        | Active    | MAU, Revenue
  Mobile App        | Mobile      | Active    | DAU, Retention
  ...
```

**Implementation:**
1. Load from `business/products/index.yaml`
2. Display in table format
3. If empty: "No products defined. Add products to `<workspace>/knowledge/organizations/{org}/business/products/index.yaml`."

### `/business metrics` — Inspect Metric Definitions
Display metric dictionary:

```
Metrics ({n} defined)

  Metric            | Type        | Formula/Definition        | Owner
  ──────────────────|─────────────|───────────────────────────|──────
  Conversion Rate   | Ratio       | signups / visitors        | Growth
  MRR               | Currency    | SUM(active_subscriptions) | Finance
  ...
```

**Implementation:**
1. Load from `business/metrics/index.yaml`
2. Cross-reference with `<workspace>/knowledge/datasets/{active}/metrics/` if available
3. Show definition, type, owner
4. If empty: "No metrics defined. Use `/metrics add` to define metrics, or add to `<workspace>/knowledge/organizations/{org}/business/metrics/index.yaml`."

### `/business objectives` — Review OKRs/Goals
Display current objectives:

```
Objectives ({n} active)

  Objective                      | Key Results              | Status
  ───────────────────────────────|──────────────────────────|────────
  Increase activation rate       | +15% by Q2               | On Track
  Reduce churn                   | <5% monthly by Q3        | At Risk
  ...
```

**Implementation:**
1. Load from `business/objectives/index.yaml`
2. Show status indicators (On Track / At Risk / Behind)
3. If empty: "No objectives defined. Add OKRs to `<workspace>/knowledge/organizations/{org}/business/objectives/index.yaml`."

### `/business teams` — Show Team Structure
Display team organization:

```
Teams ({n} mapped)

  Team              | Lead        | Focus Area        | Analysts
  ──────────────────|─────────────|───────────────────|──────────
  Growth            | Jane D.     | Acquisition       | 2
  Product           | John S.     | Core Experience   | 3
  ...
```

**Implementation:**
1. Load from `business/teams/index.yaml`
2. Show team summary
3. If empty: "No teams defined. Add team structure to `<workspace>/knowledge/organizations/{org}/business/teams/index.yaml`."

### `/business lookup {term}` — Search
Search across all categories for a term:

1. Search glossary terms (exact + fuzzy match)
2. Search product names
3. Search metric names
4. Search objective text
5. Display all matches with category labels

If no match: "No results for '{term}'. Try a different search term or browse categories with `/business`."

**Implementation:**
1. Use `helpers/business_context.py` → `get_glossary()`, `get_products()`, etc.
2. Case-insensitive substring match across all categories
3. Rank: exact match > starts-with > contains
4. Show top 10 results with category badge

## Notion Integration (`/notion-ingest`)

### Overview

This skill uses a breadth-first crawl strategy to systematically traverse a Notion
workspace, converting pages to structured knowledge entries. It does NOT require
external Python packages — all Notion API calls use inline HTTP requests.

### Step 1: Authentication Check

```python
import yaml, os

# Load integration config
integrations_path = "<workspace>/knowledge/user/integrations.yaml"
with open(integrations_path) as f:
    config = yaml.safe_load(f)

notion_token = config.get("notion", {}).get("token")
if not notion_token:
    print("No Notion token found. Add to <workspace>/knowledge/user/integrations.yaml")
    # HALT
```

Verify token works with a simple API call:
```
GET https://api.notion.com/v1/users/me
Authorization: Bearer {token}
Notion-Version: 2022-06-28
```

### Step 2: Workspace Discovery

Ask the user for crawl scope:
```
Notion workspace connected. How would you like to crawl?

1. **Full workspace** — Crawl all accessible pages (may be slow for large workspaces)
2. **Specific database** — Provide a database URL to crawl
3. **Specific page tree** — Provide a root page URL to crawl its children
4. **Search by keyword** — Search for pages matching specific terms
```

### Step 3: BFS Crawl Strategy

```
Algorithm: Breadth-First Search (BFS)

Queue ← [root_page_id]
Visited ← {}
Results ← []

WHILE Queue is not empty:
    page_id ← Queue.dequeue()
    IF page_id IN Visited: CONTINUE
    Visited.add(page_id)

    page ← fetch_page(page_id)        # GET /v1/pages/{id}
    children ← fetch_children(page_id) # GET /v1/blocks/{id}/children

    result ← convert_to_knowledge(page, children)
    Results.append(result)

    # Enqueue child pages and linked databases
    FOR child IN children:
        IF child.type == "child_page" OR child.type == "child_database":
            Queue.enqueue(child.id)

    rate_limit_pause()  # See Step 4
```

### Step 4: Rate Limiting

Notion API limits: 3 requests per second for integration tokens.

**Backoff strategy:**
- On 429 (rate limited): wait `Retry-After` header seconds, minimum 1s
- On 5xx: exponential backoff (1s, 2s, 4s), max 3 retries
- On 4xx (not 429): log error, skip page, continue crawl

### Step 5: Page-to-Markdown Conversion

Convert Notion block types to markdown:

| Notion Block Type | Markdown Output |
|-------------------|-----------------|
| paragraph | Plain text |
| heading_1 | `# Title` |
| heading_2 | `## Title` |
| heading_3 | `### Title` |
| bulleted_list_item | `- Item` |
| numbered_list_item | `1. Item` |
| code | ` ```lang\ncode\n``` ` |
| quote | `> Quote` |
| callout | `> ℹ️ Callout` |
| table | Markdown table |
| divider | `---` |
| toggle | Treat as heading + nested content |
| child_page | `[Page Title](notion://page_id)` |
| child_database | `[Database Title](notion://db_id)` |

### Step 6: Knowledge Extraction

For each crawled page, attempt to classify and extract structured knowledge:

### Auto-Classification Rules
| Page Contains | Classification | Target File |
|---------------|---------------|-------------|
| Term definitions, glossary entries | Glossary term | `business/glossary/terms.yaml` |
| KPI, metric, formula | Metric definition | `business/metrics/index.yaml` |
| Product name, feature list | Product entry | `business/products/index.yaml` |
| OKR, objective, key result | Objective | `business/objectives/index.yaml` |
| Team name, org chart | Team entry | `business/teams/index.yaml` |
| SQL query, data pattern | Query archaeology | `<workspace>/knowledge/query-archaeology/raw/` |

### Step 7: Progress Reporting

During crawl, show progress:
```
Crawling Notion workspace...

  Pages crawled:    45/~120 (estimated)
  Terms extracted:  12
  Metrics found:    5
  Products found:   3
  Errors:           1 (skipped)

  Current: "Q4 2025 OKR Tracker"
```

### Step 8: Post-Crawl Summary

After crawl completes:
```
Notion ingest complete!

  Pages crawled:     127
  Pages skipped:     3 (errors logged)

  Knowledge extracted:
    Glossary terms:  23 → business/glossary/terms.yaml
    Metrics:         8  → business/metrics/index.yaml
    Products:        5  → business/products/index.yaml
    Objectives:      12 → business/objectives/index.yaml
    Teams:           4  → business/teams/index.yaml

  Raw pages saved:   127 → <workspace>/knowledge/query-archaeology/raw/

  Review extracted knowledge with `/business` to verify accuracy.
```

## Error Handling
- Missing org directory → suggest `/setup` Phase 3
- Empty categories → show helpful "how to add" message with file path
- Malformed YAML → show parse error, suggest checking file syntax
- Partial context (some categories empty) → show what exists, note gaps
- Invalid Notion token → "Notion token is invalid or expired. Update in `<workspace>/knowledge/user/integrations.yaml`."
- Permission denied (403) → "Cannot access page '{title}'. Check integration permissions in Notion."

## Display Rules
- Use tables for structured data (align columns)
- Limit initial display to 20 rows; offer pagination
- Always show file paths so users know where to edit
- Adapt detail level: summary for `/business`, detail for subcommands
