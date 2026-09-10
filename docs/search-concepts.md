# Search model and design choices

The product objective is general-purpose Web search. The current implementation
uses BM25 and source-aware rules; those mechanisms do not define the full scope
of the product or establish that its search quality is sufficient.

## Terms used in design discussions

| Term | Meaning in this project |
|---|---|
| Query | The observable input, which is evidence about what the user wants |
| Intent | The immediate information need inferred from that input |
| Purpose | The broader task behind a search; it need not be observable to the engine |
| Target | The page or resource that could satisfy the information need |
| Representation | The stored text, analyzed terms, or other features used to retrieve and assess a target |
| Retrieval | Selecting the candidate set that ranking can operate on |
| Scoring / ranking | Assessing candidates / ordering them for presentation |
| Signal / policy | Evidence about a candidate / the rules for combining that evidence |

These distinctions prevent implementation choices from being mistaken for the
user's goal. For example, a canonical-domain match is one source-fit signal;
it does not by itself establish that a page answers the query.

## Boundaries to preserve

- A missing useful page can be a coverage, representation, or retrieval problem.
  Reordering the existing candidates cannot recover a page outside that set.
- A retrieved page can still be poorly ranked. Diagnose candidate availability
  before changing ordering rules.
- Presentation and telemetry do not belong in candidate retrieval. This lets
  HTML, API, and offline callers use the same search engine.

The first two points distinguish failure types; they are not claims that the
current classifier, rules, or evaluation judgments are correct.

## Choices that remain open

Keeping signals understandable and independently changeable is a maintenance
preference. It is not evidence that hand-written rules outperform learned
retrieval or ranking.

Vector retrieval is not currently in the serving path. Whether to add it, use
a hybrid, or keep BM25 alone remains an empirical quality/cost decision. This
conceptual model does not require vectors to be merely a supplement or require
more manual rules before that comparison.

`search-ranking-policy.md` describes the implementation; `search-evaluation.md`
describes what its current evaluation can and cannot establish.
