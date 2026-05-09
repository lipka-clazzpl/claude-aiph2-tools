# AIPH2 Active Learning Agent

## Co to jest

Pythonowy REPL do **aktywnej nauki** materiałów kursu **AI Product Heroes 2**. Zamiast czytać slajdy biernie, przerabiasz je z agentem według pięciu kroków: **intuicja → konkret → why/tradeoff/pitfall → szersza perspektywa → pytanie sprawdzające**.

- każdy koncept zapisuje się jako fiszka w `aiph2/learning/cards/`
- powtórki rozłożone w czasie (algorytm **SM-2**, ocena 0–5)
- profil zainteresowań sam podnosi priorytet tematów, do których wracasz
- ta sama baza kart co skill `learning-aiph-quests` — karty są wymienne w obie strony

## Demo

![demo](./demo.gif)

## Instalacja

```bash
cd aiph2/learn-agent && just install
```

Wymagania: Python ≥3.11, [`uv`](https://docs.astral.sh/uv/), `ANTHROPIC_API_KEY`. `just install`:

1. uruchamia `uv sync` (instaluje `claude-agent-sdk`, `rich`, `python-frontmatter`, `PyYAML`, `python-docx`),
2. kopiuje `.env.sample → .env` jeśli `.env` jeszcze nie istnieje (`cp -n`, nie nadpisuje),
3. przypomina o uzupełnieniu `ANTHROPIC_API_KEY` w `.env`.

Po instalacji edytuj `.env` i wpisz klucz:

```env
ANTHROPIC_API_KEY=sk-ant-...
AIPH2_LEARNING_DIR=         # opcjonalnie, domyślnie ../learning/
```

## Uruchomienie

```bash
# tryb interaktywny (REPL)
just run

# one-shot — od razu /learn-quest <slug>
just run-day w1d2-2026-04-22-fundamenty
```

Pierwsza interakcja: agent wczytuje `interest-profile.md`, proponuje plan dnia, pyta o akceptację, przechodzi przez koncepty według 5 zasad. Po każdym koncepcie zapisuje pełną kartę do `aiph2/learning/cards/`.

## Slash commands

| Komenda | Opis |
|---|---|
| `/learn <topic>` | Wolny temat (Polish prompt do agenta, bez wczytywania pliku) |
| `/learn-file <path>` | Nauka z pojedynczego pliku (`.md` / `.txt` / `.docx`) |
| `/learn-web <url>` | Nauka z URL (agent pobiera przez `WebFetch`) |
| `/learn-quest <slug>` | Quest dnia — wczytuje `aiph2/weeks/<slug>/{transcripts,slides,materials}/` |
| `/due` | Lista kart zaległych do powtórki dziś |
| `/review` | Pętla powtórki w stylu SuperMemo (front-only → odpowiedź → ocena 0-5) |
| `/cards [filter]` | Listuje karty z filtrami (quest, tag, type, query) |
| `/interest [topic priority]` | Ręczne nadpisanie priorytetu tematu w profilu zainteresowań |
| `/save-anki [name]` | Eksport kart do CSV zgodnego z Anki |
| `/stats` | Statystyki sesji (liczba kart, sygnałów, tokenów) |
| `/clear` | Czyści kontekst rozmowy |
| `/help` | Pokazuje listę komend |
| `/exit` | Kończy sesję |

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `ANTHROPIC_API_KEY` | (wymagana) | Klucz do API Claude |
| `AIPH2_LEARNING_DIR` | `../learning/` | Katalog bazy kart (override względem default `aiph2/learning/`) |

## Porównanie z `learning-aiph-quests` skill

Oba narzędzia uczą tego samego kursu i piszą do tej samej bazy kart, ale różnią się trybem pracy:

| Aspekt | learn-agent | learning-aiph-quests skill |
|---|---|---|
| Kontekst | własny proces, niezakłócany przez inne zadania | dzieli kontekst Claude Code z resztą sesji |
| UI | Rich + Polish REPL | tekst w terminalu Claude Code |
| Sesja | długa, interaktywna (godziny), z planem dnia | krótka, ad-hoc, na zadanie |
| Wejście | `just run` lub `just run-day <slug>` | wywołanie `/learning-aiph-quests` w Claude Code |
| Wywoływanie narzędzi | MCP server (`add_card_full`, `record_review`, ...) | bash skrypty (`add_card.py`, `review.py`, ...) |
| Karty | wspólne `aiph2/learning/cards/` | wspólne `aiph2/learning/cards/` |
| Profil zainteresowań | tak (`interest-profile.md`, auto-tracking) | nie |
| Kiedy używać | "Siadam na 2h, przerabiamy dzień 5" | "Mam pytanie z kursu w środku innej pracy" |

Karty zapisane przez agenta są **bidirectionally** kompatybilne ze skillem (skill je odczytuje i powtarza tak samo, agent czyta karty zapisane przez skill).

## Architektura

- **REPL (`learn_agent.py`)** — `LearningAgentREPL` na `ClaudeSDKClient`, slash command dispatch, streaming-render.
- **Moduły (`modules/`)** — `sm2` (vendor z skill'a, env-aware `LEARNING_DIR`), `models` (Pydantic: `RoundCard`, `InterestTopic`, `InterestProfile`, `SessionStats`), `card_io` (body builder/parser), `interest` (profil), `streaming_display` (Rich live panel), `tools` (10 MCP tools).
- **Prompty (`prompts/`)** — `SYSTEM_PROMPT.md` (5 zasad + IL + tool inventory), `LEARN_QUEST.md`, `LEARN_FILE.md`, `REVIEW_SESSION.md`, `INTEREST_SIGNALS.md`.

## Layout danych

Agent czyta źródła z `aiph2/weeks/` i pisze karty + profil zainteresowań do `aiph2/learning/`. Oba katalogi są **rówieśnikami** `learn-agent/` (relatywnie do `aiph2/`):

```
aiph2/
├── learn-agent/          # ten projekt (REPL + moduły)
├── learning/             # baza wiedzy (zapisywana tu, czytana też przez skill)
│   ├── manifest.md       # opis konwencji bazy
│   ├── index.json        # auto-generowany indeks kart
│   ├── interest-profile.md   # profil zainteresowań (topics + priority + signals)
│   ├── cards/            # karty IL (jedna karta = jeden plik markdown)
│   └── exports/          # CSV dla Anki, eksporty PDF
└── weeks/                # źródłowe materiały kursu (input do /learn-quest)
    └── w1d2-2026-04-22-fundamenty/
        ├── transcripts/  # transcript.md, transcript-raw.{md,txt}
        ├── slides/       # *.md, *.pdf
        └── materials/    # *.docx, *.skill (zadania, side-questy)
```

`AIPH2_LEARNING_DIR` może wskazać inny katalog bazy (domyślnie `../learning/` względem `learn-agent/`).

## Linki

- System prompt: [`prompts/SYSTEM_PROMPT.md`](prompts/SYSTEM_PROMPT.md)
- Sygnały zainteresowania: [`prompts/INTEREST_SIGNALS.md`](prompts/INTEREST_SIGNALS.md)
- Skill alternatywny: [`aiph2/.claude/skills/learning-aiph-quests/SKILL.md`](../.claude/skills/learning-aiph-quests/SKILL.md)
