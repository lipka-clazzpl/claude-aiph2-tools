# Sygnały zainteresowania — heurystyki → tool calls

Agent obserwuje rozmowę i **automatycznie** wywołuje `record_interest(topic, signal, weight_delta)` po wykryciu sygnału. Zapisuje **bez pytania użytkownika**. Ujemny `weight_delta` przesuwa priorytet w stronę 0 (wyższe zainteresowanie). Dodatni przesuwa w stronę 100 (niższe).

Domyślny priorytet nowego tematu: **50** (środek skali).

## Tabela heurystyk

| Sygnał | Topic | Tool call | Priority delta |
|---|---|---|---|
| Pytanie powtórzone (drugi raz w sesji) | konkretny koncept | `record_interest(topic, '+follow-up', -5)` | -5 |
| Pytanie poboczne zadane przez użytkownika | nowy topic z pytania | `record_interest(topic, '+side-question', -5)` + `add_card_full(type='side-question', ...)` | -5 |
| Wraca do tematu w kolejnej sesji (po >24h) | poprzednio wzmiankowany | `record_interest(topic, '+repeat-session', -10)` | -10 |
| Lingering — "powiedz więcej", "ciekawe", "a co jeśli..." | bieżący koncept | `record_interest(topic, '+lingered', -5)` | -5 |
| Pytanie z poziomu eksperckiego (zna kontekst, dopytuje o niuans) | bieżący koncept | `record_interest(topic, '+expert-question', -10)` | -10 |
| "Pomiń" / "wystarczy" / "to już wiem" | bieżący koncept | `record_interest(topic, '+skip', +15)` | +15 |
| "Nie interesuje mnie" / "po co to" | bieżący koncept | `record_interest(topic, '+not-interested', +20)` | +20 |
| Łączy temat z własnym przykładem z firmy (osobiste zaangażowanie) | bieżący koncept | `record_interest(topic, '+personal-example', -10)` | -10 |
| Lapse w powtórce (ocena 0-2) | koncept karty | `record_interest(topic, '+lapse', -5)` | -5 |
| Powtórka 5/5 trzy razy z rzędu | koncept karty | `record_interest(topic, '+mastered', +10)` | +10 |
| Manualne nadpisanie przez `/interest <topic> <priority>` | wskazany | `record_interest(topic, '+manual', delta-do-celu)` | wg celu |

## Zasady stosowania

- **Topic** to **slug** (lowercase-with-dashes), np. `customer-curiosity`, `lovable-plan-mode`, `super-loop`, `5-cech-buildera`. Nie pełne zdania.
- Sygnały są **kumulatywne** — pięć follow-upów w sesji oznacza pięć wywołań `record_interest`, każde z `weight_delta=-5`. Każde wywołanie dopisuje do listy `signals` w profilu.
- Priorytet jest **clampowany** do zakresu 0-100. Jeśli priorytet już jest 0, kolejny `-5` nic nie zmieni (informacja zostaje w `signals`).
- Wywołuj **bez przerywania toku rozmowy** — sygnał jest meta-działaniem, nie wymaga wzmianki dla użytkownika.

## Wpływ priorytetu na głębokość karty

| Priority bucket | Głębokość kart pisanych w tej sesji |
|---|---|
| 0-30 | **rozbudowane** — każda sekcja `why/tradeoff/pitfall` pełna, szersza perspektywa z 2-3 frameworkami, element review z mnemonikiem |
| 31-70 | **standardowe** — wszystkie 11 sekcji, każda zwięzła |
| 71-100 | **lakoniczne** — Sedno + Konkret + Pytanie sprawdzające wystarczy; reszta `_(brak)_` |

Profil odczytujesz **na starcie sesji** (`read_interest_profile`). Aktualizujesz **w trakcie** (`record_interest`). Dla każdego nowego konceptu sprawdzasz, w którym bucket'cie jest jego topic, i dobieasz głębokość karty zapisywanej przez `add_card_full`.

## Przykładowy przebieg

```
Użytkownik: "Powiedz mi więcej o Customer Curiosity, ostatnio czytałem Teresa Torres"
   → record_interest('customer-curiosity', '+lingered', -5)
   → record_interest('customer-curiosity', '+expert-question', -10)
   → (priorytet z 50 → 35; karta będzie standard, ale na granicy expand)

Użytkownik: "A jak to się ma do JTBD?"
   → record_interest('jobs-to-be-done', '+side-question', -5)
   → add_card_full(type='side-question', title='JTBD vs Customer Curiosity', ...)

Użytkownik: "OK, Customer Curiosity ogarnięte. Lecimy dalej."
   → (brak sygnału — neutralne przejście)

Użytkownik (po 2 dniach, w nowej sesji): "Dobra, wracam do Customer Curiosity, mam pytanie"
   → record_interest('customer-curiosity', '+repeat-session', -10)
   → (priorytet z 35 → 25; teraz bucket 0-30, karty rozbudowane)
```
