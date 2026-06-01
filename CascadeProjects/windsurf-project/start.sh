#!/bin/bash

# SuperMegaBot - Einfacher Start-Button
# Startet das komplette SuperMegaBot-System

echo "🚀 SuperMegaBot - System Start"
echo "================================"
echo ""
echo "📋 Starte alle Komponenten..."
echo ""

# System-Diagnostik
echo "🔍 System-Diagnostik..."
node supermegabot-starter.js diagnose
echo ""

# Komplettes System starten
echo "🚀 Starte SuperMegaBot System..."
node supermegabot-starter.js start
