# OpenCode GitHub Usage Guide

Dieses Repository nutzt [OpenCode](https://opencode.ai/) fuer automatisierte AI-Unterstuetzung via GitHub Actions.

## Verfuegbare Workflows

| Workflow | Datei | Trigger |
|---|---|---|
| Manueller Assist | `opencode.yml` | `/oc` oder `/opencode` in Kommentaren |
| Scheduled Review | `opencode-scheduled.yml` | Jeden Montag 09:00 UTC |
| Issue Triage | `issue-triage.yml` | Neues Issue (Account >= 30 Tage) |
| PR Review | `pr-review.yml` | PR opened / synchronized |

## Beispiele

### Issue erklaeren

Kommentar in einer GitHub Issue:

```
/opencode explain this issue
```

OpenCode liest den gesamten Thread (inkl. aller Kommentare) und antwortet mit einer klaren Erklärung.

### Issue beheben

Kommentar in einer GitHub Issue:

```
/opencode fix this
```

OpenCode erstellt einen neuen Branch, implementiert die Änderungen und oeffnet ein PR.

### PR aendern

Kommentar auf einem GitHub PR:

```
Delete the attachment from S3 when the note is removed /oc
```

OpenCode implementiert die angeforderte Aenderung und pusht sie an denselben PR.

### Spezifische Codezeilen reviewen

Kommentar direkt auf Codezeilen in der **Files**-Tab eines PR:

```
/oc add error handling here
```

OpenCode erkennt automatisch:
- Die genaue Datei
- Die spezifischen Zeilennummern
- Den umgebenden Diff-Context

Dies ermoeglicht gezielte Anfragen ohne manuelle Angabe von Dateipfaden oder Zeilennummern.

## Erforderliches Secret

`ANTHROPIC_API_KEY` muss in **Settings > Secrets and variables > Actions** hinterlegt sein.
