#!/usr/bin/env bash
# ============================================================================
# One-Click Project Completion — complete-projects.sh
#
# Findet alle Schwester-Projekte neben diesem Repo, erkennt pro Projekt den
# Stack (Node/Next/Express, Python, statisches HTML) und führt automatisiert
# Install → Lint → Typecheck → Build → Healthcheck aus. Erzeugt am Ende einen
# Report unter ./completion-report.md.
#
# Nutzung:
#   ./scripts/complete-projects.sh                # alle gefundenen Projekte
#   ./scripts/complete-projects.sh repoA repoB    # nur genannte Projekte
#   WORKSPACE=/pfad/zu/projekten ./scripts/complete-projects.sh
#
# GRENZEN (bewusst, nie ohne explizite Freigabe):
#   - kein Deploy, keine Live-DB-Migration, keine echten Zahlungen
#   - keine echten Mails / Social-Posts
#   - Zahlungen/Webhooks nur im Test-/Sandbox-Modus
# ============================================================================
set -uo pipefail

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
REPORT="${WORKSPACE}/completion-report.md"
FILTER=("$@")

pass=0; warn=0; fail=0
echo "# Completion-Report — $(date -u '+%Y-%m-%d %H:%M UTC')" > "$REPORT"
echo "" >> "$REPORT"
echo "| Projekt | Typ | Install | Lint | Typecheck | Build | Health | Status |" >> "$REPORT"
echo "|---|---|---|---|---|---|---|---|" >> "$REPORT"

want() { # respektiert optionalen Projektfilter
  [ ${#FILTER[@]} -eq 0 ] && return 0
  for f in "${FILTER[@]}"; do [ "$f" = "$1" ] && return 0; done
  return 1
}

run() { # run <cmd...> → gibt "ok"/"fail"/"skip" via echo, Logs nach /tmp
  local log; log="$(mktemp)"
  if "$@" >"$log" 2>&1; then echo "ok"; else echo "fail"; fi
  rm -f "$log"
}

detect() { # erkennt Projekttyp
  local d="$1"
  if [ -f "$d/next.config.ts" ] || [ -f "$d/next.config.js" ] || [ -f "$d/next.config.mjs" ]; then echo "next"; return; fi
  if [ -f "$d/package.json" ]; then echo "node"; return; fi
  if [ -f "$d/requirements.txt" ] || ls "$d"/*.py >/dev/null 2>&1; then echo "python"; return; fi
  if ls "$d"/*.html >/dev/null 2>&1; then echo "static"; return; fi
  echo "unknown"
}

pkg_has() { # pkg_has <dir> <script>
  [ -f "$1/package.json" ] && grep -q "\"$2\"" "$1/package.json" 2>/dev/null
}

health_url() { # liest optionale HEALTH_URL_<REPO> env
  local key="HEALTH_URL_$(echo "$1" | tr '[:lower:]-' '[:upper:]_')"
  echo "${!key:-}"
}

for dir in "$WORKSPACE"/*/; do
  name="$(basename "$dir")"
  [ "$name" = "$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")" ] && here="$name"
  [ -d "$dir/.git" ] || continue
  want "$name" || continue

  type="$(detect "$dir")"
  inst="skip"; lint="skip"; tc="skip"; build="skip"; health="skip"
  echo ">>> $name ($type)"
  pushd "$dir" >/dev/null || continue

  case "$type" in
    node|next)
      if [ -f pnpm-lock.yaml ]; then PM="pnpm"; elif [ -f yarn.lock ]; then PM="yarn"; else PM="npm"; fi
      inst="$(run $PM install)"
      pkg_has "$dir" lint      && lint="$(run $PM run lint)"
      pkg_has "$dir" typecheck && tc="$(run $PM run typecheck)"
      pkg_has "$dir" build     && build="$(run $PM run build)"
      ;;
    python)
      if [ -f requirements.txt ]; then inst="$(run python3 -m pip install -r requirements.txt)"; fi
      # Syntax-Check als Typecheck-Ersatz
      if compgen -G "*.py" >/dev/null || [ -d modules ]; then
        if find . -name '*.py' -not -path './.git/*' -print0 | xargs -0 -n1 python3 -m py_compile 2>/dev/null; then tc="ok"; else tc="fail"; fi
      fi
      ;;
    static)
      # statische HTML-Projekte: kein Build; prüfe nur, dass index.html existiert
      [ -f index.html ] && build="ok" || build="fail"
      ;;
  esac

  hu="$(health_url "$name")"
  if [ -n "$hu" ]; then
    if curl -fsS --max-time 15 "$hu" >/dev/null 2>&1; then health="ok"; else health="fail"; fi
  fi

  popd >/dev/null

  # Gesamtstatus
  status="✅"
  for r in "$inst" "$lint" "$tc" "$build" "$health"; do [ "$r" = "fail" ] && status="❌"; done
  [ "$status" = "✅" ] && { [ "$inst" = "skip" ] && [ "$build" = "skip" ]; } && status="⚠️"
  case "$status" in "✅") pass=$((pass+1));; "⚠️") warn=$((warn+1));; "❌") fail=$((fail+1));; esac

  echo "| $name | $type | $inst | $lint | $tc | $build | $health | $status |" >> "$REPORT"
done

{
  echo ""
  echo "**Zusammenfassung:** ✅ $pass · ⚠️ $warn · ❌ $fail"
  echo ""
  echo "> \`skip\` = für diesen Stack nicht anwendbar (z. B. kein lint-Script)."
  echo "> Healthchecks laufen nur, wenn \`HEALTH_URL_<REPO>\` gesetzt ist (z. B. \`HEALTH_URL_SUPERMEGABOT\`)."
  echo "> Deploy, Live-DB-Migration, echte Zahlungen und Mails sind bewusst NICHT Teil dieses Workflows."
} >> "$REPORT"

echo ""
echo "Report geschrieben: $REPORT"
echo "Ergebnis: ✅ $pass · ⚠️ $warn · ❌ $fail"
[ "$fail" -eq 0 ]
