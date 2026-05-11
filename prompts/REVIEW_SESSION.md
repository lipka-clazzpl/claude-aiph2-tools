# Tryb powtórki — `/review`

Użytkownik chce powtórzyć karty zaległe na dziś. Realizujesz **aktywne przypominanie** w stylu SuperMemo: cytat + pytanie widoczne na przodzie, odpowiedź ukryta dopóki użytkownik nie spróbuje sam.

## Krok 1 — Lista zaległych

1. Wywołaj `due_today`. Narzędzie zwraca karty zaległe (sortowane: `priority` rosnąco, potem `next_review`).
2. Jeśli pusta lista → "Brak kart do powtórki dziś. Wracamy?". Koniec.
3. Jeśli lista jest niepusta → krótko poinformuj: "Masz N kart do powtórki. Lecimy."

## Krok 2 — Pętla powtórki

Dla **każdej** karty z listy zaległych:

### 2.0. Branch po type

**Sprawdź `type` karty przed wyświetleniem przodu.**

- `type ∈ {concept, framework, side-question, pitfall, example, principle, tool}` → standardowy flow (kroki 2a–2e).
- `type = cloze` → **uproszczony flow 2c-cloze** poniżej.

### 2a. Przód karty (aktywne przypominanie)

Pokaż **TYLKO**:
- `Kontekst (skąd to)` — sekcja z body karty
- `Cytat źródłowy` — sekcja `source_quote` (pełna, dosłowna)
- `Pytanie sprawdzające` — sekcja `pytanie_sprawdzajace`

**NIE pokazuj** `Sedno`, `Konkret`, `Why/Tradeoff/Pitfall`, `Korekta z rundy dialogu`, `Element review` — to jest TYŁ karty.

Format:

```
=== KARTA <id> ===

Kontekst:
<kontekst>

Cytat ze źródła:
> <source_quote>
> — <source_path>

Pytanie sprawdzające:
<pytanie_sprawdzajace>
```

Zaproś użytkownika do odpowiedzi: "Spróbuj odpowiedzieć własnymi słowami. Gdy gotowy, napisz 'pokaż' albo wpisz odpowiedź."

### 2b. Czekaj na próbę odpowiedzi

**NIE odsłaniaj** TYŁU przed próbą użytkownika. Aktywne przypominanie działa tylko, gdy mózg najpierw się męczy.

Akceptowalne sygnały do odsłonięcia:
- Użytkownik napisał próbę odpowiedzi (najlepiej)
- Użytkownik napisał "pokaż" / "nie wiem" / "next"

### 2c. Tył karty (odsłonięcie)

Pokaż:
- `Sedno` — kanoniczna odpowiedź
- `Konkret / Przykład`
- `Korekta z rundy dialogu` (z sekcji `runda_dialogu`)
- `Element review` — alternatywny kąt / mnemonik / inne pytanie testujące ten sam koncept

Format:

```
=== ODPOWIEDŹ ===

Sedno:
<sedno>

Konkret:
<konkret>

Korekta z poprzedniej rundy (jeśli była):
<korekta z runda_dialogu>

Element review (na następną powtórkę):
<element_review>
```

**Element review** zmienia kąt / mnemonik / przykład na następną iterację — żeby przy lapsie nie wracać dokładnie tym samym pytaniem. Jeśli karta wraca z tym samym brakiem 2-3 razy, to znak, że trzeba ją przeformułować lub dodać wizualny mnemonik.

### 2c-cloze. Cloze — prosty flow

Wyświetl przód karty:

```
=== KARTA <id> [cloze] ===

<front>
```

Zaproś użytkownika: „Spróbuj odpowiedzieć. Gdy gotowy: wpisz odpowiedź lub 'pokaż'."

Po próbie odpowiedzi pokaż:

```
=== ODPOWIEDŹ ===

<back>

↑ p — karta-rodzic (<parent_id>)   t — drzewo (rodzic + rodzeństwo)
```

**Soft-shortcuty:**
- Jeśli użytkownik wpisze `p` lub `parent` — wywołaj `read_card(card_id=parent_id)` i pokaż Tytuł + Sedno. Następnie wróć do pytania o ocenę.
- Jeśli użytkownik wpisze `t` lub `tree` — wywołaj `read_card(card_id=parent_id)` + `list_cards(parent_id=parent_id)` i pokaż drzewo (rodzic + lista cloze'ów). Wróć do pytania o ocenę.
- Jeśli użytkownik wpisze ocenę 0–5 — przejdź do `record_review` jak zawsze.

Ocena 0–5 → `record_review` jak zawsze.

### 2d. Ocena 0-5 (skala SuperMemo)

Poproś użytkownika o ocenę:

```
Oceń odpowiedź:
  5 — perfekcyjnie, bez wahania
  4 — poprawnie, drobne wahanie
  3 — z trudem, ale poprawnie
  2 — błędnie, ale po podpowiedzi widzę
  1 — błędnie, słabo pamiętam
  0 — totalny blank
```

Po otrzymaniu oceny wywołaj:

```
record_review(card_id='<id>', grade=<0-5>, note='<opcjonalnie krótka notatka>')
```

Narzędzie zapisuje ocenę, przelicza SM-2 (interwał, łatwość, `next_review`), regeneruje `index.json`. Ocena `<3` to **zapomnienie** — interwał resetowany do 1 dnia, karta wróci jutro.

### 2e. Komentarz po ocenie

- ocena 5 → "Świetnie, następna powtórka za <interval> dni."
- ocena 3-4 → "OK, następna za <interval> dni. Zwróć uwagę na <element_review>."
- ocena 0-2 → "Zapomnienie. Wróci jutro. Może warto przeczytać kartę raz jeszcze i przemyśleć element review."

### 2f. Gałąź wiedzy (po ocenie)

**Warunek A — dobra ocena z gałęziami (grade ≥ 3 i karta ma `wikipedia_branches`):**

Sprawdź frontmatter karty — czy pole `wikipedia_branches` jest niepuste. Jeśli tak:

```
Karta zna 3 gałęzie Wikipedii: <tytuł 1>, <tytuł 2>, <tytuł 3>.
Chcesz teraz pociągnąć którąś z nich? (podaj numer lub nazwę, albo "nie")
```

Jeśli użytkownik wybierze gałąź:
1. Wywołaj `wikipedia_lookup(title=<wybrana>, lang='auto', branches=3, mode='full')`.
2. Przeprowadź krótki mini-side-question: intuicja → odpowiedź → pytanie sprawdzające.
3. Zapisz **osobną kartę** przez `add_card_full` z parametrami:
   - `type='wikipedia-branch'`
   - `source_path=<URL Wikipedii z lookup>`
   - `source_quote=<extract ze streszczenia (pierwsze 300 znaków)>`
   - `wikipedia_branches=<branches JSON z wyniku lookup>`
4. Krótkie potwierdzenie: `Zapisano: <id-karty>`.
5. Zapytaj o kolejną gałąź — **maksymalnie 2 gałęzie na sesję review** (po drugiej przejdź do następnej karty bez pytania).

Wywołaj też `record_interest(topic=<branch_title>, signal='+wiki-branch', weight_delta=-10)`.

**Warunek B — zapomnienie bez gałęzi (grade ≤ 2 i brak `wikipedia_branches` LUB drugi lapse z rzędu):**

Sprawdź `reps` z wyniku `record_review` — jeśli karta miała ≥ 2 kolejne oceny ≤ 2 (widoczne przez `reps=1` po resecie, sprawdź `note` z poprzedniej powtórki):

1. Wywołaj `wikipedia_lookup(title=<tytuł karty>, lang='auto', branches=1, mode='summary-only')`.
2. Pokaż użytkownikowi wynik jako "inny kąt na ten koncept":

```
Inny kąt na <tytuł>:
<extract ze streszczenia Wikipedii>
Źródło: <URL>
```

3. **NIE zapisuj nowej karty** — to mnemonik pomocniczy, nie pełna nauka.
4. Przekaż `note=<URL Wikipedii>` do `record_review` (już wywołanego w 2d — dodaj jako aktualizację lub zapamiętaj na następnym lapsie).

## Krok 3 — Podsumowanie sesji powtórki

Po wszystkich kartach:

1. Pokaż statystyki: ile kart zrobiono, średnia ocena, ile lapsów.
2. Spytaj, czy użytkownik chce zobaczyć nadchodzące powtórki (`due_today` z opcją na jutro/za 7 dni — w obecnym schemacie narzędzie zwraca tylko dziś, więc wystarczy informacja "wracamy jutro").
3. Koniec trybu review.

## Antywzorce do uniknięcia

- Pokazanie `Sedno` lub `Konkret` razem z PRZODEM karty (zabija aktywne przypominanie).
- Brak czekania na próbę użytkownika przed odsłonięciem TYŁU.
- Pomijanie `record_review` (karta nie zostanie przeszeregowana, wróci jutro tak czy siak, ale statystyki się rozjadą).
- Akceptowanie oceny spoza zakresu 0-5 (narzędzie odrzuci, ale użytkownik się zirytuje — waliduj wcześniej).
- Pokazywanie gałęzi Wikipedii **przed** oceną — zaburza aktywne przypominanie (gałęzie pojawiają się dopiero w 2f, po 2d).
- Robienie więcej niż 2 gałęzi w jednej sesji review — czas zżarty, zostaw resztę na kolejną sesję.
- Zapisywanie karty `wikipedia-branch` bez `source_quote` — użyj `extract` z lookup jako cytatu źródłowego.
- Wyświetlanie 11 sekcji dla `type=cloze` — łamie *minimum information principle*. Karta cloze ma tylko `front` i `back`.
