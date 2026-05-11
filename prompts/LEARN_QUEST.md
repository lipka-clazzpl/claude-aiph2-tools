# Nauczanie z questa AIPH2 — `/learn-quest <slug>`

Użytkownik chce się uczyć z konkretnego dnia kursu. Slug ma format `w<N>d<M>-YYYY-MM-DD-<temat>` (np. `w1d2-2026-04-22-fundamenty`).

Slug: `{slug}`

## Krok 0 — Profil zainteresowań

1. Wywołaj `read_interest_profile`. Zapamiętaj listę tematów + ich priorytety.
2. Jeśli profil pusty → traktuj sesję jako neutralną (priorytet domyślny 50 dla każdego nowego konceptu).
3. Jeśli któryś z tematów dnia ma w profilu priorytet 0-30 (`priority` w frontmatter) — sygnalizuj sobie, że pisze się **rozbudowane** karty.

## Krok 1 — Wczytanie materiałów questa

1. Wywołaj `load_quest_materials(slug='{slug}')`. Narzędzie zwraca skonsolidowany tekst z `transcripts/`, `slides/`, `materials/*.docx`.
2. Jeśli narzędzie zwróciło błąd ("Nie znaleziono katalogu questa") → przyznaj się i spytaj użytkownika o poprawny slug LUB sprawdź `Glob` po `aiph2/weeks/*` żeby zaproponować dostępne slugi.
3. Jeśli narzędzie zwróciło uciętą zawartość ("truncated") → ostrzeż użytkownika i zaproponuj kontynuację bez pełnego materiału, lub doczytanie z konkretnych plików przez `load_learning_material`.

## Krok 2 — Plan sesji

Po przeczytaniu materiałów wypisz krótko:

- **Główne questy** (z `materials/quest-*.docx`)
- **Side questy** (z `materials/side-quest-*.docx`)
- **Kluczowe koncepty z transkryptu** (np. "5 cech buildera", "Super Loop", "Lovable Plan vs Build", "Customer Curiosity")
- **Pytania Q&A z sesji** (jeśli są w transkrypcie i warte przerobienia)

Zaproponuj kolejność **od najprostszych do złożonych** i poproś użytkownika o akceptację lub modyfikację. Format:

> Plan na dziś:
> 1. <koncept A>
> 2. <koncept B>
> 3. <quest 1.X — zadanie praktyczne>
>
> Pasuje? Zmieniam kolejność, dodaję, usuwam coś?

**Czekaj na odpowiedź.** Bez akceptacji nie zaczynasz pętli nauczania.

## Krok 3-4 — Pętla nauczania konceptu

Dla **każdego** konceptu z planu, zgodnie z 5 zasadami z `SYSTEM_PROMPT.md`:

1. **Intuicja** — pytanie otwarte. "Co dla ciebie znaczy `<koncept>`? Do czego ze swojej pracy byś go przypiął?" Czekaj na odpowiedź.
2. **Definicja** — krótka, własnymi słowami, jednym akapitem.
3. **Konkret** — przypadek z kursu (Airbnb, Zappos, Konrad/kalkulator, Superhuman, Shopify) lub realistyczna sytuacja z jego firmy.
4. **Krok 3.5 — Wikipedia** — wywołaj `wikipedia_lookup(title=<koncept>, lang='auto', branches=3, mode='full')`. Z `extract` destyluj 1-2 zdania do sekcji `Szersza perspektywa`. Z `branches` wybierz 2-3 najtrafniejsze gałęzie (te które są naprawdę powiązane, nie generic) i zapamiętaj je do zapisu karty. Jeśli Wikipedia zwróciła błąd — pomiń cicho i przejdź dalej z pustą listą gałęzi.
5. **Why + Tradeoff + Pitfall** — minimum jeden punkt z każdej kategorii.
6. **Szersza perspektywa** — porównanie z Lean Startup / JTBD / Continuous Discovery / Working Backwards, wzbogacone 1-2 zdaniami z Wikipedii (jeśli lookup był udany).
7. **Pytanie sprawdzające** (aktywne przypominanie) — aplikacyjne, nie odtwórcze.
8. **Reakcja na odpowiedź:**
   - poprawna → krótkie potwierdzenie + Krok 5 (zapis karty) + następny koncept
   - częściowa → pochwała + dopytanie o brakujące elementy
   - błędna → wyjaśnienie + wskazówka + ponowne pytanie

### Pytania poboczne (auto-zapis)

W **dowolnym momencie** użytkownik może zadać pytanie poboczne. Wtedy:
1. Odpowiedz pełną sekcją (kontekst, sedno, przykład, why/tradeoff/pitfall, pytanie sprawdzające).
2. **Natychmiast** zapisz to jako kartę przez `add_card_full` z `type='side-question'` (cytat ze źródła + runda dialogu obowiązkowe).
3. Krótkie potwierdzenie: `Zapisano: <id-karty>`.
4. Wróć do głównego wątku.

## Krok 5 — Zapis karty (po koncepcie)

Wywołaj `add_card_full` z pełnym zestawem pól. Argumenty obowiązkowe:

- `title` — haczyk, odróżniający
- `type` — `concept` / `framework` / `pitfall` / `example` / `principle` / `tool` / `side-question`
- `quest` — slug questa (`{slug}`)
- `tags` — rozdzielone przecinkami, np. "super-loop,framework,fundamenty"
- `source_path` — `weeks/{slug}/transcripts/transcript.md` lub konkretny `.docx`
- `source_quote` — **dosłowny cytat** ze źródła (system odrzuca karty bez)
- `kontekst`, `sedno`, `konkret`
- `why_tradeoff_pitfall`, `szersza_perspektywa`
- `runda_dialogu` — `Agent zapytał: ... / Odpowiedziałeś: ... / Korekta: ...`
- `pytanie_sprawdzajace` — system odrzuca karty bez
- `element_review` — alternatywne pytanie / mnemonik na następną powtórkę
- `wikipedia_branches` — JSON-encoded lista gałęzi z Kroku 3.5, np. `'[{"title":"Lean Startup","url":"https://...","summary":"...","lang":"pl"}]'`. Jeśli Wikipedia nie miała hasła → przekaż `'[]'`.
- `priority` — 0-100, na podstawie profilu zainteresowań (0-30 wysokie, 31-70 standardowe, 71-100 niskie)

Po zapisie krótkie potwierdzenie: `Zapisano: <id-karty>`.

Po udanym `add_card_full` oceń ile cloze'ów należy wygenerować. Minimum: 1 (definicja terminu tytułowego). Bez górnego limitu — tyle ile sygnałów z sesji uzasadnia. Sygnały: data/rok w materiałach, konkretna liczba/KPI, termin słownikowy, właściwa nazwa po raz pierwszy, pytanie poboczne użytkownika, para kontrastu (X vs Y), długa runda dialogu (≥3 tury). Im więcej sygnałów (≥3), tym więcej cloze'ów (≥5). Wywołaj `add_clozes`. Cloze body nie może powtarzać tekstu z karty-rodzica — tylko `front`, `back` i link.

## Krok 6 — Sygnały zainteresowania

W trakcie sesji obserwuj sygnały (patrz `INTEREST_SIGNALS.md`) i wywołuj `record_interest(topic, signal, weight_delta)` automatycznie. Przykłady:

- Użytkownik wraca do tematu drugi raz w sesji → `record_interest('<topic>', '+follow-up', -5)`
- Użytkownik mówi "pomiń" / "to już wiem" → `record_interest('<topic>', '+skip', +15)`
- Użytkownik zadaje pytanie z poziomu eksperckiego → `record_interest('<topic>', '+expert-question', -10)`

## Krok 7 — Podsumowanie sesji

Po wszystkich konceptach z planu:

1. Wywołaj `list_cards(quest='{slug}')` — pokaż użytkownikowi nowe karty z dzisiejszego questa.
2. Wywołaj `due_today` — zaproponuj powtórkę kart due (jeśli są) lub zostaw na jutro.
3. Spytaj: "Robimy powtórkę kart due teraz, czy zostawiamy na jutro?"

Jeśli użytkownik wybiera powtórkę — przejdź do trybu z `REVIEW_SESSION.md`.
