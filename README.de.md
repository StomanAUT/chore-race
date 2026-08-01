<p align="center">
  <img src="brand_assets/icon@2x.png" width="112" height="112" alt="Chore-Race-Logo mit Pokal">
</p>

<h1 align="center">Chore Race</h1>

<p align="center">
  Ein lokaler Haushaltsplaner für Home Assistant, der alltägliche Aufgaben in ein freundliches Familienrennen verwandelt.
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>Deutsch</strong>
</p>

> [!NOTE]
> Chore Race 1.0 ist die erste stabile öffentliche Familienversion. Erstelle
> vor jedem Update ein vollständiges Home-Assistant-Backup.

## Was Chore Race bietet

Chore Race verbindet einen übersichtlichen Planer für Erwachsene mit einer
responsiven Rennkarte:

- Personen, Räume und Etagen direkt aus Home Assistant verwenden;
- wiederverwendbare Aufgabentypen mit Punkten, Schwierigkeit und Aufgabenbild;
- einmalige und wiederkehrende Aufgaben planen;
- voneinander abhängige Aufgaben als Aufgabenkette organisieren;
- heutige und überfällige offene Aufgaben auch ohne Rennen erledigen;
- ein konfigurierbares Familienrennen mit Fahrer-, Copilot-, Fair-Play- und
  Serienpunkten durchführen;
- Erledigungen rückgängig machen, ohne den Verlauf zu verlieren;
- Belohnungen verwalten und zusammengefasste Home-Assistant-Sensoren nutzen.

Bei einer Aufgabe für eine ganze Etage werden die Basispunkte mit der Anzahl
der dieser Etage zugeordneten Home-Assistant-Räume multipliziert.

<p align="center">
  <img src="custom_components/chore_race/task_icons/mop-floor.png" width="72" height="72" alt="Illustration eines Bodenwischers">
  &nbsp;
  <img src="custom_components/chore_race/task_icons/dishwasher.png" width="72" height="72" alt="Illustration eines Geschirrspülers">
  &nbsp;
  <img src="custom_components/chore_race/task_icons/tidy-up.png" width="72" height="72" alt="Illustration einer Aufräumbox">
</p>

## Schnellstart

1. Füge in HACS `https://github.com/StomanAUT/chore-race` als
   benutzerdefiniertes Repository vom Typ **Integration** hinzu.
2. Installiere **Chore Race** und starte Home Assistant neu.
3. Öffne **Einstellungen → Geräte & Dienste → Integration hinzufügen** und
   füge **Chore Race** hinzu.
4. Installiere die beiden Dashboard-Ressourcen wie unter
   [Installation und Updates](docs/installation.md) beschrieben.
5. Füge eine Planer- und eine Rennkarte zu einem Dashboard hinzu:

```yaml
type: custom:chore-race-planner-card
title: Chore Race Planer
max_width: 960
accent_color: "#74829a"
```

```yaml
type: custom:chore-race-card
title: Familien Grand Prix
target_points: 12
max_width: 820
accent_color: "#74829a"
```

Die Integration wird über die Home-Assistant-Oberfläche eingerichtet. Es wird
nur eine Instanz unterstützt; trage sie nicht in `configuration.yaml` ein.

## Dokumentation

- [Bedienungsanleitung](docs/bedienungsanleitung.md)
- [Installation und Updates](docs/installation.md)
- [Konfigurationsbeispiele](docs/examples.md)
- [Fehlerbehebung](docs/troubleshooting.md)
- [Architektur (Englisch)](docs/architecture.md)
- [Planer-API (Englisch)](docs/planner-api.md)

Englische Dokumentation:
[User guide](docs/user-guide.md) · [English project overview](README.md)

## Grundregeln

- Jeder aktive Teilnehmer darf jede für ihn erlaubte offene Aufgabe erledigen.
  Eine bevorzugte Person ist nur eine Empfehlung.
- Außerhalb eines Rennens vergibt jede Erledigung die eingestellte
  Alltagspunktzahl.
- Eine Aufgabe speichert ihre Rennpunkte beim Erstellen.
- Eine konkrete Aufgabe kann nur eine aktive Erledigung haben.
- Rückgängig machen öffnet die Aufgabe erneut; der inaktive Eintrag bleibt im
  Verlauf erhalten.
- Der Teamfortschritt zählt Aufgaben, nicht Punkte.
- Copilot- und Fair-Play-Bonus können bei derselben Erledigung nicht kombiniert
  werden.
- Erledigte Aufgaben und Aufgaben mit aktiver Erledigung sind vor Änderungen
  geschützt. Eine rückgängig gemachte, eigenständige Aufgabe kann wieder
  bearbeitet oder gelöscht werden.

## Automationen

Die Integration stellt Home-Assistant-Aktionen für Teilnehmer, Aufgabentypen,
Aufgaben, Wiederholungsregeln, Rennen und Erledigungen bereit.
`chore_race.ensure_task` ist für Automationen vorgesehen: Wiederholte Aufrufe
mit demselben Deduplizierungsschlüssel liefern die vorhandene Aufgabe zurück,
anstatt ein Duplikat anzulegen.

Details stehen in den [Konfigurationsbeispielen](docs/examples.md) und in der
[Planer-API](docs/planner-api.md).

## Entwicklung

Die Tests verwenden `pytest-homeassistant-custom-component` und eine getrennte,
temporäre Home-Assistant-Konfiguration:

```text
pytest
ruff check .
```

Führe die Tests niemals gegen eine produktive Home-Assistant-Konfiguration aus.

## Lizenz

Chore Race steht unter der [MIT-Lizenz](LICENSE).
