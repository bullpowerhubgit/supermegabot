#!/bin/bash
# Deployment-Script für AIITEC aus supermegabot
cd /Users/rudolfsarkany/supermegabot
# Link auf aiitec-saas Projekt/Service
railway link --project 51e5ea1f-90a8-405c-a57a-c4639d2bbff5 --service f7f2d522-0a0e-4a14-9405-70c67072bed6 2>/dev/null
# Startbefehl auf aiitec_server.py setzen
railway variables set RAILWAY_START_COMMAND="python3 aiitec_server.py" --service aiitec-saas 2>/dev/null
railway up --detach 2>&1 | tail -3
