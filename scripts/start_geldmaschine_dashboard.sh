#!/bin/bash
# Geldmaschine €10k Streamlit Dashboard — Autostart
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
export SUPERMEGABOT_API_URL="${SUPERMEGABOT_API_URL:-http://localhost:8888}"
exec streamlit run "$HOME/geldmaschine_skalieren_10k.py" \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false