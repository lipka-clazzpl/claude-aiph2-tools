# Plan: Wikipedia Knowledge Branches — rozszerzanie i rozgałęzianie konceptów (learn + review)

## Task Description

Wpięcie Wikipedii w przebieg agenta tak, aby **rozszerzała koncepty** (definicja, kontekst historyczny, mechanizm) i **pokazywała rozgałęzienia wiedzy** (powiązane hasła, branże, dyscypliny pokrewne) — w **dwóch trybach pracy**:

1. **Podczas nauki** (`/learn`, `/learn-file`, `/learn-quest`, `/learn-web`) — po doprowadzeniu konceptu do końca, ale **przed** zapisem karty: agent sięga po Wikipedię, destyluje 2-3 sąsiednie hasła i wzbogaca sekcje `Szersza perspektywa` + `Powiązane`. Dzięki temu karta nie jest izolowanym pojęciem, tylko węzłem w mapie.
2. **Podczas review** (`/review`) — po ocenie karty (grade ≥ 3): agent oferuje 2-3 *gałęzie do dalszej eksploracji* na bazie zapisanych w karcie `wikipedia_branches`. Po lapsie (grade ≤ 2) — pokazuje **inny kąt** z Wikipedii jako mnemonik wzmacniający, zamiast tylko prosić o ponowne przeczytanie karty.

Mechanizm: nowa MCP tool `wikipedia_lookup`, opakowanie REST API (`pl.wikipedia.org` z fallbackiem na `en.wikipedia.org`), drobne rozszerzenie schematu karty (`wikipedia_branches` w frontmatter + sekcja `## Powiązane (Wikipedia)` w body), oraz aktualizacja czterech promptów określająca kiedy/jak po nią sięgać.

## Objective

Po wdrożeniu:

- Agent po wyjaśnieniu konceptu (np. "Customer Curiosity", "Jobs To Be Done", "Lean Startup") **automatycznie** wywołuje `wikipedia_lookup` i wykorzystuje wynik do bogatszej sekcji `Szersza perspektywa` ORAZ do listy 2-3 *gałęzi* w `Powiązane (Wikipedia)`. Każda gałąź to `{title, url, one-line summary}`.
- Karta zapisana przez `add_card_full` nosi te gałęzie w frontmatter (pole `wikipedia_branches`), więc są dostępne przy powtórce nawet po latach.
- W `/review` po ocenie ≥ 3 agent pyta: *"Karta zna 3 gałęzie: Lean Startup, Continuous Discovery, JTBD. Chcesz zobaczyć którąś z nich teraz?"* — i jeśli tak, robi krótki *side-question* (z zapisem osobnej karty `type='wikipedia-branch'`).
- Po grade ≤ 2 (zapomnienie) agent zamiast samej re-prezentacji karty pokazuje **alternatywny kąt** z Wikipedii (jeśli `wikipedia_branches` ma wpisy) — to **inny element review**, mnemonik o niezależnej trasie aktywacji.
- Polityka źródeł: Wikipedia jest **oznaczona** jako uzupełnienie, **nigdy** nie zastępuje `source_quote` z materiałów AIPH2. Ranga zaufania: transkrypt > slajdy > Wikipedia > wyszukiwarka.
- Polish-first: agent najpierw próbuje `pl.wikipedia.org`, fallback na `en.wikipedia.org` gdy hasło nie istnieje lub stub. URL i tytuł zawsze w wyniku, dla weryfikacji.

## Problem Statement

Trzy konkretne luki w obecnym agencie:

**1. Karty są wyspami.** Sekcja `Szersza perspektywa` w SYSTEM_PROMPT (Zasada 4) prosi o porównanie z Lean Startup / JTBD / Continuous Discovery / Working Backwards — ale agent zna te ramy tylko z own training data. Bez świeżego źródła karty są pisane "z głowy", a użytkownik nie wie, gdzie pójść po więcej. SuperMemo IL traktuje karty jak węzły grafu wiedzy, nie atomy — bez gałęzi graf się nie składa.

**2. /review nie eksploruje.** Po poprawnej odpowiedzi agent tylko mówi *"Świetnie, następna powtórka za N dni"* i kończy. Nie ma momentu *zaproszenia do drążenia* — czas, w którym mózg już aktywował koncept, jest najlepszy do dokładania powiązań ("memory consolidation window"). Marnujemy go.

**3. Lapsy są mechaniczne.** Karta z grade 0-2 wraca jutro **tym samym kanałem**. Element review w karcie jest jeden, statyczny. Po drugim lapsie tej samej karty użytkownik utyka. Wikipedia daje *innego seeda*: zamiast tej samej definicji znów, prezentujemy hasło sąsiednie, które aktywuje koncept od drugiej strony.

**4. Brak przyciętej polityki dla halucynacji.** Agent ma `WebSearch` i `WebFetch` w `allowed_tools`, ale prompt nie mówi *kiedy* po nie sięgać. W praktyce model woli odpowiadać z own knowledge i czasem konfabuluje. Wikipedia to twardy referent — **publiczna, datowana, ze źródłami**. Wpisanie jej jako preferowanego pierwszego ruchu dla "rozszerz koncept" zmniejsza zmyślanie.

## Solution Approach

### Wysokopoziomowo

```
            ┌────────────────────────────────────────────────────┐
            │ Pętla nauczania konceptu (LEARN_QUEST / LEARN_FILE)│
            └────────────────────────────────────────────────────┘
                                       │
   ... 1.intuicja → 2.definicja → 3.konkret → 4.why/tradeoff/pitfall
                                       │
                                       ▼
                       ┌─────────────────────────────────┐
                       │  NOWY KROK 4.5 — Wikipedia      │
                       │  wikipedia_lookup(title=..)     │
                       │  → summary + 2-3 related        │
                       └─────────────────────────────────┘
                                       │
                                       ▼
                            5. Szersza perspektywa
                              (wzmocnione gałęziami)
                                       │
                                       ▼
                            6. Pytanie sprawdzające
                                       │
                                       ▼
                            7. add_card_full
                              (wikipedia_branches w frontmatter,
                               sekcja "Powiązane (Wikipedia)" w body)


            ┌────────────────────────────────────────────────────┐
            │ Pętla powtórki (REVIEW_SESSION)                    │
            └────────────────────────────────────────────────────┘
        ... pokaż przód → użytkownik → tył → record_review
                                       │
                          ┌────────────┴───────────────┐
                          │                            │
                  grade ≥ 3 (pamięta)         grade ≤ 2 (zapomnienie)
                          │                            │
                          ▼                            ▼
              "Chcesz zobaczyć gałąź:        Pokaż gałąź jako mnemonik
              X / Y / Z?" (z karty)          (inny kąt, nie ta sama karta)
                          │                            │
                tak → side-question           interval reset (jak teraz)
                karta type='wikipedia-branch'
                z cytatem z Wikipedii (URL),
                runda dialogu, pytanie sprawdz.
```

### Wikipedia jako źródło — polityka

- **Pierwszeństwo**: zawsze `pl.wikipedia.org` (mentalny model użytkownika jest polski). Fallback `en.wikipedia.org` jeśli (a) brak hasła w PL, (b) hasło PL to stub (< 500 znaków), (c) użytkownik wprost prosi o EN.
- **Kąt wykorzystania**: TYLKO sekcje `Szersza perspektywa` i `Powiązane (Wikipedia)`. **NIGDY** w `Sedno`, `Konkret`, `Source quote`, `Pytanie sprawdzające` — te muszą pochodzić z materiałów kursu.
- **Cytowanie**: każda gałąź pokazana użytkownikowi MUSI mieć URL. W karcie zapisujemy `wikipedia_branches: [{title, url, summary}]` w frontmatter — review może je później odzyskać.
- **Nie halucynuj**: jeśli `wikipedia_lookup` zwrócił pustkę / 404 — agent wprost mówi *"Wikipedia nie ma tego hasła"* i przechodzi dalej **bez** zmyślania gałęzi.

### Schemat tool — `wikipedia_lookup`

API Wikipedii (REST v1, anonimowe, brak limitu):
- `GET /api/rest_v1/page/summary/{title}` → `{title, extract, content_urls.desktop.page, ...}` (definicja + first paragraph + URL)
- `GET /api/rest_v1/page/related/{title}` → `{pages: [{title, extract, ...}]}` (haseł "See also", do 20)

Wrapper:

```python
async def wikipedia_lookup(args) -> dict:
    """
    args:
      title: str — hasło do wyszukania (po polsku albo angielsku)
      lang: 'pl' | 'en' | 'auto' (default 'auto' — pl→en fallback)
      branches: int (default 3, max 8)
      mode: 'full' | 'summary-only' | 'branches-only' (default 'full')

    returns:
      ok: {summary: {title, url, extract, lang}, branches: [{title, url, summary, lang}], notes: str}
      err: {is_error: True, content: [...]}
    """
```

Caps: extract ≤ 1500 chars, każdy branch summary ≤ 300 chars, łącznie ≤ 6000 chars w odpowiedzi tool. To zostawia kontekst dla wszystkiego innego.

Cache: in-memory dict `_WIKI_CACHE: dict[(lang,title), result]` z TTL 1h. Sesja typowo używa tego samego konceptu kilka razy (raz przy nauce, raz przy review-branch). Cache ratuje od 4-5 wywołań na sesję.

### Schema karty — minimalne rozszerzenie

`RoundCard` (modules/models.py):
```python
wikipedia_branches: list[dict] = Field(default_factory=list)
# każdy dict: {"title": str, "url": str, "summary": str, "lang": "pl"|"en"}
```

`build_body` (modules/card_io.py) — dodaje **opcjonalną** sekcję `## Powiązane (Wikipedia)` po `## Powiązane karty`. Renderuje `- [Title](url) — summary`. Jeśli lista pusta → sekcja w ogóle nie jest renderowana (nie marnujemy linii `_(brak)_`).

`add_card_full` (modules/tools.py) — nowy parametr `wikipedia_branches: str` (JSON-encoded list, bo MCP schema zwykle string). Walidacja: jeśli niepusty, parsujemy JSON, każdy element musi mieć `title` + `url`.

Frontmatter: pole `wikipedia_branches` jako lista YAML. Indeks (sm2.export_index) rzutuje na string przy serializacji index.json — bez zmiany schematu indeksu.

### Allowed tools + REPL

`learn_agent.py` — dodać `"mcp__learning__wikipedia_lookup"` do `allowed_tools`. Help text dostaje wzmiankę. Opcjonalnie nowa komenda `/wiki <hasło>` — manualne sprawdzenie hasła bez wchodzenia w pełną pętlę nauczania (przydatne gdy użytkownik chce *tylko* zobaczyć gałęzie). To +1 handler `_cmd_wiki` w SLASH_COMMANDS.

### Prompty — co dokładnie zmienia się w treści

**SYSTEM_PROMPT.md** — nowa sekcja **§5a (przed obecną §6 "Profil zainteresowań")**: *"Wikipedia — kiedy i jak"*. Zawiera (a) policy (PL→EN, tylko `Szersza perspektywa` + `Powiązane`, nie zastępuje cytatu kursu), (b) trigger (po Kroku 4 w pętli, opcjonalnie po pytaniach pobocznych), (c) anti-pattern (cytowanie Wikipedii jako `source_quote` zamiast materiałów AIPH2 — błąd).

**LEARN_QUEST.md** — w "Pętli nauczania konceptu" wstawić Krok **3.5 (Wikipedia)** między 3 (Konkret) a 4 (Why/Tradeoff/Pitfall): *"Wywołaj `wikipedia_lookup(title=<koncept>, mode='full')`. Z extract destyluj 1-2 zdania uzupełnienia do `Szersza perspektywa`. Z `branches` wybierz 2-3 najtrafniejsze (te które są naprawdę powiązane z konceptem, nie generic) i przygotuj listę dla `Powiązane (Wikipedia)`."* Plus: w "Krok 5 — Zapis karty" dodać `wikipedia_branches` do listy obowiązkowych argumentów (z możliwością pustej listy gdy Wikipedia nie miała hasła).

**LEARN_FILE.md** — analogiczna wstawka, krótsza (delegacja do SYSTEM_PROMPT §5a).

**REVIEW_SESSION.md** — najistotniejsza zmiana:
- Po **Krok 2d (ocena)** + **Krok 2e (komentarz po ocenie)** wstawić **Krok 2f — Gałąź wiedzy**:
  - jeśli `card.wikipedia_branches` niepuste **i grade ≥ 3**: pokaż 2-3 tytuły z URL, zapytaj *"Chcesz teraz pociągnąć którąś gałąź?"*. Jeśli tak → wywołaj `wikipedia_lookup(title=<wybrana>, mode='full')` na świeżo (cache z sesji), zaprezentuj jak side-question (intuicja → odpowiedź → pytanie sprawdzające) i zapisz **osobną** kartę przez `add_card_full(type='wikipedia-branch', source_path=<URL>, source_quote=<extract>)`. Po jednej gałęzi pytaj o kolejną — max 2 na sesję review (żeby nie zjadać czasu na powtórki).
  - jeśli `card.wikipedia_branches` puste i grade ≤ 2 **przy drugim z rzędu lapsie**: wywołaj `wikipedia_lookup` na świeżo i pokaż 1 sąsiednie hasło jako *"inny kąt na ten koncept"*. NIE zapisuj nowej karty (to tylko mnemonik), ale dodaj note do `record_review` z URL Wikipedii.

**INTEREST_SIGNALS.md** — drobne, opcjonalne: dodać sygnał "wybrał gałąź Wikipedii" → `record_interest(topic=<branch>, signal='+wiki-branch', weight_delta=-10)`. Wybranie eksploracji to mocny sygnał zainteresowania.

## Relevant Files

Pliki do modyfikacji:

- `modules/tools.py` — nowy tool `wikipedia_lookup`, rejestracja w `learning_tools_server`, rozszerzenie `add_card_full` o `wikipedia_branches` parameter (parsing JSON-encoded listy).
- `modules/models.py` — pole `wikipedia_branches: list[dict]` w `RoundCard`.
- `modules/card_io.py` — opcjonalna sekcja `## Powiązane (Wikipedia)` w `build_body` (renderowanie tylko gdy lista niepusta) + parser w `parse_body` (jeśli istnieje) lub komentarz że frontmatter jest źródłem prawdy.
- `learn_agent.py` — `wikipedia_lookup` w `allowed_tools`, dodatkowa pozycja w `SLASH_HELP_ROWS` (komenda `/wiki <hasło>`), handler `_cmd_wiki`.
- `prompts/SYSTEM_PROMPT.md` — nowa sekcja §5a "Wikipedia — kiedy i jak", wzmianka w §7 "Spis narzędzi" (11 narzędzi MCP zamiast 10).
- `prompts/LEARN_QUEST.md` — Krok 3.5 (Wikipedia) w pętli, dodanie `wikipedia_branches` do Krok 5.
- `prompts/LEARN_FILE.md` — analogiczna, krótsza wzmianka.
- `prompts/REVIEW_SESSION.md` — nowy Krok 2f "Gałąź wiedzy" (grade ≥ 3 → oferta, grade ≤ 2 lapse-2x → mnemonik).
- `prompts/INTEREST_SIGNALS.md` — opcjonalnie: nowy sygnał `+wiki-branch`.
- `tests/smoke_e2e.py` — dorzucić smoke test: stub Wikipedii (httpx mock), wywołanie `wikipedia_lookup` przez MCP, weryfikacja że wynik zawiera summary + branches + URLs.

### New Files

- `modules/wikipedia.py` — czysty wrapper REST API Wikipedii. Funkcje: `fetch_summary(title, lang)`, `fetch_related(title, lang, limit)`, oraz helper `lookup(title, lang='auto', branches=3, mode='full')`. Używa `httpx.AsyncClient`, in-memory `LRU` cache (functools dla sync, manualny dict dla async). Brak zależności poza tym co już jest (`httpx` jest tranzytywne via `claude_agent_sdk` — sprawdzić w `pyproject.toml`, dodać jawnie jeśli trzeba przez `uv add httpx`).
- `tests/test_wikipedia.py` — unit testy dla wrappera (mockowany transport httpx), testy fallbacku PL→EN, testy cache, testy obcięcia długich tekstów.

## Implementation Phases

### Phase 1: Foundation

- Dodać `httpx` jawnie do deps jeśli nie jest (`uv add httpx`).
- Napisać `modules/wikipedia.py` — czysty client, zero zależności od reszty agenta. Zwraca strukturę `{summary: {...}, branches: [...], notes}` lub rzuca wyjątek z czytelnym komunikatem.
- Unit testy `tests/test_wikipedia.py` — fallback PL→EN, cache, error handling, obcięcia.

### Phase 2: Core Implementation

- Rozszerzyć `RoundCard` w `modules/models.py` o `wikipedia_branches`.
- `build_body` w `modules/card_io.py` — opcjonalna sekcja w body.
- Nowy MCP tool `wikipedia_lookup` w `modules/tools.py` + `add_card_full` przyjmuje `wikipedia_branches` (JSON string parsowany do listy z walidacją `title` + `url`).
- Rejestracja w `learning_tools_server`.
- `learn_agent.py` — `allowed_tools` + opcjonalny `/wiki` slash command + help text.
- Smoke test E2E w `tests/smoke_e2e.py`: query agenta wymuszający `wikipedia_lookup`, asercja na zapis karty z `wikipedia_branches` w frontmatter.

### Phase 3: Integration & Polish

- Aktualizacja czterech promptów (`SYSTEM_PROMPT.md`, `LEARN_QUEST.md`, `LEARN_FILE.md`, `REVIEW_SESSION.md`) — sekcje Wikipedia, kroki 3.5 i 2f, anti-patterns.
- Drobny update `INTEREST_SIGNALS.md` (sygnał `+wiki-branch`).
- Aktualizacja `README.md` — wzmianka o nowej feature i `/wiki` w spisie komend.
- Pełny test ręczny: `just run`, sesja `/learn-quest <slug>`, weryfikacja że agent sięga po Wikipedię, że karta ma sekcję `Powiązane (Wikipedia)` i frontmatter `wikipedia_branches`. Potem `/review` na nowej karcie z grade=4 → weryfikacja oferty gałęzi.

## Team Orchestration

- Operuję jako team lead.
- Trzy role w zespole: builder kodu (tools + schema + REPL + testy), builder promptów (4 pliki MD), reviewer (przegląd końcowy + smoke run).
- Builder kodu i builder promptów mogą pracować **równolegle** — schemat karty + nowy MCP tool są stabilną umową, prompty mogą być pisane w oderwaniu od dokładnej implementacji (znając tylko sygnaturę `wikipedia_lookup`).
- Reviewer wchodzi na końcu, jako sequential gate.

### Team Members

- Builder
  - Name: builder-impl
  - Role: implementacja modułu Wikipedia, rozszerzenie schematu karty, nowy MCP tool `wikipedia_lookup`, hookup w `learn_agent.py`, testy unit + smoke
  - Agent Type: general-purpose
  - Resume: true

- Builder
  - Name: builder-prompts
  - Role: aktualizacja czterech plików w `prompts/` (SYSTEM_PROMPT, LEARN_QUEST, LEARN_FILE, REVIEW_SESSION) plus drobnostka w INTEREST_SIGNALS i README. Pisze po polsku, w stylu istniejących promptów (sekcje numerowane, anti-patterns na końcu)
  - Agent Type: general-purpose
  - Resume: true

- Reviewer
  - Name: reviewer
  - Role: przegląd kodu (czytelność, brak halucynacji, zgodność z politiką cytowania), przegląd promptów (spójność, brak konfliktów z już istniejącymi sekcjami), uruchomienie testów (`just test` lub `uv run pytest`), próba ręczna `just run` z wymuszonym pojedynczym lookupem
  - Agent Type: general-purpose
  - Resume: false

## Step by Step Tasks

Wykonujemy w kolejności. Po każdym zadaniu `TaskUpdate` na `completed`. Zadania równoległe oznaczone `Parallel: true`.

### 1. Foundation — Wikipedia client module
- **Task ID**: wikipedia-client
- **Depends On**: none
- **Assigned To**: builder-impl
- **Agent Type**: general-purpose
- **Parallel**: false
- Sprawdzić czy `httpx` jest jawną zależnością w `pyproject.toml`. Jeśli nie — `uv add httpx` (potem `uv lock`).
- Stworzyć `modules/wikipedia.py` z funkcjami `fetch_summary(title, lang)`, `fetch_related(title, lang, limit)`, `lookup(title, lang='auto', branches=3, mode='full')`.
- `lookup` z `lang='auto'`: spróbuj `pl`, jeśli 404 lub `extract` < 500 znaków → spróbuj `en`. Zwróć `notes` zawierające informację o fallbacku.
- Cache `_WIKI_CACHE: dict[(lang, title.lower()), (timestamp, result)]` z TTL 3600s.
- Caps: extract ≤ 1500 chars, każdy branch summary ≤ 300, łącznie ≤ 6000 znaków serializowanej odpowiedzi.
- Brak zewnętrznych zmiennych — wszystko in-memory. Sygnatura asynchroniczna (`async def`).

### 2. Foundation — testy modułu Wikipedia
- **Task ID**: wikipedia-tests
- **Depends On**: wikipedia-client
- **Assigned To**: builder-impl
- **Agent Type**: general-purpose
- **Parallel**: false
- `tests/test_wikipedia.py` — `pytest`-style.
- Testy: (a) summary OK, (b) 404 PL → fallback EN, (c) extract too short → fallback EN, (d) cache działa (drugie wywołanie nie idzie do sieci), (e) caps respektowane (długi extract obcięty), (f) `mode='branches-only'` zwraca tylko `branches`, (g) `mode='summary-only'` zwraca tylko `summary`.
- Mock przez `httpx.MockTransport` (httpx natywnie wspiera).

### 3. Core — schema + body builder
- **Task ID**: card-schema
- **Depends On**: none
- **Assigned To**: builder-impl
- **Agent Type**: general-purpose
- **Parallel**: true (równolegle z `wikipedia-client`)
- W `modules/models.py` — dodać `wikipedia_branches: list[dict] = Field(default_factory=list)` do `RoundCard`.
- W `modules/card_io.py` — w `build_body` po sekcji `## Powiązane karty` dodać warunkowy blok: jeśli `rc.wikipedia_branches` niepuste, renderować `## Powiązane (Wikipedia)` z listą `- [{title}]({url}) — {summary}`. Pusta lista → sekcji w ogóle nie ma (zero noise).
- Aktualizacja `_HEADING_TO_FIELD` w `card_io.py` (parser) — opcjonalne, w zasadzie frontmatter jest źródłem prawdy, ale dla kompletności dodać `"Powiązane (Wikipedia)": "wikipedia_branches"` jako pole tylko-do-zapisu (parser robi best-effort, nie hard-required).
- Smoke test: jeden test budujący `RoundCard` z 2 gałęziami, weryfikujący że `build_body` zawiera nową sekcję; drugi test z pustą listą — weryfikujący że sekcji NIE ma.

### 4. Core — MCP tool wrapper
- **Task ID**: mcp-tool
- **Depends On**: wikipedia-client, card-schema
- **Assigned To**: builder-impl
- **Agent Type**: general-purpose
- **Parallel**: false
- W `modules/tools.py` — nowa async `wikipedia_lookup(args)` opakowująca `modules.wikipedia.lookup(...)`. Sygnatura MCP: `{title: str, lang: str, branches: int, mode: str}`. Domyślne wartości: `lang='auto'`, `branches=3`, `mode='full'`. Walidacja: `branches ∈ [0, 8]`, `lang ∈ {'auto','pl','en'}`, `mode ∈ {'full','summary-only','branches-only'}`. Błąd → `_err(...)`.
- Wynik formatowany jako tekst markdown (struktura: `### Streszczenie ...` + `### Powiązane hasła ...` z linkami) + JSON pod separatorem `--- JSON ---` (żeby agent mógł go bezstratnie zparsować do `wikipedia_branches`).
- `add_card_full` — nowy parametr `wikipedia_branches: str` (JSON-encoded). Parsowanie: pusty/None → []. Niepusty → `json.loads`, walidacja że to lista dictów z `title` i `url`. Zachowuje istniejące guard checki (`source_quote`, `pytanie_sprawdzajace`).
- Rejestracja w `learning_tools_server` — dorzucić `_wikipedia_lookup_tool` na koniec listy.

### 5. REPL hookup
- **Task ID**: repl-allowed-tools
- **Depends On**: mcp-tool
- **Assigned To**: builder-impl
- **Agent Type**: general-purpose
- **Parallel**: false
- `learn_agent.py` — dodać `"mcp__learning__wikipedia_lookup"` do `allowed_tools`.
- Dorzucić wpis do `SLASH_HELP_ROWS`: `("/wiki <hasło>", "Pociągnij gałąź wiedzy z Wikipedii (PL z fallbackiem EN)")`.
- Handler `_cmd_wiki(repl, args)` — jeśli pusty arg → wskazówka. Inaczej: prompt do agenta `"Wywołaj wikipedia_lookup z title='{args}'. Pokaż streszczenie + 3 gałęzie. NIE zapisuj karty (to manualny lookup, nie pętla nauczania)."`. Dodać do `SLASH_COMMANDS`.
- Brak zmian w streaming display.

### 6. Smoke test E2E
- **Task ID**: smoke-test
- **Depends On**: mcp-tool, repl-allowed-tools
- **Assigned To**: builder-impl
- **Agent Type**: general-purpose
- **Parallel**: false
- W `tests/smoke_e2e.py` — dorzucić scenariusz: zainicjalizować REPL bez sieci (mockowany Wikipedia client), wymusić wywołanie `wikipedia_lookup` przez query, sprawdzić że tool został wywołany i że (oddzielne wywołanie) `add_card_full` z `wikipedia_branches='[{...}]'` dał kartę z sekcją `## Powiązane (Wikipedia)` w body.
- Asercja na frontmatter karty: `wikipedia_branches` zachowany jako lista YAML.

### 7. Prompts — SYSTEM_PROMPT
- **Task ID**: prompt-system
- **Depends On**: none
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: true (równolegle z całą Phase 1+2 implementation)
- Dodać sekcję §5a *"Wikipedia — kiedy i jak"* przed §6 (Profil zainteresowań).
- W §5a: policy (PL→EN, tylko `Szersza perspektywa` + `Powiązane`, NIGDY zamiast `source_quote`), trigger (po Kroku 4 w pętli, po pytaniach pobocznych jeśli koncept obcy), anti-patterns.
- W §7 (Spis narzędzi MCP) — dorzucić wiersz `wikipedia_lookup`.
- W §8 (Zabronione) — dorzucić: *"Wikipedia jako `source_quote` zamiast materiałów AIPH2"*.
- W §10 (Antywzorce) — *"Cytowanie Wikipedii jako jedynego źródła konceptu"* + *"Pomijanie wikipedia_lookup gdy koncept ma światową literaturę (np. Lean Startup, JTBD)"*.

### 8. Prompts — LEARN_QUEST
- **Task ID**: prompt-quest
- **Depends On**: prompt-system
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: false
- W "Pętla nauczania konceptu" wstawić Krok **3.5 — Wikipedia** między 3 (Konkret) a 4 (Why/Tradeoff/Pitfall). Treść: trigger + format wywołania + jak destylować wynik do `Szersza perspektywa` (1-2 zdania) i do `Powiązane (Wikipedia)` (2-3 najtrafniejsze gałęzie).
- W Kroku 5 (Zapis karty) — dorzucić `wikipedia_branches` do listy argumentów (z możliwością pustej listy `'[]'` gdy Wikipedia nie miała hasła).

### 9. Prompts — LEARN_FILE
- **Task ID**: prompt-file
- **Depends On**: prompt-system
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: true (z prompt-quest, prompt-review)
- Krótka wzmianka delegująca do SYSTEM_PROMPT §5a — wystarczy 2-3 zdania w sekcji "Pamiętaj".

### 10. Prompts — REVIEW_SESSION
- **Task ID**: prompt-review
- **Depends On**: prompt-system
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: true (z prompt-quest, prompt-file)
- **Najistotniejsza zmiana.** Po Kroku 2e (Komentarz po ocenie) wstawić **Krok 2f — Gałąź wiedzy**:
  - Warunek 1: `card.wikipedia_branches` niepuste **i grade ≥ 3** → pokaż 2-3 tytuły z URL, zapytaj *"Chcesz teraz pociągnąć którąś gałąź?"*. Jeśli tak → świeży `wikipedia_lookup`, mini-side-question (intuicja → odpowiedź → pytanie sprawdzające), zapis OSOBNEJ karty `type='wikipedia-branch'` z `source_path=<URL Wikipedii>`, `source_quote=<extract>`, `wikipedia_branches=<branches z odpowiedzi>` (cykl trwa). Max 2 gałęzie / sesja review.
  - Warunek 2: `card.wikipedia_branches` puste i **drugi z rzędu lapse** (grade ≤ 2 dwa razy z rzędu na tej karcie — sprawdzane w `record_review` wynik `reps`+ostatni `note`) → świeży `wikipedia_lookup` na tytule karty, jedno powiązane hasło pokazane jako "inny kąt". NIE zapisuj nowej karty (to mnemonik). W `record_review` przekaż `note=<URL Wikipedii>`.
- W antywzorcach REVIEW dorzucić: *"Pokazywanie gałęzi przed oceną (zaburza aktywne przypominanie)"* + *"Robienie więcej niż 2 gałęzi w jednej sesji review (czas zżarty)"*.

### 11. Prompts — INTEREST_SIGNALS + README
- **Task ID**: prompt-misc
- **Depends On**: prompt-review
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: false
- `prompts/INTEREST_SIGNALS.md` — dorzucić sygnał `+wiki-branch` (delta -10).
- `README.md` — krótka wzmianka (2-3 linie) o Wikipedii + `/wiki` w sekcji komend.

### 12. Final review pass
- **Task ID**: validate-all
- **Depends On**: wikipedia-tests, smoke-test, mcp-tool, repl-allowed-tools, prompt-system, prompt-quest, prompt-file, prompt-review, prompt-misc
- **Assigned To**: reviewer
- **Agent Type**: general-purpose
- **Parallel**: false
- Przeczytać wszystkie zmienione pliki (`git diff`) — sprawdzić spójność stylu, brak hardkodowanych URLi w testach, brak halucynacji w promptach.
- Uruchomić `uv run pytest tests/` — wszystkie zielone.
- Uruchomić `uv run python -m py_compile learn_agent.py modules/*.py` — bez błędów składniowych.
- Manual smoke: `AIPH2_LEARNING_DIR=/tmp/wiki-test uv run python learn_agent.py` (bez questa, w trybie REPL), wpisać `/wiki Lean Startup`, sprawdzić że agent wywołuje tool i pokazuje gałęzie.
- Sprawdzić że w README sekcja komend jest zgodna z `SLASH_HELP_ROWS` w `learn_agent.py`.
- Raport: zielona / czerwona lista + ewentualne odkryte regresje.

## Acceptance Criteria

- [ ] `wikipedia_lookup` jako MCP tool dostępny dla agenta (widoczny w `allowed_tools`).
- [ ] Wywołanie `wikipedia_lookup(title='Lean Startup')` zwraca summary (≤1500 chars) + 2-3 gałęzie z URLami.
- [ ] Fallback PL→EN działa: `wikipedia_lookup(title='Customer Curiosity')` (brak w PL) zwraca wynik z `lang='en'` w `notes`.
- [ ] Karta zapisana przez `add_card_full(..., wikipedia_branches='[{...}]')` ma sekcję `## Powiązane (Wikipedia)` w body i listę w frontmatter.
- [ ] Pusta `wikipedia_branches` → sekcja **NIE** jest renderowana (brak szumu).
- [ ] `/learn-quest` po wczytaniu materiałów woła `wikipedia_lookup` minimum raz na koncept przy włączonym Internecie (manualny test).
- [ ] `/review` po `record_review` z grade ≥ 3 i niepustym `wikipedia_branches` w karcie pyta o pociągnięcie gałęzi.
- [ ] `wikipedia_lookup` cache działa: drugie wywołanie tego samego `(lang, title)` w tej samej sesji nie idzie do sieci (weryfikowalne przez mock w teście).
- [ ] Wszystkie testy w `tests/` przechodzą.
- [ ] `learn_agent.py --help` pokazuje `/wiki` w help table.
- [ ] Brak regresji: `add_card_full` bez `wikipedia_branches` (stare wywołania) działa jak dotąd.

## Validation Commands

- `uv run pytest tests/` — pełna suita testów (włącznie z nowymi `test_wikipedia.py`).
- `uv run python -m py_compile learn_agent.py modules/*.py` — sanity check kompilacji.
- `uv run python -c "from modules.wikipedia import lookup; import asyncio; print(asyncio.run(lookup('Lean Startup', lang='pl')))"` — test ręczny modułu (wymaga sieci).
- `AIPH2_LEARNING_DIR=/tmp/wiki-test-$(date +%s) uv run python learn_agent.py` → wpisać `/wiki Lean Startup` → zweryfikować output.
- `git diff prompts/` — przegląd zmian w promptach (czy spójne, brak literówek).
- `grep -n 'wikipedia_lookup' prompts/*.md` — weryfikacja że wszystkie cztery prompty wspominają tool tam, gdzie powinny.

## Notes

- **Zależność sieciowa.** Wikipedia wymaga Internetu. Wszystkie testy unit muszą używać `httpx.MockTransport` — żaden test nie idzie do prawdziwego endpointu (CI byłby flaky). Smoke E2E też mockowany. Manualny test (przy reviewer) idzie do prawdziwej Wikipedii.
- **Rate limiting.** Wikipedia REST API: 200 req/sec dla anonimowych klientów. Agent sesyjnie wywołuje 1-3 lookupy na koncept, czyli 5-30 / sesja. Daleko od limitu. Cache dodatkowo redukuje.
- **User-Agent header.** Wikipedia wymaga `User-Agent` zgodnie z polityką ([https://meta.wikimedia.org/wiki/User-Agent_policy](https://meta.wikimedia.org/wiki/User-Agent_policy)). Ustawić: `aiph2-learn-agent/1.0 (https://github.com/...; <kontakt>)` — w `wikipedia.py` jako stała `_WIKI_UA`. Bez UA Wikipedia czasem zwraca 403.
- **TTL cache.** 1h jest kompromisem: artykuły rzadko się zmieniają, ale nie trzymamy w nieskończoność. Per-process (resetuje przy restarcie agenta).
- **Brak wsparcia dla offline-first.** Jeśli sieci nie ma — `wikipedia_lookup` zwraca błąd, agent informuje użytkownika i kontynuuje bez gałęzi. Karta jest zapisywana z `wikipedia_branches: []`. To OK — nie blokujemy nauki.
- **Prompty po polsku.** Cały istniejący stack jest po polsku (system prompt, learn-quest, review). Nowe sekcje też po polsku. Tytuły w gałęziach Wikipedii są w języku, w którym artykuł istnieje (PL lub EN) — agent NIE tłumaczy ich automatycznie.
- **Nie eksplodować zakresu.** Świadomie pomijamy: (a) wsparcie dla innych źródeł (Britannica, arXiv) — przyszła iteracja, (b) "graf gałęzi" jako wizualizacja — overkill, (c) automatyczne pociąganie gałęzi przy CV (Continuous Discovery) — zachłanne, w sesji review użytkownik decyduje.
