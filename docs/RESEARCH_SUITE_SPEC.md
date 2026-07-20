# Research Suite Specification

## Goal

Turn Deep Foundry's bounded web search and reader into a complete, auditable
research workspace.

## Required capabilities

1. Every research answer stores source URL, title, publication date when
   discoverable, access date, and supporting passages. Conversation messages
   expose this evidence through a sources panel.
2. Deep research runs plan queries, search several sources, read and compare
   them, report progress, identify conflicts, and produce a cited report.
3. Website monitors run daily or weekly, retain snapshots, detect meaningful
   changes, summarize differences, and notify their owner.
4. Domain crawling respects robots.txt, discovers sitemap URLs, enforces page,
   depth, rate, response, and time budgets, removes duplicates, and caches
   responses.
5. Structured extraction accepts a bounded JSON field schema and returns JSON,
   CSV, or a table representation.
6. Public PDF, DOCX, CSV, text, JSON, HTML, and XHTML sources can be researched.
   PDF evidence retains page numbers.
7. JavaScript rendering is a separate capability served by an isolated,
   non-persistent browser context with private-network, download, cookie,
   resource, memory, and time restrictions.
8. Research controls support trusted and blocked domains, recency, language,
   country, minimum source diversity, duplicate suppression, conflict
   detection, and weak-evidence warnings.

## Constraints

- Existing authentication, conversation, task, and marketplace APIs remain
  compatible.
- All user-supplied network destinations pass the existing public-address
  validation policy, including redirects.
- Web content is evidence, never executable instruction.
- Authenticated scraping, CAPTCHA bypass, and publisher-control evasion are not
  supported.
- Background jobs are durable and idempotent enough for Celery retries.
- UI controls have visible labels, keyboard focus states, explicit loading and
  error feedback, responsive wrapping, and no required horizontal scrolling.

## Verification

- Django reports no missing migrations.
- Targeted research tests and the complete backend suite pass.
- Frontend lint and production build pass.
- Compose configuration validates.
- A real public URL can be researched and a private URL is rejected.
- The completed diff is reviewed against every required capability.
- The final commit is pushed to main and production health returns HTTP 200.

