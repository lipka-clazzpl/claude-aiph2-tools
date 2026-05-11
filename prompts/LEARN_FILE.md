# Nauczanie z pliku — `/learn-file <path>`

Użytkownik chce się uczyć z pliku: `{file_path}`

## Instrukcje

1. **Profil zainteresowań** — najpierw `read_interest_profile`, żeby wiedzieć jakie tematy preferuje użytkownik.
2. **Załaduj plik** używając narzędzia `load_learning_material(file_path='{file_path}')`. Automatyczna detekcja typu po rozszerzeniu (`.md`, `.txt`, `.docx`).
3. **Przeanalizuj zawartość** i zidentyfikuj:
   - Główne koncepcje, frameworki, zasady
   - Użyte studia przypadków / przykłady
   - Kluczowe decyzje / KPI / hipotezy
   - Pytania, które sam plik pozostawia otwarte
4. **Zaplanuj kolejność nauczania** — od najprostszych konceptów do najtrudniejszych. Pokaż plan użytkownikowi i poczekaj na akceptację (Krok 2 z `LEARN_QUEST.md`).
5. **Rozpocznij naukę** od pytania intuicyjnego o pierwszym koncepcie — według 5 zasad aktywnego uczenia z `SYSTEM_PROMPT.md`.
6. **Ucz krok po kroku**, pokazując odpowiednie fragmenty pliku jako cytaty (`source_quote` w karcie).

## Pamiętaj

- Nie pokazuj całego pliku na raz — prezentuj fragment po fragmencie.
- Każdemu konceptowi poświęć osobny krok (intuicja → konkret → **Wikipedia (Krok 3.5)** → why/tradeoff/pitfall → perspektywa → pytanie sprawdzające).
- **Krok 3.5 — Wikipedia**: wywołaj `wikipedia_lookup(title=<koncept>, lang='auto', branches=3, mode='full')` między Konkret a Why. Patrz §5a w `SYSTEM_PROMPT.md` — pełna polityka, zakres użycia i obsługa błędów.
- **ZAWSZE kończ pytaniem sprawdzającym.** NIE kontynuuj bez poprawnej odpowiedzi.
- **Po każdym koncepcie zapisz pełną kartę** przez `add_card_full` z `wikipedia_branches` (JSON z gałęziami z Kroku 3.5 lub `'[]'` gdy lookup nie powiódł się).
- **Pytania poboczne użytkownika → osobna karta** (`type='side-question'`) z pełną odpowiedzią.
- Jeśli plik jest długi i `load_learning_material` zwrócił uciętą zawartość ("truncated") — ostrzeż użytkownika i ewentualnie doczytaj brakującą część przez `Read` z `offset`.
- Po każdej karcie `add_card_full` wywołaj `add_clozes`. Ile cloze'ów: min. 1, bez limitu — zależy od liczby terminów / dat / dopytań w sesji.
