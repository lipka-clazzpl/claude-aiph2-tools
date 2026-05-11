# Plan: Cloze podczas review — gap-fill dla kart, które nie mają cloze'ów

## Task Description

Rozszerz tryb `/review` o **drugi cel sesji powtórki**: nie tylko aktywne przypominanie istniejących kart, ale też **uzupełnianie luk cloze**. Cloze przestaje być wyłącznie efektem ubocznym `add_card_full` (faza nauki) i staje się **pierwszoklasowym celem review** zgodnie z istniejącymi regułami w `CLOZE_RULES.md`.

Dwie ścieżki, wspólny silnik (`add_clozes`):

1. **Inline gap-fill** — w trakcie zwykłej pętli `/review`, po `record_review` każdej karty *bogatej* (non-cloze) agent sprawdza pokrycie cloze przez `list_cards(parent_id=X)`. Gdy karta ma 0 cloze i pojawia się sygnał (`grade<3`, eksplicytna prośba użytkownika, heurystyka systemu), agent proponuje wygenerowanie cloze w tym samym oknie review.
2. **Dedykowany tryb `/cloze-fill`** — osobna komenda REPL przeznaczona do batch-uzupełniania starych kart. Iteruje wyłącznie po kartach **bez** cloze (nowy tool `find_clozeless_cards`), dla każdej proponuje 2-5 cloze (na podstawie tabeli triggerów z `CLOZE_RULES.md`), użytkownik akceptuje / edytuje / odrzuca, agent woła `add_clozes`. Po sesji statystyki.

Soft-shortcut `cloze` w trybie `/review` na żądanie użytkownika wymusza gap-fill dla aktualnej karty niezależnie od oceny.

## Objective

Po wdrożeniu:

1. **Każda karta bogata, której brakuje cloze'ów, ma szansę je dostać** — albo opportunistycznie podczas zwykłego review (inline), albo świadomie przez `/cloze-fill` (batch).
2. **Lapse (`grade<3`)** na karcie bez cloze automatycznie triggeruje propozycję wygenerowania atomowych Q&A — bo właśnie brak atomowości recall'u jest częstą przyczyną lapsa.
3. **Legacy cards** (sprzed wdrożenia cloze, czyli sprzed `c08aa7e`) odzyskują pokrycie cloze bez konieczności re-learning'u.
4. **Nowy tool `find_clozeless_cards`** pozwala zobaczyć i zaadresować cały dług cloze w jednej sesji.
5. **`CLOZE_RULES.md`** ma dedykowaną sekcję „Review-time generation" z triggerami, by agent miał deterministyczną politykę kiedy proponować, a kiedy nie.

## Problem Statement

W aktualnym stanie cloze powstają **wyłącznie** w fazie nauki (`add_card_full` → `add_clozes`). To pozostawia trzy luki:

1. **Legacy debt.** Karty utworzone przed wdrożeniem cloze (commits przed `c08aa7e`) mają 0 cloze. Bez gap-fill'u zostaną tak na zawsze, bo użytkownik nie będzie ich re-learn'ował.
2. **Pominięcia agenta.** Prompt instrukcja „po `add_card_full` wywołaj `add_clozes`" nie jest twardą regułą kodu — agent czasami pominie z powodu non-determinism / długiego kontekstu / pomyłki. Brak ścieżki naprawczej.
3. **Lapsy bez akcji.** Zapomnienie karty bogatej (grade<3) sygnalizuje, że recall jest za szeroki — czyli właśnie ten przypadek, w którym **brakuje atomowych cloze**. Obecny review tylko resetuje interwał, niczego nie naprawia.

Dodatkowo: review w obecnym kształcie ma jeden cel (recall + ocena). Cloze jako *cel sam w sobie* (instrukcja użytkownika) wymaga jawnego potraktowania w `REVIEW_SESSION.md` — w przeciwnym razie agent będzie trzymał się starej pętli.

## Solution Approach

### Decyzje projektowe (z uzasadnieniem)

**D1 — Inline gap-fill po `record_review`, sterowany sygnałami.** Po `record_review` każdej karty `type ∉ {cloze}`, agent wywołuje `list_cards(parent_id=<id>, type='cloze')`. Jeśli wynik pusty → agent kwalifikuje sygnały:

| Sygnał | Akcja |
|---|---|
| `grade < 3` + 0 cloze | **Propose silnie** ("zauważyłem, że ta karta nie ma cloze'ów. Zrobimy 3?"). Default = tak. |
| `grade < 3` + 0 cloze + `reps == 0 i lapses >= 1` (powtórny lapse) | **Propose stanowczo**, generuj automatycznie po krótkim potwierdzeniu. |
| `grade ≥ 3` + 0 cloze + karta starsza niż 30 dni | **Propose miękko** ("ta karta ma X dni i 0 cloze, dorzucimy?"). |
| `grade ≥ 3` + 0 cloze + karta typu `concept`/`framework` (bogata) | **Propose miękko**. |
| `grade ≥ 3` + 0 cloze + karta `side-question`/`pitfall` (krótka) | **Pomiń** (nie zalewaj sesji). |
| Użytkownik napisał `cloze` / `zrób cloze` | **Wygeneruj zawsze**, niezależnie od pozostałych warunków. |

Logika: lapse jest najsilniejszym sygnałem braku atomowości; wiek karty + bogaty typ to słabsze. Krótkie karty (side-question/pitfall) zostawiamy w spokoju, chyba że user wyraźnie chce.

**D2 — `/cloze-fill` jako oddzielny tryb batch.** Komenda iteruje po wynikach nowego tool'a `find_clozeless_cards`. Dla każdej karty:
1. `read_card(card_id)` → agent ma kontekst.
2. Krótkie streszczenie (Sedno + Cytat) — bez kompletnego flow review (to nie powtórka, to tworzenie cloze).
3. Propozycja 2-5 cloze (zgodnie z tabelą triggerów w `CLOZE_RULES.md` — daty/liczby/terminy/itd.) jako lista `{front, back}`.
4. User: `tak` / `edytuj` / `nie` / `pomiń resztę`.
5. `add_clozes(parent_id, clozes=...)` → potwierdzenie.

Tryb nie zmienia harmonogramu SM-2 dla karty bogatej (to nie jest review). Ale **utworzone cloze** dostają normalny `sm2:` i pojawią się w `due_today` od jutra.

**D3 — Nowy MCP tool `find_clozeless_cards` (Tool 14).** Sygnatura: `(quest?, tag?, type?, older_than_days?) -> list[{id, title, type, age_days}]`. Implementacja: jeden przebieg `all_cards()`, oddziel cloze'y, zbierz `parent_id`'s ze wszystkich cloze'ów, wyfiltruj non-cloze cards, których `id` nie pojawia się w tym zbiorze. `O(n)`.

**D4 — Cloze nie blokują flow review.** Jeśli `add_clozes` się nie powiedzie — agent pisze jednym zdaniem „cloze odłożone" i przechodzi do następnej karty. **Review > cloze-fill** priorytetowo.

**D5 — Soft-shortcut `cloze` w review.** W dowolnym momencie pętli powtórki użytkownik może wpisać `cloze` / `zrób cloze` / `dorzuć cloze` → agent przerywa flow, wywołuje `list_cards(parent_id=...)`, jeśli istnieją to pokazuje, potem proponuje dodatkowe; jeśli brak — generuje od zera. Po zakończeniu wraca do flow review (do `2e` jeśli karta była już oceniona, do `2c` jeśli jeszcze nie).

**D6 — Cloze nie generuje cloze dla cloze.** Karta `type=cloze` nigdy nie jest celem gap-fill'u. Tool `find_clozeless_cards` filtruje po `type != 'cloze'` z definicji. W inline-flow agent sprawdza `type` przed wywołaniem.

**D7 — Triggery „warto wygenerować" są w `CLOZE_RULES.md`, nie w kodzie.** Tool `find_clozeless_cards` jest agnostyczny — zwraca kandydatów, decyzję podejmuje agent na podstawie promptu. Filozofia spójna z `add_clozes` (no upper limit, agent decyduje).

**D8 — Szybki preview „co już mamy?" w `/cloze-fill`.** Mimo że tryb bierze tylko karty z 0 cloze, przed generowaniem agent **zawsze** woła `list_cards(parent_id=X, type='cloze')` żeby uniknąć race condition (np. user dodał ręcznie). Defensywne.

**D9 — Bez nowych zależności, bez zmian w `models.py`/`sm2.py`/`card_io.py`.** Cała implementacja stoi na istniejących `ClozeCard`, `add_clozes`, `list_cards`, `read_card`. Nowy tool to czysta funkcja na `all_cards()`. Reszta to prompty i REPL handler.

**D10 — Statystyki gap-fill.** `/cloze-fill` na koniec pokazuje: ile kart było bez cloze, ile uzupełniono, ile pominięto, łączna liczba utworzonych cloze. Pomaga użytkownikowi zobaczyć dług i tempo jego spłaty.

### Triggery: kiedy generować cloze podczas review (tabela docelowa do `CLOZE_RULES.md`)

| Sytuacja | Czy proponować? | Default odpowiedź |
|---|---|---|
| 0 cloze + grade < 3 | **TAK, silnie** | tak |
| 0 cloze + grade < 3 + lapses ≥ 2 | **TAK, automatycznie po Y/n** | tak |
| 0 cloze + grade ≥ 3 + karta ≥ 30 dni | TAK, miękko | tak |
| 0 cloze + grade ≥ 3 + karta `concept`/`framework` | TAK, miękko | tak |
| 0 cloze + grade ≥ 3 + karta `side-question`/`pitfall`/`example` | NIE (chyba że user prosi) | n/a |
| ≥1 cloze już istnieje | NIE w inline (chyba że user prosi „dorzuć") | n/a |
| User napisał `cloze` | TAK zawsze | n/a (akcja natychmiastowa) |
| Karta `type=cloze` | NIE nigdy | n/a |

### Skutki dla istniejących sekcji (krótko)

- `add_clozes` → bez zmian (reuse).
- `list_cards` → bez zmian (filtr `parent_id` już jest, dorzucamy tylko `type='cloze'` w wywołaniach).
- `read_card` → bez zmian.
- `record_review` → bez zmian (review-flow normalny, gap-fill jest *po* review).
- `due_today` → bez zmian.
- `export_anki` → bez zmian.
- `find_clozeless_cards` → **nowy tool 14**.
- `REVIEW_SESSION.md` → **dorzucamy Krok 2g** „Cloze gap-fill po review".
- `CLOZE_RULES.md` → **dorzucamy sekcję „Review-time generation"** z tabelą triggerów.
- `CLOZE_FILL.md` → **nowy prompt** — szablon dla `/cloze-fill`.
- `SYSTEM_PROMPT.md` → drobny update sekcji 5 + 7 (nowy tool, nowy moment generacji).
- `learn_agent.py` → `find_clozeless_cards` w `allowed_tools`, nowy handler `_cmd_cloze_fill`, wpis w `SLASH_COMMANDS` i `SLASH_HELP_ROWS`.
- `tests/smoke_e2e.py` → sekcje 12-14: `find_clozeless_cards` happy path + filtr `older_than_days` + sanity że tool nie zwraca kart cloze ani kart z istniejącymi cloze.

## Relevant Files

Use these files to complete the task:

- `modules/tools.py` — dodać `find_clozeless_cards` (Tool 14). Zarejestrować w `learning_tools_server`. Wpisać do `__all__`.
- `learn_agent.py` — `mcp__learning__find_clozeless_cards` do `allowed_tools`; nowy handler `_cmd_cloze_fill`; wpis w `SLASH_COMMANDS`, `SLASH_HELP_ROWS`. Załadować nowy prompt `CLOZE_FILL.md` w `__init__`.
- `prompts/REVIEW_SESSION.md` — Krok 2g (po 2d, przed 2e/2f) + soft-shortcut `cloze` w 2c i 2c-cloze (uwaga: cloze-cloze NIE generuje gap-fill'u dla siebie samego, tylko dla rodzica jeśli user wprost prosi).
- `prompts/CLOZE_RULES.md` — dorzucić sekcję „Review-time generation" z tabelą triggerów (D1) + sekcją „Soft-shortcut `cloze`".
- `prompts/SYSTEM_PROMPT.md` — sekcja 5 (Krok 5): zaznaczyć, że cloze mogą też powstać podczas review (link do `CLOZE_RULES.md` review-time). Sekcja 7: dorzucić wiersz `find_clozeless_cards` do tabeli narzędzi MCP. Sekcja 10 antywzorce: „Pomijanie gap-fill'u po lapsie na karcie bez cloze".
- `prompts/CLOZE_FILL.md` — **nowy plik**: szablon prompta dla trybu `/cloze-fill`. Pętla: `find_clozeless_cards` → dla każdej `read_card` → propozycja 2-5 cloze → akceptacja → `add_clozes` → następna. Statystyki na końcu.
- `tests/smoke_e2e.py` — sekcje 12-14 (patrz „Step by Step Tasks").

### New Files

- `prompts/CLOZE_FILL.md` — prompt-szablon dla nowego slash commanda `/cloze-fill`. Linkowany przez `learn_agent.py` jak `LEARN_QUEST.md` / `REVIEW_SESSION.md`.

## Implementation Phases

### Phase 1: Foundation (tool + reguły)
- `find_clozeless_cards` w `modules/tools.py`.
- Sekcja „Review-time generation" w `CLOZE_RULES.md`.

Cel: agent ma dane (lista kart bez cloze) i politykę (kiedy proponować). Bez zmian w UI / flow.

### Phase 2: Core (gap-fill w review + /cloze-fill)
- Krok 2g w `REVIEW_SESSION.md` + soft-shortcut `cloze`.
- Nowy `prompts/CLOZE_FILL.md`.
- Handler `_cmd_cloze_fill` + rejestracja w `SLASH_COMMANDS` i `SLASH_HELP_ROWS`.
- `mcp__learning__find_clozeless_cards` w `allowed_tools`.

Cel: end-to-end UX dla obu ścieżek (inline + batch).

### Phase 3: Integration & Polish (SYSTEM_PROMPT + smoke + sanity)
- `SYSTEM_PROMPT.md` sekcje 5 + 7 + 10.
- Smoke sekcje 12-14.
- Manualny sanity: usunąć cloze z testowej karty, uruchomić `/cloze-fill`, sprawdzić czy cloze się odbudowują; uruchomić `/review` z legacy kartą + symulować lapse, sprawdzić czy agent proponuje.

## Team Orchestration

- You operate as the team lead and orchestrate the team to execute the plan.
- You're responsible for deploying the right team members with the right context to execute the plan.
- IMPORTANT: You NEVER operate directly on the codebase. You use `Task` and `Task*` tools to deploy team members to the building, validating, testing, deploying, and other tasks.
  - This is critical. You're job is to act as a high level director of the team, not a builder.
  - You're role is to validate all work is going well and make sure the team is on track to complete the plan.
  - You'll orchestrate this by using the Task* Tools to manage coordination between the team members.
  - Communication is paramount. You'll use the Task* Tools to communicate with the team members and ensure they're on track to complete the plan.
- Take note of the session id of each team member. This is how you'll reference them.

### Team Members

Repo nie ma `.claude/agents/team/*.md`, więc wszystkie role to `general-purpose`.

- Builder
  - Name: builder-core
  - Role: Cały Python — `find_clozeless_cards` w `modules/tools.py` (rejestracja w MCP + `__all__`), `learn_agent.py` (`allowed_tools` + `_cmd_cloze_fill` + `SLASH_COMMANDS` + `SLASH_HELP_ROWS` + ładowanie `CLOZE_FILL.md`).
  - Agent Type: general-purpose
  - Resume: true
- Builder
  - Name: builder-prompts
  - Role: Edycja `REVIEW_SESSION.md` (Krok 2g + soft-shortcut), `CLOZE_RULES.md` (sekcja Review-time + soft-shortcut), `SYSTEM_PROMPT.md` (sekcje 5/7/10). Nowy plik `CLOZE_FILL.md`. Bez Pythona.
  - Agent Type: general-purpose
  - Resume: true
- Builder
  - Name: builder-tests
  - Role: Sekcje 12-14 w `tests/smoke_e2e.py`. Uruchomienie smoke (`uv run python tests/smoke_e2e.py`). Walidacja promptów przez grep. `git diff --stat` na koniec.
  - Agent Type: general-purpose
  - Resume: true

## Step by Step Tasks

- IMPORTANT: Execute every step in order, top to bottom. Each task maps directly to a `TaskCreate` call.
- Before you start, run `TaskCreate` to create the initial task list that all team members can see and execute.

### 1. Tool: find_clozeless_cards (MCP, Tool 14)

- **Task ID**: tool-find-clozeless
- **Depends On**: none
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: true (niezależne od task 2)
- W `modules/tools.py` dodać Tool 14 po `add_clozes`:
  ```python
  # ---------------------------------------------------------------------------
  # Tool 14: find_clozeless_cards
  # ---------------------------------------------------------------------------

  async def find_clozeless_cards(args: dict[str, Any]) -> dict[str, Any]:
      """Listuje karty NON-cloze, ktore nie maja zadnych cloze-children.

      Filtry: quest (przedrostek), tag (dokladne), type (dokladne),
      older_than_days (int — tylko karty starsze niz N dni od `created`).
      """
      try:
          import datetime as _dt
          cards = sm2.all_cards()

          cloze_parents: set[str] = set()
          for c in cards:
              if c.type == "cloze":
                  pid = c.meta.get("parent_id")
                  if pid:
                      cloze_parents.add(pid)

          non_cloze = [c for c in cards if c.type != "cloze"]

          quest = (args.get("quest") or "").strip()
          tag = (args.get("tag") or "").strip()
          ctype = (args.get("type") or "").strip()
          if quest:
              non_cloze = [c for c in non_cloze if (c.quest or "").startswith(quest)]
          if tag:
              non_cloze = [c for c in non_cloze if tag in c.tags]
          if ctype:
              non_cloze = [c for c in non_cloze if c.type == ctype]

          older = args.get("older_than_days")
          if older is not None and str(older).strip() != "":
              try:
                  days = int(older)
                  cutoff = _dt.date.today() - _dt.timedelta(days=days)
                  def _created(c):
                      raw = c.meta.get("created")
                      if not raw:
                          return _dt.date.today()
                      try:
                          return _dt.date.fromisoformat(str(raw))
                      except ValueError:
                          return _dt.date.today()
                  non_cloze = [c for c in non_cloze if _created(c) <= cutoff]
              except (TypeError, ValueError):
                  pass

          clozeless = [c for c in non_cloze if c.id not in cloze_parents]

          if not clozeless:
              return _ok("Wszystkie karty (po filtrach) maja juz cloze.")

          today = sm2.today()
          lines = [f"Karty bez cloze ({len(clozeless)}):"]
          for c in clozeless:
              raw = c.meta.get("created") or ""
              age = ""
              try:
                  d = _dt.date.fromisoformat(str(raw))
                  age = f"  age: {(today - d).days}d"
              except ValueError:
                  pass
              lines.append(
                  f"  {c.id}\n"
                  f"    title: {c.title}\n"
                  f"    type: {c.type}  quest: {c.quest or '-'}{age}"
              )
          return _ok("\n".join(lines))

      except Exception as e:  # noqa: BLE001
          return _err(f"Blad listy kart bez cloze: {e}")


  _find_clozeless_tool = tool(
      "find_clozeless_cards",
      "Listuje karty non-cloze, ktore nie maja jeszcze zadnych cloze-children. "
      "Filtry: quest (przedrostek), tag (dokladne), type (dokladne), older_than_days (int). "
      "Uzywany przez tryb /cloze-fill do batch-uzupelniania luk cloze.",
      {
          "quest": str,
          "tag": str,
          "type": str,
          "older_than_days": int,
      },
  )(find_clozeless_cards)
  ```
- Dorzucić `_find_clozeless_tool` do listy `tools=[...]` w `create_sdk_mcp_server`.
- Dodać `find_clozeless_cards` do `__all__`.

### 2. CLOZE_RULES.md: sekcja Review-time generation

- **Task ID**: prompts-cloze-rules
- **Depends On**: none
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: true
- Po sekcji „Podsumowanie operacyjne" w `prompts/CLOZE_RULES.md` dodać dwie nowe sekcje:
  ```md
  ---

  ## Review-time generation (gap-fill)

  Cloze powstają nie tylko po `add_card_full` (faza nauki), ale **też podczas
  review** — kiedy karta bogata zostaje powtórzona, a okazuje się, że nie ma
  jeszcze żadnych cloze'ów. Cel: domknąć dług cloze dla kart starszych niż
  wdrożenie cloze-feature i ratunek po lapsach.

  Po `record_review` każdej karty `type ∉ {cloze}` agent **musi** wywołać
  `list_cards(parent_id=<id>, type='cloze')` i zinterpretować wynik wg tabeli:

  | Sytuacja | Czy proponować? | Domyślna sugestia |
  |---|---|---|
  | 0 cloze + grade < 3 | **TAK, silnie** | tak (1 zdanie zaproszenia) |
  | 0 cloze + grade < 3 + lapses ≥ 2 (powtórny lapse) | **TAK, automatycznie po Y/n** | tak |
  | 0 cloze + grade ≥ 3 + karta starsza niż 30 dni | TAK, miękko | tak |
  | 0 cloze + grade ≥ 3 + karta `concept`/`framework` | TAK, miękko | tak |
  | 0 cloze + grade ≥ 3 + karta `side-question`/`pitfall`/`example` | NIE (chyba że user prosi) | n/a |
  | ≥1 cloze już istnieje | NIE w inline | n/a |
  | Karta `type=cloze` (powtarzasz cloze) | NIE nigdy | n/a |
  | User napisał `cloze` / `zrób cloze` | TAK zawsze | n/a (akcja natychmiast) |

  Liczba cloze'ów do wygenerowania w trybie review: **2-5** (mniej niż przy
  `add_card_full`, bo to recovery, nie pełna sesja). Wybieraj triggery z
  głównej tabeli powyżej (daty / liczby / terminy / kontrasty).

  ## Soft-shortcut `cloze` w review

  W dowolnym momencie pętli `/review` użytkownik może wpisać `cloze`,
  `zrób cloze` lub `dorzuć cloze`. Wtedy:

  1. Wywołaj `list_cards(parent_id=<aktualna karta>, type='cloze')` żeby
     pokazać user'owi, co już jest (jeśli coś jest).
  2. Zaproponuj 2-3 NOWE cloze (nie powtarzaj istniejących frontów).
  3. Po akceptacji wywołaj `add_clozes`.
  4. Wróć do flow review (do oceny jeśli jeszcze nie była, do `2e` jeśli była).

  Soft-shortcut **nie zmienia** harmonogramu SM-2 karty bogatej — to akcja
  niezależna od recall'u.
  ```

### 3. REVIEW_SESSION.md: Krok 2g + soft-shortcut

- **Task ID**: prompts-review-session
- **Depends On**: prompts-cloze-rules (treść triggerów ustalona — REVIEW_SESSION linkuje do CLOZE_RULES)
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: false
- W `prompts/REVIEW_SESSION.md`, **po sekcji `2e. Komentarz po ocenie`** i **przed `2f. Gałąź wiedzy`** wstawić nową sekcję:
  ```md
  ### 2g. Cloze gap-fill (po record_review)

  **Tylko dla `type ∉ {cloze}`.** Karta `type=cloze` przeskakuje ten krok.

  Po `record_review`:

  1. Wywołaj `list_cards(parent_id='<id-karty>', type='cloze')`.
  2. Zinterpretuj wynik wg tabeli z `CLOZE_RULES.md` sekcja „Review-time
     generation":
     - **0 cloze + grade < 3** → silne zaproszenie:
       > „Zauważyłem, że ta karta nie ma żadnych cloze'ów, a właśnie ją
       > zapomniałeś. Zrobimy 3 atomowe Q&A z najtrudniejszych faktów?"
     - **0 cloze + grade ≥ 3 + (karta ≥30 dni LUB type concept/framework)** →
       miękkie zaproszenie:
       > „Ta karta ma 0 cloze'ów. Dorzucimy 2-3 atomowe Q&A?"
     - **0 cloze + grade ≥ 3 + krótka karta** (`side-question`/`pitfall`/`example`) → pomiń.
     - **≥1 cloze** → pomiń (chyba że user wpisał `cloze`).
  3. Jeśli user akceptuje:
     - Zaproponuj 2-5 par `{front, back}` (zgodnie z `CLOZE_RULES.md` tabela
       triggerów: daty/liczby/terminy/kontrasty).
     - **NIE powtarzaj** sedna ani kontekstu w `front` — front to atomowe
       pytanie (zasada minimum information).
     - Pokaż listę → user akceptuje / edytuje → `add_clozes(parent_id=<id>, clozes=...)`.
     - Krótkie potwierdzenie: `Dodano N cloze'ów do <id-karty>`.
  4. Jeśli user odmówi → kontynuuj do `2f` lub do następnej karty.
  5. Jeśli `add_clozes` zwróci błąd → 1 zdanie „cloze odłożone" i kontynuuj.
     Review > cloze-fill priorytetowo.

  ### Soft-shortcut `cloze` w trakcie review

  W dowolnym momencie pętli (przód, tył, po ocenie) użytkownik może wpisać:
  `cloze` / `zrób cloze` / `dorzuć cloze`.

  Wtedy **przerwij flow** i wykonaj 2g powyżej (z pominięciem oceny — generuj
  niezależnie od grade'a). Po dokończeniu wróć do miejsca, w którym byłeś:
  - Jeśli karta nie była jeszcze oceniona → wróć do `2c` (czekaj na ocenę).
  - Jeśli była oceniona → wróć do `2e` (komentarz / `2f`).
  - Jeśli karta była `type=cloze` → wygeneruj cloze dla **rodzica** (przez
    `parent_id` z frontmattera), nie dla samego cloze'a.
  ```
- W sekcji „Antywzorce do uniknięcia" dorzucić wiersz:
  > - Pomijanie kroku `2g` po lapsie na karcie bez cloze'ów — najsilniejszy sygnał, że brakuje atomowych Q&A.

### 4. CLOZE_FILL.md: nowy prompt dla /cloze-fill

- **Task ID**: prompts-cloze-fill
- **Depends On**: prompts-cloze-rules
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: false
- Utworzyć **nowy plik** `prompts/CLOZE_FILL.md`:
  ```md
  # Tryb cloze-fill — `/cloze-fill`

  Cel: **uzupełnić cloze'y dla kart bogatych, którym ich brakuje.**
  Komenda iteruje po kartach bez cloze (legacy + pominięcia agenta) i
  dla każdej proponuje 2-5 atomowych Q&A zgodnie z `CLOZE_RULES.md`.

  Tryb **NIE przeprowadza review** (nie ma oceny 0-5, nie ma SM-2 update).
  Cel jedyny: tworzyć cloze.

  ## Krok 1 — Lista kart bez cloze

  1. Wywołaj `find_clozeless_cards`. Argumenty opcjonalne: `quest`, `tag`,
     `type`, `older_than_days` — jeśli user przekazał filtry w argumencie
     komendy, użyj. W przeciwnym razie bez filtrów.
  2. Jeśli pusto → „Wszystkie karty mają już cloze. Wracamy?". Koniec.
  3. Jeśli niepusto → krótka informacja: „Znalazłem N kart bez cloze. Lecimy
     po kolei. Dla każdej zaproponuję 2-5 cloze, ty akceptujesz / edytujesz /
     pomijasz."

  ## Krok 2 — Pętla generacji

  Dla **każdej** karty z listy:

  ### 2a. Wczytanie karty

  1. `read_card(card_id='<id>')` — pobierz pełny frontmatter + body.
  2. Defensywnie: `list_cards(parent_id='<id>', type='cloze')` — race-check,
     czy ktoś nie dodał cloze'ów ręcznie. Jeśli ≥1 → pomiń kartę („już ma N
     cloze'ów, pomijam") i przejdź do następnej.

  ### 2b. Krótki kontekst dla użytkownika

  Pokaż:
  ```
  === KARTA <id> ===
  Tytuł: <title>
  Type: <type>  Quest: <quest>
  Sedno: <sedno>  (max 2 zdania)
  Cytat źródłowy: <source_quote>  (max 2 zdania)
  ```
  Bez 11 sekcji — to nie review, to triage.

  ### 2c. Propozycja 2-5 cloze

  Wygeneruj 2-5 par `{front, back}` zgodnie z **tabelą triggerów** w
  `CLOZE_RULES.md` (daty / liczby / terminy / kontrasty / nazwy własne).
  Każdy cloze MUSI być atomowy (jeden fakt). Pokaż jako numerowaną listę:

  ```
  Proponuję:
    1. front: "..." → back: "..."
    2. front: "..." → back: "..."
    3. front: "..." → back: "..."

  Akceptujesz? (tak / edytuj N / nie / pomiń resztę)
  ```

  ### 2d. Reakcja użytkownika

  - `tak` / `t` / `ok` → wywołaj `add_clozes(parent_id='<id>', clozes='<JSON>')`. Potwierdź `Dodano N cloze'ów`.
  - `edytuj N` → user dyktuje zmianę dla cloze nr N. Przyjmij, zaktualizuj listę, pokaż jeszcze raz, czekaj na akceptację.
  - `nie` / `n` / `pomiń` → pomiń tę kartę, przejdź do następnej.
  - `pomiń resztę` / `koniec` → przerwij pętlę, przejdź do Kroku 3.

  ### 2e. Następna karta

  Po zapisie / pominięciu — przejdź do następnej karty z listy.

  ## Krok 3 — Statystyki sesji

  Po zakończeniu (lub przerwaniu):
  - Ile kart przetworzono.
  - Ile uzupełniono cloze'ami.
  - Ile pominięto.
  - Łącznie dodanych cloze'ów.
  - Pozostało kart bez cloze (jeśli user przerwał wcześniej).

  Format:
  ```
  Sesja /cloze-fill:
    karty przetworzone: 8
    uzupełnione: 6  pominięte: 2
    cloze'y dodane: 19
    pozostało bez cloze: 4 (uruchom /cloze-fill ponownie żeby kontynuować)
  ```

  ## Antywzorce

  - Generowanie cloze'a powtarzającego sedno karty-rodzica — łamie zasadę
    minimum information.
  - Multiclaim front (np. „Co to X i Y?") — łam na dwa.
  - Generowanie z `type=cloze` jako rodzica — niemożliwe, tool `find_clozeless_cards` filtruje.
  - Pomijanie defensywnego `list_cards` w 2a (race condition).
  - Wykonywanie `record_review` w tym trybie — to nie review, tylko triage.
  ```

### 5. Wire-up REPL: /cloze-fill + allowed_tools + ładowanie promptu

- **Task ID**: wire-repl-cloze-fill
- **Depends On**: tool-find-clozeless, prompts-cloze-fill
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- W `learn_agent.py`:
  - W `LearningAgentREPL.__init__` po `self.review_template = ...` dorzuć:
    ```python
    self.cloze_fill_template = _load_prompt("CLOZE_FILL.md")
    ```
  - W `self.allowed_tools` dodać:
    ```python
    "mcp__learning__find_clozeless_cards",
    ```
  - Dorzucić nowy handler **po `_cmd_review`** (zachowaj porządek logiczny — tryby uczenia/review):
    ```python
    async def _cmd_cloze_fill(repl: LearningAgentREPL, args: str) -> bool:
        filt = args.strip()
        base = repl.cloze_fill_template or (
            "Wywolaj find_clozeless_cards. Dla kazdej karty wczytaj read_card, "
            "zaproponuj 2-5 cloze zgodnie z CLOZE_RULES.md i po akceptacji wywolaj "
            "add_clozes. Na koncu pokaz statystyki sesji."
        )
        if filt:
            prompt = (
                base
                + f"\n\nFiltry przekazane przez uzytkownika: {filt!r}. "
                "Przekaz je do find_clozeless_cards (np. quest='X' lub older_than_days=30)."
            )
        else:
            prompt = base
        await repl.process_query(prompt, display=f"/cloze-fill {filt}".rstrip())
        return True
    ```
  - W `SLASH_COMMANDS` dodać:
    ```python
    "/cloze-fill": _cmd_cloze_fill,
    ```
  - W `SLASH_HELP_ROWS` dodać (umieść po `/review`):
    ```python
    ("/cloze-fill [filtr]", "Uzupelnij cloze'y dla kart, ktore ich nie maja"),
    ```

### 6. SYSTEM_PROMPT.md: drobne updates

- **Task ID**: prompts-system
- **Depends On**: prompts-cloze-rules
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: true (z task 5 — inny plik)
- W `prompts/SYSTEM_PROMPT.md`:
  - **Sekcja 5 (Krok 5)**: po istniejącym akapicie „Po udanym `add_card_full` oceń ile cloze'ów..." dorzuć:
    > Cloze'y mogą też powstać podczas **review** (gap-fill po `record_review` na karcie bez cloze'ów) i w dedykowanym trybie `/cloze-fill`. Reguły review-time: patrz `CLOZE_RULES.md` sekcja „Review-time generation".
  - **Sekcja 7 (Spis narzędzi MCP)**: dorzuć wiersz tabeli (po `add_clozes`):
    | `find_clozeless_cards` | Listuje karty non-cloze, które nie mają jeszcze cloze-children. Filtry: quest, tag, type, older_than_days. Używany przez `/cloze-fill` i krok 2g w review. |

    Zmień nagłówek sekcji z `Narzędzia MCP (11)` / `(13)` na `Narzędzia MCP (14)` (sprawdź faktyczną liczbę po zmianie).
  - **Sekcja 10 (Antywzorce)**: dorzuć:
    > - Pomijanie gap-fill'u (Krok 2g) po lapsie na karcie bez cloze'ów — najsilniejszy sygnał, że brakuje atomowych porcji recall'u, a my go ignorujemy.

### 7. Tests: smoke e2e dla find_clozeless_cards

- **Task ID**: tests-smoke-clozeless
- **Depends On**: tool-find-clozeless
- **Assigned To**: builder-tests
- **Agent Type**: general-purpose
- **Parallel**: false
- W `tests/smoke_e2e.py`, **po sekcji 11 (Guard: empty front)**, dorzuć trzy nowe sekcje:

  ```python
  # ---------- 12. find_clozeless_cards: parent ma cloze, więc nie pojawia się ----------
  from modules.tools import find_clozeless_cards  # noqa: WPS433

  fcl = await find_clozeless_cards({})
  assert fcl.get("is_error") is not True, f"find_clozeless_cards failed: {fcl}"
  fcl_text = fcl["content"][0]["text"]
  # parent (card_id) MA 8 cloze'ów (z sekcji 7), więc NIE powinien się pojawić
  assert card_id not in fcl_text, (
      f"parent card_id pojawila sie w find_clozeless mimo ze ma cloze: {fcl_text[:300]}"
  )
  # cloze'e same w sobie tez nie powinny sie pojawic
  for cc in cloze_cards:
      cid = cc.metadata["id"]
      assert cid not in fcl_text, (
          f"cloze id {cid} pojawila sie w find_clozeless (powinno byc filtered out)"
      )
  print("[smoke] find_clozeless_cards ok: parent z cloze nie listowany, cloze'e nie listowane")

  # ---------- 13. find_clozeless_cards: nowa karta bez cloze SIE pojawia ----------
  payload2 = _full_payload(title="Karta bez cloze test")
  res2 = await add_card_full(payload2)
  assert res2.get("is_error") is not True
  # extract id from response
  import re as _re
  m = _re.search(r"Zapisano kartę: (\S+)", res2["content"][0]["text"])
  assert m, f"could not extract card_id from {res2}"
  new_card_id = m.group(1)

  fcl2 = await find_clozeless_cards({})
  fcl2_text = fcl2["content"][0]["text"]
  assert new_card_id in fcl2_text, (
      f"nowa karta bez cloze NIE pojawila sie w find_clozeless: {fcl2_text[:300]}"
  )
  print(f"[smoke] find_clozeless_cards ok: nowa karta {new_card_id} listowana")

  # ---------- 14. find_clozeless_cards: po add_clozes znika z listy ----------
  await add_clozes({
      "parent_id": new_card_id,
      "clozes": _json.dumps([{"front": "fp1", "back": "bp1"}]),
  })
  fcl3 = await find_clozeless_cards({})
  fcl3_text = fcl3["content"][0]["text"]
  assert new_card_id not in fcl3_text, (
      f"karta po add_clozes nadal w find_clozeless: {fcl3_text[:300]}"
  )
  print("[smoke] find_clozeless_cards ok: karta znika po add_clozes")
  ```

  Update `REQUIRED_FRONTMATTER_KEYS` jeśli się okaże, że trzeba (raczej nie — ten test nie sprawdza nowych pól).

### 8. Validation

- **Task ID**: validate-all
- **Depends On**: tool-find-clozeless, prompts-cloze-rules, prompts-review-session, prompts-cloze-fill, wire-repl-cloze-fill, prompts-system, tests-smoke-clozeless
- **Assigned To**: builder-tests
- **Agent Type**: general-purpose
- **Parallel**: false
- Uruchom: `uv run python -m py_compile modules/tools.py learn_agent.py tests/smoke_e2e.py` — brak output'u = OK.
- Uruchom: `uv run python tests/smoke_e2e.py` — oczekiwane `PASS` z 14 sekcjami.
- Walidacja promptów (każda komenda powinna mieć ≥1 hit):
  - `grep -n "find_clozeless_cards" prompts/SYSTEM_PROMPT.md prompts/CLOZE_FILL.md`
  - `grep -n "Review-time generation" prompts/CLOZE_RULES.md`
  - `grep -n "Soft-shortcut" prompts/CLOZE_RULES.md prompts/REVIEW_SESSION.md`
  - `grep -n "2g" prompts/REVIEW_SESSION.md`
  - `grep -n "cloze-fill" learn_agent.py`
  - `grep -n "_cmd_cloze_fill" learn_agent.py`
  - `ls prompts/CLOZE_FILL.md`
- Pokaż `git diff --stat` — oczekiwane ~6 plików zmienionych + 1 nowy:
  - `modules/tools.py` (Tool 14)
  - `learn_agent.py` (REPL: handler + allowed_tools + prompt loader + SLASH_*)
  - `prompts/REVIEW_SESSION.md` (Krok 2g + soft-shortcut + antywzorzec)
  - `prompts/CLOZE_RULES.md` (sekcja Review-time + sekcja soft-shortcut)
  - `prompts/SYSTEM_PROMPT.md` (sekcja 5 + 7 + 10)
  - `prompts/CLOZE_FILL.md` (NOWY)
  - `tests/smoke_e2e.py` (sekcje 12-14)

## Acceptance Criteria

- [ ] MCP tool `find_clozeless_cards` zarejestrowany. Filtry: `quest`, `tag`, `type`, `older_than_days`. Zwraca tylko karty `type ≠ cloze`, które nie mają children-cloze.
- [ ] `learn_agent.py`: `mcp__learning__find_clozeless_cards` w `allowed_tools`. Handler `_cmd_cloze_fill` w `SLASH_COMMANDS`. Wpis `/cloze-fill [filtr]` w `SLASH_HELP_ROWS`. Ładowanie `CLOZE_FILL.md` w `__init__`.
- [ ] `prompts/CLOZE_FILL.md` istnieje: 3 kroki, format propozycji `{front, back}`, statystyki na końcu, antywzorce.
- [ ] `prompts/REVIEW_SESSION.md` ma **Krok 2g** „Cloze gap-fill" z tabelą decyzji opartą na grade + wieku + typie. Ma sekcję „Soft-shortcut `cloze`". Ma antywzorzec o pomijaniu 2g po lapsie.
- [ ] `prompts/CLOZE_RULES.md` ma sekcję „Review-time generation" z tabelą triggerów i sekcję „Soft-shortcut `cloze` w review".
- [ ] `prompts/SYSTEM_PROMPT.md`:
  - Sekcja 5 (Krok 5) wzmiankuje cloze podczas review + tryb `/cloze-fill`.
  - Sekcja 7 ma wiersz tabeli `find_clozeless_cards`.
  - Sekcja 10 ma antywzorzec o pomijaniu gap-fill'u.
- [ ] Smoke sekcje 12-14 zielone: parent z cloze nie wylistowany, nowa karta bez cloze wylistowana, po `add_clozes` znika.
- [ ] `uv run python tests/smoke_e2e.py` → `PASS`.
- [ ] Manualny sanity: w działającym `/cloze-fill` agent przeprowadza pętlę na minimum 1 karcie i zapisuje cloze'y. (Sanity test, nie egzekwowane CI'em.)

## Validation Commands

Execute these commands to validate the task is complete:

- `uv run python -m py_compile modules/tools.py learn_agent.py tests/smoke_e2e.py`
- `uv run python tests/smoke_e2e.py`
- `uv run python -c "from modules.tools import find_clozeless_cards; print('ok')"`
- `grep -n "find_clozeless_cards" prompts/SYSTEM_PROMPT.md prompts/CLOZE_FILL.md`
- `grep -n "Review-time generation" prompts/CLOZE_RULES.md`
- `grep -n "Soft-shortcut" prompts/REVIEW_SESSION.md`
- `grep -n "2g" prompts/REVIEW_SESSION.md`
- `grep -cE "cloze.fill" learn_agent.py` — co najmniej 3 (slash, handler, help row)
- `ls prompts/CLOZE_FILL.md`

## Notes

- **Zero nowych zależności.** Wszystko stoi na istniejącym `add_clozes`, `list_cards`, `read_card` + nowy `find_clozeless_cards` w `modules/tools.py`.
- **Brak twardych progów w kodzie.** Triggery w `CLOZE_RULES.md` (lapse, wiek, typ) są na poziomie promptu — koryguj prompt, nie koduj limitów. To samo zachowanie co w `add_clozes` (no upper limit).
- **`find_clozeless_cards` jest agnostyczny.** Zwraca kandydatów; decyzję czy generować podejmuje agent. Jeden tool — dwa konsumenci (`/review` step 2g + `/cloze-fill`).
- **`/cloze-fill` to triage, nie review.** Brak `record_review`, brak SM-2 update na karcie-rodzicu. Tylko `add_clozes`. Nowo utworzone cloze pojawią się w `due_today` jutro normalnie.
- **Soft-shortcut `cloze` jest prompt-level.** Działa tylko w aktywnej sesji `/review`, gdy agent interpretuje user-input. Dla nawigacji poza review użyj `/cloze-fill` z filtrem.
- **Race-check w 2a `/cloze-fill`** (defensywne `list_cards`) jest ważne, bo sesja `/cloze-fill` może być długa, a user mógł w międzyczasie ręcznie dodać cloze (przez `/learn` z innej karty wskazującej na ten sam parent — mało prawdopodobne, ale defensywnie warto).
- **Skill `learning-aiph-quests`** — tryb `/cloze-fill` nie ma odpowiednika po stronie skilla (review.py nie zna gap-fill'u). Osobny plan jeśli użytkownik chce równoległą funkcjonalność tam.
- **Manualny sanity zalecany:**
  - `just run` → `/cloze-fill` na czystym katalogu z 1-2 starymi kartami → sprawdź czy agent generuje sensowne cloze'y.
  - `just run` → `/review` z legacy kartą → odpowiedz źle (grade<3) → sprawdź czy agent woła Krok 2g i proponuje gap-fill.
  - `just run` → `/review` z dowolną kartą → wpisz `cloze` w trakcie pętli → sprawdź czy agent przerywa flow i generuje.
- **Prawdopodobne pytanie do rozważenia później:** czy w `/cloze-fill` agent powinien też proponować *uzupełnienie* karty z 1-2 cloze do 5? Aktualny plan upraszcza do „0 cloze only". Rozszerzenie wymagałoby dodatkowego argumentu `min_cloze_count` w `find_clozeless_cards`. Odkładamy do osobnego planu, jeśli sygnał z użycia to potwierdzi.
