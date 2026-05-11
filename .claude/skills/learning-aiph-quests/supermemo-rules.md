# SuperMemo — esencja 20 reguł + incremental learning (skrót dla AIPH2)

Źródła: [20 rules of formulating knowledge](https://super-memory.com/articles/20rules.htm),
[Incremental learning](https://help.supermemo.org/wiki/Incremental_learning).

Tutaj: **co stosujemy w tym skillu**, bo nie wszystkie reguły są 1:1 użyteczne w kursie produktowym.

## Kanon reguł (zaadaptowany)

1. **Nie ucz się, czego nie rozumiesz** — jeśli nie wiesz, dlaczego framework działa, nie twórz
   z niego fiszki. Najpierw zrozumienie (5 zasad aktywnego uczenia), potem zapis.
2. **Zrozumienie → uproszczenie → zapis**. Karta to *destylat*, nie kopia transkryptu.
3. **Buduj na podstawach** — nie ucz się "Validate", jeśli nie czujesz "Frame". Powiązania
   krzyżowe w sekcji `Powiązane karty` ratują kontekst.
4. **Zasada minimum informacji** — jedna karta = jedna idea. Jeśli karta ma 2 odrębne pomysły,
   rozbij ją na dwie. ALE: jedna idea może mieć bogatą sekcję z kontekstem, why, przykładem —
   to **nie narusza** zasady minimum informacji, bo to wciąż jedna idea.
5. **Cloze deletion działa** — przy pytaniu sprawdzającym preferuj formy: "X różni się od Y tym,
   że __" albo "Brakujący krok między A i C to __".
6. **Unikaj zestawień bez znaczenia** — nie zapamiętuj "5 cech buildera" jako listy 5 słów.
   Zapamiętuj każdą cechę osobno z casem. Lista jest dobrą *kotwicą*, ale nie kartą.
7. **Bój się wyliczeń** — jeśli musisz nauczyć się kolejności (Sense → Frame → Prototype →
   Validate → Ship → Learn), zrób z tego mnemonik / opowiadanie, nie ślepe wyliczenie.
8. **Mnemoniki dla trudnych** — jeśli karta wraca z lapsem 3+ razy, dodaj wizualny mnemonik
   (np. "Agency = pies bez smyczy: idzie, dopóki ktoś go nie zatrzyma").
9. **Personalizuj przykłady** — zamień case Konrada na case z **swojej** firmy w sekcji
   "Notatki własne". Wpis własny zawsze wzmacnia ślad pamięciowy.
10. **Kontekst ratuje** — sekcja "Kontekst (skąd to)" odpala kontekst sesji w 2 sekundach,
    nawet po 6 miesiącach.
11. **Zredundowane → łatwiejsze do zapamiętania** — w skali fiszek to znaczy: zapamiętujesz
    *trochę więcej* niż musisz, żeby ratować się przy częściowym braku przypomnienia.
    Sekcja "Powód" + "Kompromis" robi tę robotę.
12. **Źródła** — zawsze pole `source` w frontmatter. Inaczej w przyszłości nie zweryfikujesz.
13. **Daty w frontmatter** — `created`, `last_review`, `next_review` to historia karty.
14. **Priorytety** — `difficulty` (`easy/medium/hard`) wpływa na to, które karty robisz najpierw,
    gdy jest ich za dużo. (W tym skillu: trudne najpierw rano.)
15. **Tytuł = haczyk** — tytuł karty musi pojedynczy fragment dnia odróżnić od innego. Zły tytuł:
    "Customer". Dobry: "Customer Curiosity — codzienny nawyk vs jednorazowy research".

## Incremental learning — minimalny pipeline w tym skillu

Pełen SuperMemo używa dwóch poziomów: **extracts** (wycinki źródła) → **items** (gotowe karty).
Tutaj robimy uproszczoną wersję:

1. **Wczytaj materiał** dnia (transcript, slidy, quest .md/.docx) lub pobierz z Circle.
2. **Wskaż interesujące fragmenty** w trakcie nauki krok-po-kroku.
3. **Promuj** każdy fragment do karty (`type: concept|framework|example|...`) — pełna sekcja
   wg `templates/card.md`.
4. **Pytania poboczne** (zadane przez Ciebie) ZAWSZE → karta `type: side-question` z pełną
   odpowiedzią (zasada "jeśli pytasz, jest istotne").
5. **Powtórki** — codziennie `due.py`, ocena `review.py --grade 0..5`.

## Czego NIE robimy

- Nie robimy fiszek z dat / cen / nazw narzędzi w stylu trivia ("ile MB ważyła prezentacja").
  Fakty operacyjne, nie wiedza.
- Nie kopiujemy slajdów 1:1. Karta to *Twój* destylat.
- Nie tworzymy karty bez sekcji "Pytanie sprawdzające". Karta bez pytania nie jest powtórzona,
  jest tylko przeczytana.
