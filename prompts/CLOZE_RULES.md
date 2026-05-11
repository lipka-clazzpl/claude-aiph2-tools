# CLOZE_RULES — Zasady generowania kart cloze

## Kiedy generować

Wywołaj `add_clozes` bezpośrednio po każdym udanym `add_card_full`. Użyj poniższej tabeli, żeby ocenić ile cloze'ów jest potrzebnych:

| Sygnał w sesji | Cloze które powinny powstać |
|---|---|
| Pojawia się data lub rok (np. "Airbnb 2009", "2023") | Q: "Kiedy X?" A: rok |
| Pojawia się konkretna liczba / KPI (np. "38%→32%", "11 sekcji") | Q: "Jaki wskaźnik po X?" A: liczba |
| Pojawia się termin słownikowy w specyficznym kontekście | Q: "Co to X w kontekście Y?" A: krótka def. |
| Pojawia się właściwa nazwa (firma, narzędzie, nazwisko) po raz pierwszy | Q: "Z czym kojarzy się X?" A: kontekst kursu |
| Użytkownik dopytuje ("co to znaczy", "nie rozumiem", "a co jeśli...") | Extra cloze dla dopytanego termin/faktu |
| Pojawia się para kontrastu (X vs Y, X prowadzi do Y, X bez X → Y) | Cloze dla każdej strony pary |
| Długa runda dialogu (≥3 tury zanim user odpowiedział poprawnie) | Dodatkowe cloze dla każdego błędu z korekty |

**Minimalne baseline:** zawsze co najmniej 1 cloze z definicją konceptu tytułowego. Jeśli ≥3 sygnały z tabeli — generuj 5+. Brak górnego limitu; każdy cloze musi być atomowy (jeden fakt).

---

## Atomowość

**Jedno front = jeden fakt.** Cloze jest atomowy wtedy i tylko wtedy, gdy można ocenić odpowiedź bez wahania: albo dobrze, albo źle — bez "no, trochę tak".

**Dobry cloze (atomowy):**
- front: "Kiedy Airbnb zaczął stosować Customer Curiosity jako systematyczny nawyk?"
- back: "2009"

**Zły cloze (multiclaim — łam na dwa):**
- front: "Co to Customer Curiosity i dlaczego ją stosuje się w Airbnb?"
- back: "Nawyk codziennego kontaktu z użytkownikiem; Airbnb użył go w 2009 żeby odwrócić spadki."

Zamiast tego — dwa osobne cloze:
1. front: "Co to Customer Curiosity?" / back: "Systematyczny nawyk codziennego kontaktu z użytkownikiem — nie jednorazowy research."
2. front: "Kiedy Airbnb zastosował Customer Curiosity?" / back: "2009, podczas kryzysu wzrostu."

---

## Minimalizm body

Cloze **nie powtarza** tekstu z karty-rodzica. Body cloze zawiera wyłącznie:
- `front` — pytanie testujące jeden fakt
- `back` — krótka, precyzyjna odpowiedź
- link do karty-rodzica (pole `parent_card_id`)

Sekcje `sedno`, `kontekst`, `konkret` z karty-rodzica NIE trafiają do cloze — tam już są. Cloze służy wyłącznie recall + nawigacji do karty-rodzica po sesji powtórkowej.

---

## Przykłady

Poniższe pary front/back pochodzą z kontekstu kursu AIPH2:

**1. Data / rok**
- front: "W którym roku Zappos przetestował "buty wysyłane na żądanie" bez magazynu?"
- back: "1999"

**2. KPI / liczba**
- front: "O ile spadł wskaźnik zwrotów w przykładzie Customer Curiosity z kursu?"
- back: "Z 38% do 32% po 6 tygodniach"

**3. Termin w kontekście**
- front: "Co to OST (Opportunity Solution Tree) w kontekście frameworku Teresa Torres?"
- back: "Drzewo wizualizujące szanse (outcomes), rozwiązania i założenia — narzędzie Continuous Discovery."

**4. Właściwa nazwa**
- front: "Z czym kojarzy się Superhuman w kontekście kursu AIPH2?"
- back: "Przykład Product Taste — obsesja na punkcie jakości UX prowadząca do szybkości i satysfakcji użytkownika."

**5. Para kontrastu**
- front: "Co się dzieje z hipotezą produktową BEZ kroku Validate w Super Loop?"
- back: "Budujesz rozwiązanie oparte na założeniu, nie na obserwacji — ryzyko 'Konrad i kalkulator butów'."

---

## Podsumowanie operacyjne

1. Po `add_card_full` → policz sygnały z tabeli powyżej.
2. Minimum 1 cloze (definicja terminu tytułowego) — zawsze.
3. ≥3 sygnały → ≥5 cloze.
4. Każdy cloze: jedno front, jedno back, link do rodzica — nic więcej.
5. Wywołaj `add_clozes` z listą wygenerowanych par.
