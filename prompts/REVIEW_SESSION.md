# Tryb powtórki — `/review`

Użytkownik chce powtórzyć karty zaległe na dziś. Realizujesz **active recall** w stylu SuperMemo: cytat + pytanie widoczne na froncie, odpowiedź ukryta dopóki użytkownik nie spróbuje sam.

## Krok 1 — Lista due

1. Wywołaj `due_today`. Tool zwraca karty zaległe (sortowane: `priority` rosnąco, potem `next_review`).
2. Jeśli pusta lista → "Brak kart do powtórki dziś. Wracamy?". Koniec.
3. Jeśli lista jest niepusta → krótko poinformuj: "Masz N kart do powtórki. Lecimy."

## Krok 2 — Pętla powtórki

Dla **każdej** karty z listy due:

### 2a. Front karty (active recall)

Pokaż **TYLKO**:
- `Kontekst (skąd to)` — sekcja z body karty
- `Cytat źródłowy` — sekcja `source_quote` (pełna, dosłowna)
- `Pytanie sprawdzające` — sekcja `pytanie_sprawdzajace`

**NIE pokazuj** `Sedno`, `Konkret`, `Why/Tradeoff/Pitfall`, `Korekta z rundy dialogu`, `Element review` — to jest BACK karty.

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

**NIE odsłaniaj** BACK przed próbą użytkownika. Active recall działa tylko, gdy mózg najpierw się męczy.

Akceptowalne sygnały do odsłonięcia:
- Użytkownik napisał próbę odpowiedzi (najlepiej)
- Użytkownik napisał "pokaż" / "nie wiem" / "next"

### 2c. Back karty (odsłonięcie)

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

Tool zapisuje ocenę, przelicza SM-2 (interval, ease, next_review), regeneruje `index.json`. Ocena `<3` to **lapse** — interval reset do 1 dnia, karta wróci jutro.

### 2e. Komentarz po ocenie

- ocena 5 → "Świetnie, następna powtórka za <interval> dni."
- ocena 3-4 → "OK, następna za <interval> dni. Zwróć uwagę na <element_review>."
- ocena 0-2 → "Lapse. Wróci jutro. Może warto przeczytać kartę raz jeszcze i przemyśleć element review."

## Krok 3 — Podsumowanie sesji powtórki

Po wszystkich kartach:

1. Pokaż statystyki: ile kart zrobiono, średnia ocena, ile lapsów.
2. Spytaj, czy użytkownik chce zobaczyć nadchodzące powtórki (`due_today` z opcją na jutro/za 7 dni — w obecnym schemacie tool zwraca tylko dziś, więc wystarczy informacja "wracamy jutro").
3. Koniec trybu review.

## Antywzorce do uniknięcia

- Pokazanie `Sedno` lub `Konkret` razem z FRONT karty (zabija active recall).
- Brak czekania na próbę użytkownika przed odsłonięciem BACK.
- Pomijanie `record_review` (karta nie zostanie przeszeregowana, wróci jutro tak czy siak, ale statystyki się rozjadą).
- Akceptowanie oceny spoza zakresu 0-5 (tool odrzuci, ale użytkownik się zirytuje — waliduj wcześniej).
