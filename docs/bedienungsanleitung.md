# Chore Race Bedienungsanleitung

[English](user-guide.md) · [Projektübersicht](../README.de.md)

Diese Anleitung beschreibt die derzeit in Chore Race 0.8 verfügbaren
Funktionen.

## 1. Installation

Installiere die Integration, beide JavaScript-Karten und die Aufgabenbilder
gemäß [Installation und Updates](installation.md). Starte Home Assistant nach
einem Austausch der Integration neu. Ändere bei aktualisierten Kartendateien
den `?v=`-Wert ihrer Ressource und lade den Browser ohne Cache neu.

Füge eine `custom:chore-race-planner-card` zur Verwaltung und eine
`custom:chore-race-card` für Alltag und Rennen hinzu. Bei beiden Karten lassen
sich `max_width` und `accent_color` konfigurieren; Beispiele stehen unter
[Konfigurationsbeispiele](examples.md).

Nur Home-Assistant-Administratoren dürfen Änderungen im Planer und an Rennen
vornehmen.

## 2. Ersteinrichtung

Vor der ersten Verwendung:

1. Lege bei Bedarf unter **Einstellungen → Personen** die Mitglieder des
   Haushalts in Home Assistant an.
2. Lege unter **Einstellungen → Bereiche, Labels & Zonen** die Räume an.
3. Lege optional Etagen an und ordne ihnen die passenden Räume zu.
4. Öffne die Chore-Race-Planerkarte.

Chore Race verwendet die Personen-, Raum- und Etagenverzeichnisse von Home
Assistant. Es führt keine getrennte Raum- oder Etagenverwaltung.

## 3. Teilnehmer

Im Abschnitt **Teilnehmer**:

1. Wähle eine **Home-Assistant-Person** oder lasse die Auswahl leer und gib
   einen Namen manuell ein.
2. Wähle die Rolle **Kind** oder **Erwachsen**.
3. Aktiviere **Eingeschränkte Aufgaben erlaubt** nur, wenn diese Person als
   „nur für Erwachsene“ markierte Aufgabentypen erledigen darf.
4. Klicke auf **Teilnehmer anlegen**.

Die Rennkarte zeigt alle aktiven Teilnehmer. Das Entfernen aus einem Rennen
deaktiviert die Person auch im Planer, öffnet ihre betroffenen Aufgaben dieses
Rennens wieder und erhält den bisherigen Verlauf. Wird dieselbe
Home-Assistant-Person im Planer erneut ausgewählt, reaktiviert Chore Race den
vorhandenen Teilnehmer, statt ein Duplikat anzulegen.

## 4. Aufgabentypen

Ein Aufgabentyp ist eine wiederverwendbare Vorlage, zum Beispiel „Boden
wischen“ oder „Geschirrspüler ausräumen“.

1. Gib Bezeichnung und standardmäßige Rennpunkte ein.
2. Wähle optional eine Schwierigkeit.
3. Öffne **Aufgabenbild** und wähle eines der mitgelieferten Motive.
4. Lege unter **Rennwertung festlegen** bei Bedarf Serienbonus,
   Copilot-Punkte und die Beschränkung auf Erwachsene fest.
5. Klicke auf **Aufgabentyp anlegen**.

Vorhandene Vorlagen stehen im Abschnitt **Aufgabentypen**. Eine Änderung der
Vorlage wirkt auf zukünftige Standardwerte; bereits erstellte Aufgaben
behalten ihre gespeicherte Punktzahl. Ein Aufgabentyp, auf den Aufgaben oder
Wiederholungsregeln verweisen, kann nicht endgültig gelöscht werden. Er kann
stattdessen deaktiviert werden.

## 5. Einmalige und wiederkehrende Aufgaben

Unter **Aufgabe einplanen**:

1. Wähle einen Aufgabentyp.
2. Wähle das Datum. Bei Wiederholungen ist dies das Startdatum.
3. Wähle keinen Ort, einen Home-Assistant-Raum oder eine Etage.
4. Wähle optional eine bevorzugte Person.
5. Wähle die Wiederholung:

   - **Einmalig** – eine Aufgabe am gewählten Datum;
   - **Alle N Tage** – festes Kalenderintervall in Tagen;
   - **Bestimmte Wochentage** – die ausgewählten Wochentage;
   - **Nach letzter Erledigung** – das Intervall beginnt nach der Erledigung;
   - **Einmal pro Monat** – monatlich ab dem Startdatum;
   - **Einmal pro Jahr** – jährlich ab dem Startdatum.

6. Klicke auf **Aufgabe einplanen**.

Die bevorzugte Person ist eine Empfehlung. Jeder andere berechtigte und aktive
Teilnehmer kann die Aufgabe ebenfalls erledigen. Raum und Etage können nicht
gleichzeitig ausgewählt werden.

Bei einer Aufgabe für eine ganze Etage zeigt die Karte die berechnete
Gesamtpunktzahl. Chore Race multipliziert die Basispunkte des Aufgabentyps mit
der Anzahl der Home-Assistant-Räume, die dieser Etage zugeordnet sind. Eine
Etage ohne zugeordnete Räume kann für diese Berechnung nicht verwendet werden.

Bereits erzeugte Aufgaben bleiben erhalten, wenn eine Wiederholungsregel
pausiert, geändert oder gelöscht wird. Die Zeitpläne werden unter
**Wiederholungsregeln** verwaltet.

## 6. Aufgabenketten

Unter **Aufgabenketten** lassen sich mehrere Aufgaben in eine feste,
schleifenfreie Reihenfolge bringen. Gib Name und Startdatum ein, füge die
Schritte hinzu und erstelle die Kette. Ein Schritt wird erst freigegeben,
nachdem sein Vorgänger erledigt wurde.

Aufgaben in einer Kette behalten einen strengeren Verlaufsschutz als einzelne
Aufgaben. Dadurch kann eine erledigte Reihenfolge nicht nachträglich in einen
widersprüchlichen Zustand gebracht werden.

## 7. Alltagserledigung ohne Rennen

Die Rennkarte dient zugleich als Aufgabenansicht für den Alltag. Heutige und
überfällige offene Aufgaben bleiben verfügbar. Eine Aufgabe wird also nicht
unmöglich, nur weil ihr geplantes Datum bereits vergangen ist.

1. Wähle eine offene Aufgabe.
2. Wähle die Person, die sie erledigt hat.
3. Bestätige die Erledigung.

Ohne laufendes Rennen vergibt Chore Race die eingestellte Alltagspunktzahl.
Copilot- und Fair-Play-Boni stehen nur während eines Rennens zur Verfügung.

## 8. Ein Rennen durchführen

Ein Administrator klickt auf der Rennkarte auf **Rennen starten**. Die aktuell
aktiven Teilnehmer bilden das Starterfeld und der eingestellte Countdown
beginnt.

Eine Aufgabe während des Rennens erledigen:

1. Wähle die Aufgabe.
2. Wähle den Fahrer.
3. Wähle optional einen anderen Teilnehmer als Copilot oder den
   Fair-Play-Bonus.
4. Bestätige die Erledigung.

Copilot und Fair Play können nicht gleichzeitig gewählt werden. Rennstrecke,
Punkte, Fortschritt und nächste offene Aufgabe werden über lokale
Home-Assistant-Ereignisse aktualisiert. Mit **Rennen beenden** kann ein
Administrator das laufende Rennen vorzeitig abschließen.

Gibt es einen eindeutigen Sieger und sind Belohnungen angelegt, darf dieser
eine Belohnung auswählen.

## 9. Bearbeiten, Löschen und Rückgängig

Der Planer listet vorhandene Vorlagen, Wiederholungsregeln und offene Aufgaben
mit den jeweils verfügbaren Aktionen.

- Eine offene Einzelaufgabe ohne aktive Erledigung kann auch während eines
  laufenden Rennens bearbeitet oder gelöscht werden.
- Eine erledigte Aufgabe oder eine Aufgabe mit aktiver Erledigung ist bewusst
  geschützt.
- Das Rückgängigmachen öffnet die Aufgabe wieder und markiert die Erledigung
  als inaktiv; der Verlauf wird nicht gelöscht.
- Die wieder geöffnete Einzelaufgabe kann anschließend bearbeitet oder
  gelöscht werden.
- Aufgabenketten bleiben strenger geschützt, sobald ein Verlauf vorhanden ist.
- Das Löschen einer Wiederholungsregel löscht keine bereits erzeugten Aufgaben.

Diese Schutzregeln verhindern nachträgliche Änderungen an der Punktehistorie.

## 10. Rennen zurücksetzen und Teilnehmer entfernen

**Rennen zurücksetzen** nimmt die aktiven Wertungen dieses Rennens zurück,
öffnet dessen Aufgaben erneut, stellt das aktive Starterfeld wieder her und
setzt die Sitzung auf „bereit“. Historische Einträge bleiben gespeichert.

Das Entfernen-Symbol neben einem Teilnehmer entfernt die Person aus dem
gewählten Rennen und deaktiviert sie global. Erledigungen dieses Rennens, an
denen die Person beteiligt war, werden zurückgenommen und die betroffenen
Aufgaben wieder geöffnet. Lies den Bestätigungsdialog vor dem Ausführen
sorgfältig.

## 11. Fehlerbehebung

### `Unknown command` oder `Service ... not found`

Integration und Frontend haben unterschiedliche Versionsstände. Starte Home
Assistant neu, aktualisiere beide Kartendateien, erhöhe beide `?v=`-Werte und
lade den Browser ohne Cache neu.

### Die Karte zeigt weiterhin die alte Ansicht

Prüfe die JavaScript-Ressourcen unter
**Einstellungen → Dashboards → Ressourcen**, erhöhe deren Versionsparameter
und führe ein vollständiges Neuladen ohne Cache durch.

### Eine Aufgabe lässt sich nicht bearbeiten oder löschen

Prüfe, ob eine aktive Erledigung besteht oder die Aufgabe zu einer Kette mit
Verlauf gehört. Mache bei einer Einzelaufgabe zuerst die Erledigung rückgängig.

### Eine Person, ein Raum oder eine Etage fehlt

Lege den Eintrag im entsprechenden Home-Assistant-Verzeichnis an oder
korrigiere ihn und betätige danach die Aktualisieren-Schaltfläche des Planers.
Ordne einer Etage mindestens einen Raum zu, bevor du die
Etagen-Punktemultiplikation verwendest.

Weitere Hinweise zu Speicherreparatur und Diagnose stehen unter
[Fehlerbehebung](troubleshooting.md). Gib beim
[Erstellen eines Issues](https://github.com/StomanAUT/chore-race/issues) die
Home-Assistant- und Chore-Race-Version sowie relevante `chore_race`-Logzeilen
an.
