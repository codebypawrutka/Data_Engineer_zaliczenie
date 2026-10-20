# Analiza wyników

Źródła liczb:
- `data/reports/dq_report.md`: jakość danych;
- `data/reports/analytics/*.csv`: wyniki 5 zapytań.

Przyjęte definicje:
- **GMV** = suma `price` (wartość towarów bez frachtu);
- **przychód** = `price + freight_value`;
- zamówienia `canceled` i `unavailable` są wykluczone;
- kwoty są w BRL.

## 0. Jakość danych

Zbiór Olist jest stosunkowo czysty. 34 testy w 9 tabelach odrzuciły **mniej niż 0,01% wierszy** w każdej tabeli, daleko poniżej progu bezpiecznika (5%).

- **8 zamówień** ma status `delivered`, ale brak daty doręczenia (`order_delivered_has_date`). Trafiły do kwarantanny, a test integralności (`*_fk_order`) **kaskadowo** odrzucił też ich 8 pozycji, 8 płatności i 8 recenzji. Dzięki temu w hurtowni nie ma „sierot”.
- **2 płatności kartą z 0 ratami** (`payment_installments_positive`): fizycznie niemożliwe, prawdopodobnie błąd systemu źródłowego.
- **Geolokalizacja:** 1 000 163 punkty, w tym **261 831 dokładnych duplikatów (26%)**. Kolejne **33 punkty leżą poza Brazylią**. Po czyszczeniu dane zagregowano do 1 punktu (średnia) na prefiks kodu pocztowego.
- **610 produktów (1,9%) nie ma kategorii.** Nie jest to błąd odrzucający, więc w wymiarze produktu dostają wartość `unknown`.
- Typy rzutowały się bez strat (`cast_failures` puste). Kody pocztowe zachowały zera wiodące dzięki jawnemu typowi tekstowemu.

## 1. GMV miesiąc do miesiąca (`01_gmv_mom.csv`)

Analizowany okres to 2017-01 .. 2018-08. Wcześniejsze i późniejsze miesiące są w zbiorze szczątkowe: we wrześniu 2016 jest 280 BRL przychodu, a w listopadzie 2016 nie ma żadnego zamówienia. Dawałyby fałszywe skoki MoM.

- **Silny wzrost w 2017:** GMV rośnie z 120 tys. (I 2017) do 660 tys. (X 2017), czyli **5,5 raza w 10 miesięcy**.
- **Black Friday:** listopad 2017 to **1,00 mln GMV (+52% MoM)** i 7 420 zamówień, najwyższy miesiąc w całym zbiorze. W grudniu następuje korekta (−26%).
- **Plateau w 2018:** od stycznia GMV stabilizuje się w przedziale 0,85–0,99 mln miesięcznie. Średnia krocząca 3M szczytuje w maju 2018 (989 tys.), potem lekko spada.
- **Wzrost napędza wolumen, nie koszyk.** Liczba zamówień rośnie ok. 8 razy (787 → 6–7 tys.), a średnia wartość zamówienia waha się w wąskim przedziale 125–153 BRL.

**Rekomendacja:** wzrost wyhamował w 2018, więc kolejny etap to podnoszenie wartości koszyka (cross-selling, darmowa dostawa od progu) zamiast samej akwizycji. Kampanię Black Friday warto powtarzać i planować pod nią zapasy.

## 2. Top 3 kategorie w stanach (`02_top3_categories_by_state.csv`)

- **Silna koncentracja geograficzna:** **SP generuje 38,3% GMV**, a SP, RJ i MG razem **63,4%**.
- **Kraj jest dość jednolity:** `health_beauty` jest kategorią nr 1 w **15 z 27 stanów**, `watches_gifts` w 6, `sports_leisure` w 3. W TOP 3 niemal wszędzie powtarzają się te same 4–5 kategorii.
- **Różnice regionalne:** w RJ i PR wygrywa `watches_gifts`, w SP i RS `bed_bath_table`.
- **Rozdrobniony koszyk kategorii:** lider ma tylko **8–10% GMV stanu**, a największa kategoria w skali kraju (`health_beauty`) to 9,3% całości.

**Rekomendacja:** asortyment i marketing mogą być w dużej mierze ogólnokrajowe. Logistykę warto natomiast optymalizować pod osie SP, RJ i MG.

## 3. Ranking sprzedawców (`03_seller_ranking.csv`)

- **Wyraźny efekt Pareto:** **17,7% sprzedawców (540 z 3 053) generuje 80% GMV**, a zaledwie **4,2% (129) robi połowę**.
- Największy sprzedawca (SP) ma 229 tys. GMV z 1 131 zamówień.
- **Sprzedawcy są jeszcze bardziej skupieni w SP niż klienci:** 65 z TOP 100 pochodzi z SP, kolejne są PR (10), RJ (7) i MG (6).
- Najwięksi sprzedawcy **nie są lepsi logistycznie**. Górny decyl ma 7,0% spóźnień i 13,1 dnia dostawy, reszta 6,9% i 12,0 dnia.

**Rekomendacja:** program „key account” dla ok. 500 największych sprzedawców. Jakość dostaw wymaga osobnych działań, bo nie rośnie wraz ze skalą.

## 4. Retencja klientów (`04_customer_retention.csv`)

Klienta liczymy po `customer_unique_id`. `customer_id` jest w Olist nadawany **per zamówienie**, więc liczenie po nim dałoby 0% retencji.

- **Retencja jest bardzo niska:** średnio **0,49%** kohorty wraca w 1. miesiącu, **0,34%** w 2. i **0,25%** w 3. (średnia z 17 kohort 2017-01 … 2018-05).
- Tylko **3,0% z 94 975 klientów** złożyło więcej niż jedno zamówienie (rekordzista: 16).
- To właściwość modelu biznesowego, a nie błąd zapytania. Olist to marketplace z zakupami okazjonalnymi (meble, prezenty, AGD), a klient często nie wie, że kupuje „w Olist”.

**Rekomendacja:** przy takiej retencji wzrost zależy od kosztu pozyskania klienta (CAC). Warto testować programy powrotu, np. kupon po pierwszym zakupie, w kategoriach o naturalnej powtarzalności (`health_beauty`, `bed_bath_table`).

## 5. Przychód narastający (`05_cumulative_revenue.csv`)

- **Łączny przychód** (cena + fracht) za cały okres to **15,73 mln BRL**: 7,14 mln w 2017 i 8,59 mln w 2018 (YTD do sierpnia).
- **Połowę całego przychodu przekroczono w styczniu 2018** (52,4%). 8 miesięcy 2018 dało więcej niż cały 2017.
- Krzywa narastająca jest wypukła w 2017 (przyspieszenie), a w 2018 prawie liniowa (ok. 1,0–1,15 mln miesięcznie). To ten sam obraz plateau co w zapytaniu 1.

## 6. Dodatkowa obserwacja: spóźnienia a oceny

To obserwacja spoza 5 zapytań, policzona na warstwie silver. **6,8% zamówień** dociera po szacowanym terminie (mediana dostawy 10 dni, średnia 12,5). Zamówienia spóźnione mają średnią ocenę **2,27 wobec 4,29**, a ocenę 1–2 wystawia **62% ich klientów wobec 9%**. Terminowość dostaw to najsilniejsza zmienna wpływająca na zadowolenie klientów i jest w pełni zależna od procesu.

## Wnioski i rekomendacje

1. **Wzrost przeszedł w plateau** (2018: ok. 0,9–1 mln GMV miesięcznie). Dalsze źródła wzrostu to wartość koszyka i retencja, nie sam wolumen.
2. **Retencja na poziomie 3% powtórnych klientów** to największa dźwignia. Nawet niewielki wzrost istotnie obniżyłby zależność od akwizycji.
3. **Terminowość dostaw przekłada się bezpośrednio na oceny.** Monitorowanie `late_pct` per sprzedawca (tabela gold `seller_monthly_kpi`) i działania wobec najgorszych sprzedawców dadzą szybki efekt.
4. **Koncentracja w SP** (38% popytu, 65% TOP sprzedawców) uzasadnia inwestycje logistyczne w regionie Sudeste, a jednocześnie stanowi ryzyko.
