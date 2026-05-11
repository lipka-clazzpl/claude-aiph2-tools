# Plan: Cloze deletion / proste Q&A jako uzupełnienie kart IL

## Task Description

Dodaj do agenta drugi format karty — **cloze / Q&A** — wzorowany na [SuperMemo cloze deletion](https://help.supermemo.org/wiki/Glossary:Cloze_deletion). Po każdej rundzie nauki konceptu, oprócz dotychczasowej bogatej karty 11-sekcyjnej (`add_card_full`), agent generuje adaptywną liczbę atomowych Q&A — tyle ile potrzeba zależnie od bogactwa sesji, liczby dopytań i niejasnych terminów. Każde Q&A to samodzielna karta `type=cloze` z własnym harmonogramem SM-2, podpięta przez `parent_id` do karty-rodzica.

Karty cloze są celowo minimalistyczne i **nie powtarzają tekstu z karty-rodzica** — ich jedyną rolą jest atomowy recall konkretnego faktu plus szybka nawigacja po drzewie w terminalu. Bogaty kontekst (Why/Tradeoff/Konkret) zawsze zostaje w karcie-rodzicu i jest dostępny przez skróty terminalowe.

## Objective

Po wdrożeniu efektem rundy IL będą:
1. **Jedna** karta bogata (status quo — `type ∈ {concept, framework, side-question, ...}`, 11 sekcji, rygor cytatu i pytania sprawdzającego).
2. **N kart** `type=cloze` — atomowe Q&A, liczba zależy od bogactwa sesji (minimum dla prostego konceptu, dużo więcej gdy pojawiają się daty / terminy / dopytania użytkownika). Podpięte do (1) przez `parent_id`.
3. **Nawigacja drzewem** w terminalu: `/tree <card_id>`, `/parent <card_id>` plus skróty `p` i `t` podczas review.

Karty cloze pojawiają się w `due_today`, mogą być powtarzane przez `/review` (z odrębnym, prostym layoutem przód/tył), filtrowane w `list_cards(parent_id=X)` i eksportowane do Anki.

## Problem Statement

Obecnie każda runda IL produkuje *jedną* dużą kartę o 11 sekcjach. Świetnie utrwala kontekst i rozumowanie, ale ma dwa ograniczenia widoczne dopiero na powtórkach:

1. **Niska atomowość recall'u.** `pytanie_sprawdzajace` testuje cały koncept naraz. Jeśli użytkownik nie potrafi przypomnieć sobie konkretnej daty (Airbnb 2009), jednego słowa w definicji (co to "Outcome" w OST) czy jednej liczby (38%→32%) — dostaje ocenę 2 i cała karta wraca jutro. Tymczasem reszta konceptu była znana.
2. **Brak szybkich powtórek.** SuperMemo opiera się na lawinie krótkich Q&A (10-30 sekund każdy). Nasza karta bogata wymaga 2-5 minut. Przez to dzienne `due_today` szybko się rozjeżdża z realnym czasem użytkownika.
3. **Brak kontekstualnej nawigacji.** Gdy użytkownik podczas review zapomni odpowiedzi, może chcieć "zerknąć na kontekst". Teraz musi wyjść z review, wpisać `/cards`, szukać karty ręcznie. Powinno być jedno `p`.

## Solution Approach

### Decyzje projektowe (z uzasadnieniem)

**D1 — Cloze jako osobna karta, nie sekcja.** Każdy cloze to osobny plik `.md` z własnym frontmatterem, własnym `sm2:` i własnym `next_review`. Reuse'ujemy istniejące maszyny (`due_today`, `record_review`, `list_cards`, `export_anki`) zamiast budować równoległe.

**D2 — Schemat „prosty Q&A", nie tylko klasyczny cloze ze składnią `{{c1::...}}`.** Schemat `front + back` obsłuży oba style: agent może zbudować `front="Customer Curiosity to ___ nawyk"` (cloze-style) lub `front="Co to Outcome w OST?"` (otwarte Q&A). Bez parsera markerów, bez splittingu.

**D3 — Cloze body jest celowo puste ze strony kontekstu.** Karta cloze NIE powtarza Sedna, Kontekstu, Why ani żadnego innego tekstu z karty-rodzica. Sekcje body to: `## Pytanie`, `## Odpowiedź`, `## Karta-rodzic`. Nic więcej. Cel: minimalna redundancja, zero "ściągawki" — cloze wymusza czysty recall, a kontekst jest dostępny przez nawigację.

**D4 — Liczba cloze'ów nie jest z góry ograniczona.** Agent sam decyduje ile wygenerować na podstawie sygnałów z sesji (patrz sekcja „Triggery"). Dla prostego konceptu bez dopytań — może to być 2. Dla konceptu z datami, specjalistyczną terminologią i kilkoma pytaniami użytkownika — może to być 10-15. Arbitralny limit w toolze zostaje usunięty. Guard zostaje tylko na `front`/`back` niepuste i `parent_id` istniejący.

**D5 — `parent_id` jako jedyne źródło prawdy o relacji.** Cloze ma `parent_id: <id>` w frontmatterze. Karta-rodzic NIE jest mutowana. Drzewo wyciągasz przez `list_cards(parent_id=X)`.

**D6 — Nowy MCP tool `read_card(card_id)`.** Ładuje pełną kartę po ID bez znajomości ścieżki na dysku. Używany przez `/tree`, `/parent` i agent podczas review gdy użytkownik prosi o kontekst. Tool 11 (clozes to Tool 12 — ale builder może zdecydować o kolejności).

**D7 — Nawigacja terminalowa: `/tree`, `/parent` + skróty `p`/`t` w review.** Dwa nowe REPL slash commands. W REVIEW_SESSION.md: gdy agent pokazuje tył karty cloze, wypisuje hint `↑ p — karta-rodzic  t — drzewo`. Jeśli użytkownik wpisze `p` lub `parent`, agent woła `read_card(parent_id)`. Jeśli `t` lub `tree` — woła `read_card(parent_id)` + `list_cards(parent_id=parent_id)` i formatuje jako drzewo. Agent obsługuje to soft-shortcuty przez prompt, REPL obsługuje slash formy przez nowe handlery.

**D8 — Review branch'uje po `type`.** `REVIEW_SESSION.md` dostaje gałąź: dla `type=cloze` pokazuj TYLKO `front` → poczekaj → `back` + hint nawigacyjny. Bez 11 sekcji.

**D9 — Anki export bez zmian struktury kolumn.** Cloze: `front → kol. 1`, `back → kol. 2`, tagi z tagiem `cloze` → kol. 3.

### Triggery: kiedy generować cloze i ile

Agent generuje cloze po każdym `add_card_full`. Ile ich wygenerować — zależy od sygnałów:

| Sygnał w sesji | Cloze które powinny powstać |
|---|---|
| Pojawia się data lub rok (np. "Airbnb 2009", "2023") | Q: "Kiedy X?" A: rok |
| Pojawia się konkretna liczba / KPI (np. "38%→32%", "11 sekcji") | Q: "Jaki wskaźnik po X?" A: liczba |
| Pojawia się termin słownikowy w specyficznym kontekście | Q: "Co to X w kontekście Y?" A: krótka def. |
| Pojawia się właściwa nazwa (firma, narzędzie, nazwisko) po raz pierwszy | Q: "Z czym kojarzy się X?" A: kontekst kursu |
| Użytkownik dopytuje ("co to znaczy", "nie rozumiem", "a co jeśli...") | Extra cloze dla dopytanego termin/faktu |
| Pojawia się para kontrastu (X vs Y, X prowadzi do Y, X bez X → Y) | Cloze dla każdej strony pary |
| Długa runda dialogu (≥3 tury zanim user odpowiedział poprawnie) | Dodatkowe cloze dla każdego błędu z korekty |

Minimalny baseline — zawsze: 1 cloze z definicją terminu tytułowego karty. Gdy pojawi się ≥3 sygnały z tabeli — można wygenerować 5+. Nie ma górnego limitu; każdy cloze musi jednak być atomowy (jeden fakt).

### Skutki dla istniejących sekcji (krótko)

- `add_card_full` → bez zmian. Citation guard zostaje.
- `due_today` → bez zmian (cloze'e pojawiają się tam jak każda karta).
- `record_review` → bez zmian (cloze ma `sm2:` jak każda inna karta).
- `list_cards` → **dodaj filtr `parent_id`**.
- `export_anki` → drobny patch: dla `type=cloze` użyj `front`/`back`.
- `read_card` → nowy tool (Tool 11).
- `add_clozes` → nowy tool (Tool 12).

## Relevant Files

Use these files to complete the task:

- `modules/models.py` — dodać `ClozeCard` Pydantic. Lekka, 7 pól, bez sekcji kontekstowych z `RoundCard`.
- `modules/card_io.py` — dodać `build_cloze_body(cc: ClozeCard) -> str` (3 sekcje: Pytanie / Odpowiedź / Karta-rodzic). Opcjonalnie rozszerzyć `_HEADING_TO_FIELD` o te nagłówki.
- `modules/tools.py` — dodać `read_card` (Tool 11) i `add_clozes` (Tool 12). Patch `export_anki` (branch cloze) i `list_cards` (filtr `parent_id`). Zarejestrować oba nowe toole w MCP serverze.
- `modules/sm2.py` — bez zmian. `write_new_card` przyjmuje `extra: dict`, `parent_id` wejdzie tamtędy.
- `learn_agent.py` — dorzucić `mcp__learning__read_card` i `mcp__learning__add_clozes` do `allowed_tools`. Dodać handlery REPL: `_cmd_tree` i `_cmd_parent` (dwa nowe slash commands `/tree` i `/parent`).
- `prompts/SYSTEM_PROMPT.md` — sekcja 5 (Krok 5): po `add_card_full` wywołaj `add_clozes` wg reguł triggery. Sekcja 7: dorzuć oba nowe toole. Sekcja 10: antywzorce cloze.
- `prompts/LEARN_QUEST.md` — Krok 5: analogicznie jak SYSTEM_PROMPT sekcja 5.
- `prompts/LEARN_FILE.md` — „Pamiętaj": dorzuć punkt o cloze.
- `prompts/REVIEW_SESSION.md` — Krok 2: branch po type. Dla cloze: tylko front→back + hint nawigacyjny `p` / `t`. Soft-shortcuty `p`, `t`, `parent`, `tree`.
- `prompts/CLOZE_RULES.md` — **nowy plik**: triggery + doktryna minimum information + antywzorce + przykłady dobrego vs złego cloze.
- `tests/smoke_e2e.py` — sekcje 7-11: happy path cloze, brak górnego limitu (test z 8 cloze), list_cards filter parent_id, export_anki branch, guard pustego front.

### New Files

- `prompts/CLOZE_RULES.md` — reguły generowania dobrych cloze'ów (oparte o SuperMemo minimum information, triggery z tabeli, przykłady). Linkowane z `SYSTEM_PROMPT.md`.

## Implementation Phases

### Phase 1: Foundation (schema + body builder + read_card tool)
`ClozeCard` w `models.py` + `build_cloze_body` w `card_io.py` + `read_card` MCP tool w `tools.py`. Bez zmian w zachowaniu agenta.

### Phase 2: Core Implementation (add_clozes tool + patches + wire-up)
`add_clozes` w `tools.py`, rejestracja w MCP. Patch `export_anki` i `list_cards`. Dodaj oba toole do `allowed_tools`. Nowe REPL slash commands `/tree` i `/parent`.

### Phase 3: Integration & Polish (prompts + CLOZE_RULES + tests)
`CLOZE_RULES.md`. Edycja 4 promptów. Rozszerzenie smoke. Uruchom `uv run python tests/smoke_e2e.py`.

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
  - Role: Cały Python — models, card_io, tools (read_card + add_clozes + patche), learn_agent.py (allowed_tools + /tree + /parent).
  - Agent Type: general-purpose
  - Resume: true
- Builder
  - Name: builder-prompts
  - Role: Nowy CLOZE_RULES.md + edycja 4 promptów (SYSTEM_PROMPT, LEARN_QUEST, LEARN_FILE, REVIEW_SESSION). Bez kodu Pythonowego.
  - Agent Type: general-purpose
  - Resume: true
- Builder
  - Name: builder-tests
  - Role: Rozszerzenie smoke_e2e.py o sekcje 7-11. Uruchomienie smoke. Walidacja promptów przez grep.
  - Agent Type: general-purpose
  - Resume: true

## Step by Step Tasks

- IMPORTANT: Execute every step in order, top to bottom. Each task maps directly to a `TaskCreate` call.
- Before you start, run `TaskCreate` to create the initial task list that all team members can see and execute.

### 1. Schema: ClozeCard + build_cloze_body

- **Task ID**: schema-cloze
- **Depends On**: none
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: true (niezależne od task 2 — inne pliki)
- W `modules/models.py` dorzuć `ClozeCard` po `RoundCard`:
  ```python
  class ClozeCard(BaseModel):
      """Atomowa karta Q&A / cloze deletion. NIE powtarza tekstu z karty-rodzica."""
      title: str         # np. "Customer Curiosity — nawyk [cloze]"
      parent_id: str     # id karty bogatej (wymagane)
      front: str         # pytanie lub sentence-z-blankiem
      back: str          # odpowiedź (jeden fakt)
      source_path: str = ""   # dziedziczone z parenta przy zapisie
      tags: list[str] = Field(default_factory=list)
      priority: int = 50
      difficulty: str = "medium"
  ```
  Uwaga: brak `source_quote` — cloze nie cytuje źródła bezpośrednio, link do rodzica wystarczy.
- W `modules/card_io.py` dorzuć funkcję `build_cloze_body`:
  ```python
  def build_cloze_body(cc: ClozeCard) -> str:
      """Minimalistyczne body: tylko Pytanie / Odpowiedź / link do rodzica.
      NIE zawiera Sedno, Kontekst, Why ani żadnego tekstu z karty-rodzica.
      """
      return "\n".join([
          "## Pytanie",
          cc.front.strip(),
          "",
          "## Odpowiedź",
          cc.back.strip(),
          "",
          "## Karta-rodzic",
          f"[[{cc.parent_id}]]",
          "",
      ])
  ```
  Body NIE prependuje `# {title}` — `sm2.write_new_card` to robi.
- Opcjonalnie w `_HEADING_TO_FIELD` (card_io.py) dorzuć mapowanie `"Pytanie": "cloze_front"` i `"Odpowiedź": "cloze_back"` — przydatne gdy `parse_body` będzie wywoływany na cloze (np. przez `export_anki`).

### 2. CLOZE_RULES.md i prompts (nauka)

- **Task ID**: prompts-learn
- **Depends On**: none
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: true
- Utwórz `prompts/CLOZE_RULES.md`:
  - Sekcja "Kiedy generować" — tabela triggerów (daty/liczby/terminy/dopytania/kontrasty/długa runda dialogu).
  - Sekcja "Atomowość" — jeden front = jeden fakt. Przykład dobrego cloze vs złego (multiclaim).
  - Sekcja "Minimalizm body" — cloze nie powtarza tekstu z rodzica, służy recall + nawigacji.
  - Sekcja "Przykłady" — 5 konkretnych par `front` / `back` z kursu AIPH2.
- `prompts/SYSTEM_PROMPT.md`:
  - Sekcja 3 (Atomowość): dorzuć zdanie, że zasada minimum information jest realizowana przez cloze, a karta bogata służy kontekstowi.
  - Sekcja 4 (Krok 5): po opisie `add_card_full` dodaj:
    > Po udanym `add_card_full` oceń ile cloze'ów należy wygenerować (patrz `CLOZE_RULES.md`). Minimum: 1 (definicja terminu tytułowego). Bez górnego limitu — tyle ile sygnałów z sesji uzasadnia. Wywołaj `add_clozes`. Cloze body nie może powtarzać tekstu z karty-rodzica — tylko `front`, `back` i link.
  - Sekcja 7 (Spis narzędzi): dorzuć dwa wiersze tabeli — `read_card` i `add_clozes`.
  - Sekcja 10 (Antywzorce): dorzuć:
    - "Cloze kopiujące `sedno` lub `kontekst` z karty-rodzica — redundancja, zero nowej wartości."
    - "Cloze z multiclaim w `front` (np. 'X to Y i Z') — łam na dwa."
    - "Pominięcie `add_clozes` po `add_card_full` — karta bogata bez atomowych porcji recall'u."
- `prompts/LEARN_QUEST.md`: Krok 5 — po opisie `add_card_full` dorzuć akapit identyczny jak SYSTEM_PROMPT sekcja 4 (kopia, nie link — agent promptu nie ma dostępu do innych plików podczas generowania).
- `prompts/LEARN_FILE.md`: „Pamiętaj" — dodaj punkt: „Po każdej karcie `add_card_full` wywołaj `add_clozes`. Ile cloze'ów: min. 1, bez limitu — zależy od liczby terminów / dat / dopytań w sesji."

### 3. Tool: read_card (MCP, Tool 11)

- **Task ID**: tool-read-card
- **Depends On**: schema-cloze
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- W `modules/tools.py` dorzuć Tool 11 przed `add_clozes`:
  ```python
  async def read_card(args: dict[str, Any]) -> dict[str, Any]:
      try:
          card_id = (args.get("card_id") or "").strip()
          if not card_id:
              return _err("Brak card_id.")
          path = sm2.CARDS_DIR / f"{card_id}.md"
          if not path.exists():
              return _err(f"Nie znaleziono karty: {card_id}")
          card = sm2.load_card(path)
          parent_line = ""
          pid = card.meta.get("parent_id")
          if pid:
              parent_line = f"\n**Karta-rodzic:** {pid}"
          header = (
              f"**ID:** {card.id}\n"
              f"**Tytuł:** {card.title}\n"
              f"**Type:** {card.type}\n"
              f"**Quest:** {card.quest or '-'}\n"
              f"**Tags:** {', '.join(card.tags) or '-'}\n"
              f"**SM-2:** next={card.sm2.next_review} reps={card.sm2.reps} ease={card.sm2.ease:.2f}"
              f"{parent_line}"
          )
          return _ok(f"{header}\n\n---\n\n{card.body}")
      except Exception as e:
          return _err(f"Błąd odczytu karty: {e}")

  _read_card_tool = tool(
      "read_card",
      "Ładuje pełną kartę (frontmatter + body) po card_id. Używany do nawigacji: /tree, /parent, podgląd kontekstu podczas review.",
      {"card_id": str},
  )(read_card)
  ```
- Dorzuć `_read_card_tool` do listy tools w `create_sdk_mcp_server(...)`.
- Dodaj `read_card` do `__all__`.

### 4. Tool: add_clozes (MCP, Tool 12)

- **Task ID**: tool-add-clozes
- **Depends On**: tool-read-card
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- W `modules/tools.py` dorzuć Tool 12:
  ```python
  async def add_clozes(args: dict[str, Any]) -> dict[str, Any]:
      try:
          import json as _json
          parent_id = (args.get("parent_id") or "").strip()
          if not parent_id:
              return _err("Brak parent_id.")
          parent_path = sm2.CARDS_DIR / f"{parent_id}.md"
          if not parent_path.exists():
              return _err(f"Nie znaleziono karty-rodzica: {parent_id}")
          parent = sm2.load_card(parent_path)

          # Inherit from parent
          source_path = (args.get("source_path") or parent.meta.get("source") or "").strip()
          tags_csv = args.get("tags") or ",".join(parent.tags)
          tags = [t.strip() for t in tags_csv.split(",") if t.strip()]
          if "cloze" not in tags:
              tags.append("cloze")
          priority = int(args.get("priority") or parent.meta.get("priority") or 50)
          difficulty = (args.get("difficulty") or parent.meta.get("difficulty") or "medium").strip()

          clozes_raw = args.get("clozes") or "[]"
          try:
              clozes_list = _json.loads(clozes_raw)
          except _json.JSONDecodeError as e:
              return _err(f"'clozes' musi być JSON-listą obiektów {{front, back}}: {e}")
          if not isinstance(clozes_list, list) or not clozes_list:
              return _err("'clozes': oczekiwana niepusta lista obiektów {front, back}.")

          created_ids: list[str] = []
          n = len(clozes_list)
          for idx, c in enumerate(clozes_list, 1):
              front = (c.get("front") or "").strip()
              back = (c.get("back") or "").strip()
              if not front or not back:
                  return _err(f"Cloze #{idx}: 'front' i 'back' są wymagane i niepuste.")
              cc = ClozeCard(
                  title=f"{parent.title} [cloze {idx}/{n}]",
                  parent_id=parent_id,
                  front=front,
                  back=back,
                  source_path=source_path,
                  tags=tags,
                  priority=priority,
                  difficulty=difficulty,
              )
              body = card_io.build_cloze_body(cc)
              card = sm2.write_new_card(
                  title=cc.title,
                  body=body,
                  type="cloze",
                  source=cc.source_path,
                  quest=parent.quest or None,
                  tags=cc.tags,
                  difficulty=cc.difficulty,
                  priority=cc.priority,
                  extra={"parent_id": parent_id},
              )
              created_ids.append(card.id)

          sm2.export_index()
          return _ok(f"Zapisano {len(created_ids)} cloze'ów: " + ", ".join(created_ids))

      except Exception as e:
          return _err(f"Błąd zapisu cloze'ów: {e}")

  _add_clozes_tool = tool(
      "add_clozes",
      "Tworzy N kart 'cloze' (proste Q&A, bez limitu) podpiętych przez parent_id. 'clozes' to JSON-lista {front, back}. Tagi/priority/difficulty dziedziczą z rodzica gdy puste.",
      {
          "parent_id": str,
          "clozes": str,       # JSON: [{"front": "...", "back": "..."}, ...]
          "source_path": str,
          "tags": str,
          "priority": int,
          "difficulty": str,
      },
  )(add_clozes)
  ```
- Dorzuć do `learning_tools_server` i `__all__`.
- Import `ClozeCard` na górze: `from modules.models import RoundCard, ClozeCard`.

### 5. Patch list_cards: filtr parent_id

- **Task ID**: tool-list-cards-parent
- **Depends On**: tool-add-clozes
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- W `list_cards` (modules/tools.py) dorzuć filtr:
  ```python
  parent = (args.get("parent_id") or "").strip()
  if parent:
      cards = [c for c in cards if (c.meta.get("parent_id") or "") == parent]
  ```
- Dorzuć `"parent_id": str` do schematu `_list_cards_tool`.

### 6. Patch export_anki: branch po type=cloze

- **Task ID**: tool-export-anki-cloze
- **Depends On**: tool-add-clozes
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: true (z task 5)
- W pętli `for c in cards` w `export_anki`:
  ```python
  if c.type == "cloze":
      # Minimalistyczne ciało: ## Pytanie / ## Odpowiedź
      front_text = _extract_section(c.body, "Pytanie")
      back_text  = _extract_section(c.body, "Odpowiedź")
      rows.append("\t".join([
          _csv_escape(front_text),
          _csv_escape(back_text),
          _csv_escape(",".join(c.tags)),
      ]))
      continue
  ```
- Dodaj helper `_extract_section(body: str, heading: str) -> str` — zwraca tekst sekcji `## {heading}` aż do następnego `## ` lub końca stringa. Może reuse'ować logikę z `parse_body` lub być prostą pętlą nad liniami.

### 7. Wire-up REPL: allowed_tools + /tree + /parent

- **Task ID**: wire-repl
- **Depends On**: tool-read-card, tool-add-clozes
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- W `learn_agent.py`, w `self.allowed_tools` dodaj:
  ```python
  "mcp__learning__read_card",
  "mcp__learning__add_clozes",
  ```
- Dorzuć dwa nowe slash command handlery:
  ```python
  async def _cmd_tree(repl: LearningAgentREPL, args: str) -> bool:
      card_id = args.strip()
      if not card_id:
          console.print("[yellow]Uzycie: /tree <card_id>[/yellow]")
          return True
      prompt = (
          f"Wywolaj read_card(card_id='{card_id}') i pokaz te karte. "
          f"Nastepnie wywolaj list_cards(parent_id='{card_id}') i pokaz jej "
          f"cloze'y jako wypunktowana liste (id + front). "
          f"Format: najpierw pelna karta, ponizej 'Cloze'e ({len} szt.): [lista]'."
      )
      await repl.process_query(prompt, display=f"/tree {card_id}")
      return True

  async def _cmd_parent(repl: LearningAgentREPL, args: str) -> bool:
      card_id = args.strip()
      if not card_id:
          console.print("[yellow]Uzycie: /parent <card_id>[/yellow]")
          return True
      prompt = (
          f"Wywolaj read_card(card_id='{card_id}'). "
          f"Jesli karta ma parent_id w frontmatterze, wywolaj tez "
          f"read_card(card_id=parent_id) i pokaz karte-rodzica (Tytul + Sedno). "
          f"Jesli parent_id brak, pokaz tylko te karte."
      )
      await repl.process_query(prompt, display=f"/parent {card_id}")
      return True
  ```
- Dodaj oba do `SLASH_COMMANDS` dict i do `SLASH_HELP_ROWS` (opisy: `/tree <card_id>` — karta + jej cloze'e; `/parent <card_id>` — karta i jej rodzic).

### 8. Prompts: REVIEW_SESSION branch po type + skróty nawigacyjne

- **Task ID**: prompts-review
- **Depends On**: tool-read-card, tool-add-clozes (API musi być znane)
- **Assigned To**: builder-prompts
- **Agent Type**: general-purpose
- **Parallel**: false
- `prompts/REVIEW_SESSION.md`, w Kroku 2, przed krokiem 2a dodaj podsekcję „2.0. Branch po type":

  > **Sprawdź `type` karty przed wyświetleniem przodu.**
  >
  > - `type ∈ {concept, framework, side-question, pitfall, example, principle, tool}` → standardowy flow 2a-2e.
  > - `type = cloze` → **uproszczony flow 2c-cloze** poniżej.

  Dodaj podsekcję „2c-cloze. Cloze — prosty flow":
  ```
  === KARTA <id> [cloze] ===

  <front>
  ```
  Zaproś: "Spróbuj odpowiedzieć. Gdy gotowy: odpowiedź lub 'pokaż'."

  Po próbie odpowiedzi pokaż:
  ```
  === ODPOWIEDŹ ===

  <back>

  ↑ p — karta-rodzic (<parent_id>)   t — drzewo (rodzic + rodzeństwo)
  ```
  Soft-shortcuty:
  - Jeśli user wpisze `p` lub `parent` — wywołaj `read_card(card_id=parent_id)` i pokaż Tytuł + Sedno. Następnie wróć do pytania o ocenę.
  - Jeśli user wpisze `t` lub `tree` — wywołaj `read_card(parent_id)` + `list_cards(parent_id=parent_id)` i pokaż drzewo. Wróć do oceny.
  - Jeśli user wpisze ocenę 0-5 — przejdź normalnie do `record_review`.

  Ocena 0-5 → `record_review` jak zawsze.
- W „Antywzorce": „Wyświetlanie 11 sekcji dla `type=cloze` — łamie *minimum information principle*. Cloze ma tylko `front` i `back`."

### 9. Tests: smoke e2e dla cloze

- **Task ID**: tests-smoke-cloze
- **Depends On**: tool-add-clozes, tool-list-cards-parent, tool-export-anki-cloze, tool-read-card
- **Assigned To**: builder-tests
- **Agent Type**: general-purpose
- **Parallel**: false
- W `tests/smoke_e2e.py` dorzuć po sekcji 6 (guards):
  ```python
  import json as _json  # już jest w stdlib, tylko dla pewności

  from modules.tools import add_clozes, read_card  # noqa: WPS433

  # ---------- 7. add_clozes happy path (8 cloze — brak górnego limitu) ----------
  big_batch = [
      {"front": f"Pytanie numer {i}?", "back": f"Odpowiedz {i}"}
      for i in range(1, 9)
  ]
  cloze_res = await add_clozes({
      "parent_id": card_id,
      "clozes": _json.dumps(big_batch),
  })
  assert cloze_res.get("is_error") is not True, f"add_clozes failed: {cloze_res}"
  all_files = list((TEST_DIR / "cards").glob("*.md"))
  cloze_cards = [
      frontmatter.load(p) for p in all_files
      if frontmatter.load(p).metadata.get("type") == "cloze"
  ]
  assert len(cloze_cards) == 8, f"expected 8 cloze cards, got {len(cloze_cards)}"
  for cc in cloze_cards:
      m = cc.metadata
      assert m.get("parent_id") == card_id, f"wrong parent_id: {m.get('parent_id')}"
      assert "sm2" in m and m["sm2"].get("next_review"), f"missing sm2: {m}"
      assert "cloze" in (m.get("tags") or []), f"tag 'cloze' missing: {m.get('tags')}"
      body = cc.content
      assert "## Pytanie" in body, f"missing ## Pytanie in cloze body"
      assert "## Odpowiedź" in body, f"missing ## Odpowiedź in cloze body"
      assert "## Karta-rodzic" in body, f"missing ## Karta-rodzic in cloze body"
      # Upewnij się, że body nie zawiera tekstu z rodzica
      assert "Kontekst testowy" not in body, "cloze body should NOT copy parent context"
  print(f"[smoke] add_clozes ok, 8 cloze cards, no parent text leaked")

  # ---------- 8. list_cards filter parent_id ----------
  lc = await list_cards({"parent_id": card_id})
  assert lc.get("is_error") is not True
  lc_text = lc["content"][0]["text"]
  assert "cloze" in lc_text.lower(), f"no cloze in list_cards parent filter: {lc_text[:200]}"
  print("[smoke] list_cards parent_id ok")

  # ---------- 9. read_card ----------
  rc = await read_card({"card_id": card_id})
  assert rc.get("is_error") is not True, f"read_card failed: {rc}"
  rc_text = rc["content"][0]["text"]
  assert card_id in rc_text, f"card_id not in read_card output"
  assert "Sedno" in rc_text or "Pytanie sprawdzające" in rc_text, "read_card seems wrong"
  print("[smoke] read_card ok")

  # read_card for cloze — should show parent_id line
  first_cloze_id = cloze_cards[0].metadata["id"]
  rc2 = await read_card({"card_id": first_cloze_id})
  assert rc2.get("is_error") is not True
  rc2_text = rc2["content"][0]["text"]
  assert card_id in rc2_text, "parent_id not shown in read_card output for cloze"
  print("[smoke] read_card cloze (parent_id visible) ok")

  # ---------- 10. export_anki cloze branch ----------
  exp2 = await export_anki({"filename": "smoke-cloze", "scope": "all"})
  assert exp2.get("is_error") is not True
  csv2 = (TEST_DIR / "exports" / "smoke-cloze.csv").read_text(encoding="utf-8")
  rows_all = [r for r in csv2.strip().splitlines() if r.strip()]
  # 1 rich card + 8 cloze = 9 rows
  assert len(rows_all) == 9, f"expected 9 rows, got {len(rows_all)}: {rows_all}"
  # Cloze rows should NOT contain "Kontekst:" prefix (that's rich card format)
  cloze_rows = rows_all[1:]  # first is rich, rest cloze (order may vary; just count)
  print(f"[smoke] export_anki cloze branch ok ({len(rows_all)} rows)")

  # ---------- 11. Guard: empty front ----------
  bcr = await add_clozes({
      "parent_id": card_id,
      "clozes": _json.dumps([{"front": "", "back": "x"}]),
  })
  assert bcr.get("is_error") is True, "guard nie zadziałał na pusty front"
  print("[smoke] guard ok: empty cloze front rejected")
  ```

### 10. Validation

- **Task ID**: validate-all
- **Depends On**: wszystkie poprzednie
- **Assigned To**: builder-tests
- **Agent Type**: general-purpose
- **Parallel**: false
- Uruchom: `uv run python -m py_compile modules/models.py modules/card_io.py modules/tools.py learn_agent.py tests/smoke_e2e.py` — brak output'u = OK.
- Uruchom: `uv run python tests/smoke_e2e.py` — oczekiwane `PASS`.
- Walidacja promptów:
  - `grep -n "add_clozes" prompts/SYSTEM_PROMPT.md prompts/LEARN_QUEST.md prompts/LEARN_FILE.md` — każdy plik ≥1 hit.
  - `grep -n "type.*cloze\|cloze.*type" prompts/REVIEW_SESSION.md` — ≥1 hit.
  - `grep -n "read_card" prompts/REVIEW_SESSION.md` — ≥1 hit (agent woła read_card dla `p`/`t`).
  - `ls prompts/CLOZE_RULES.md` — plik istnieje.
  - `grep -c "front" prompts/CLOZE_RULES.md` — ≥1 (są przykłady cloze z frontem).
- Pokaż `git diff --stat` — oczekiwane ~10 plików: 3 moduły + 1 REPL + 4 istniejące prompty + 1 nowy prompt + 1 test.

## Acceptance Criteria

- [ ] `ClozeCard` w `modules/models.py` — pola `title`, `parent_id`, `front`, `back`, `source_path`, `tags`, `priority`, `difficulty`. Brak `source_quote` i sekcji kontekstowych.
- [ ] `build_cloze_body` zwraca **wyłącznie** sekcje `## Pytanie`, `## Odpowiedź`, `## Karta-rodzic [[parent_id]]`. Zero duplikacji tekstu z rodzica.
- [ ] MCP tool `read_card` zarejestrowany. Przyjmuje `card_id`. Zwraca frontmatter + body. Dla cloze pokazuje `parent_id`.
- [ ] MCP tool `add_clozes` zarejestrowany. **Brak górnego limitu** na liczbę cloze'ów. Guards: niepuste `parent_id` + istniejący parent + niepuste `front` + niepuste `back`.
- [ ] Karty cloze: `type=cloze`, `parent_id`, tag `cloze`, własny `sm2:` z `next_review`.
- [ ] `list_cards` przyjmuje `parent_id` jako filtr.
- [ ] `export_anki` produkuje `front\tback\ttags` dla `type=cloze`.
- [ ] `learn_agent.py`: `mcp__learning__read_card` i `mcp__learning__add_clozes` w `allowed_tools`, handlery `/tree` i `/parent` w `SLASH_COMMANDS`, obie komendy w `SLASH_HELP_ROWS`.
- [ ] `prompts/CLOZE_RULES.md` istnieje: tabela triggerów, zasada atomowości, przykłady.
- [ ] `SYSTEM_PROMPT.md`, `LEARN_QUEST.md`, `LEARN_FILE.md` — każdy ma instrukcję o `add_clozes` po `add_card_full`, bez limitu ilości.
- [ ] `REVIEW_SESSION.md` — branch `type=cloze` z uproszczonym flow. Soft-shortcuty `p`/`t` → `read_card`. NIE pokazuje 11 sekcji dla cloze.
- [ ] Smoke sekcje 7-11 zielone. `PASS` na `uv run python tests/smoke_e2e.py`.

## Validation Commands

Execute these commands to validate the task is complete:

- `uv run python -m py_compile modules/models.py modules/card_io.py modules/tools.py learn_agent.py tests/smoke_e2e.py`
- `uv run python tests/smoke_e2e.py`
- `grep -n "add_clozes" prompts/SYSTEM_PROMPT.md prompts/LEARN_QUEST.md prompts/LEARN_FILE.md`
- `grep -n "type.*cloze" prompts/REVIEW_SESSION.md`
- `grep -n "read_card" prompts/REVIEW_SESSION.md`
- `ls prompts/CLOZE_RULES.md`
- `uv run python -c "from modules.models import ClozeCard; ClozeCard(title='t', parent_id='p', front='f', back='b'); print('ok')"`
- `uv run python -c "from modules.tools import read_card, add_clozes; print('ok')"`

## Notes

- **Zero nowych zależności** — wszystko stoi na `pydantic`, `python-frontmatter`, `claude_agent_sdk`.
- **Brak górnego limitu** na cloze'y jest świadomy. SuperMemo generuje po kilka cloze'ów z każdego zdania długiego materiału. Kontrolę sprawuje agent przez triggery, nie kod. Jeśli w praktyce agent generuje zbyt dużo lub zbyt mało — koryguj CLOZE_RULES.md, nie koduj limitu.
- **Tag `cloze` automatycznie dopisywany** w `add_clozes` — żeby `list_cards(tag='cloze')` działało out-of-the-box.
- **`read_card` jako narzędzie nawigacyjne, nie tylko review.** Przydatny też gdy użytkownik pyta "pokaż mi kartę X z wczoraj" w dowolnym momencie sesji — agent może go wywołać bez `Glob`/`Read`.
- **Soft-shortcuty `p`/`t` w REVIEW** są prompt-level (agent interpretuje), nie REPL-level. Oznacza to, że `p` będzie działać tylko gdy agent wygeneruje hint i użytkownik wpisze to w odpowiednim kontekście. Dla nawigacji poza review — są slash commands `/parent` i `/tree`.
- **Skill `learning-aiph-quests`** — karty cloze pojawią się w `learning/cards/` i skill je odczyta. Jego review.py nie zna branchu po type, więc cloze będzie reviewowane jak zwykła karta (pokaże raw body). Osobny plan jeśli potrzeba.
- **Manualny sanity** zalecany: `just run` → `/learn "Outcome w OST"` → sprawdzić czy agent po `add_card_full` woła `add_clozes` z terminami "Outcome", "Key Result", datami itp.
