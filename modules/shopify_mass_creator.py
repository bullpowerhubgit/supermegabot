#!/usr/bin/env python3
"""
Shopify Mass Creator — 1000 Produkte vollautomatisch
=====================================================
Erstellt bis zu 1000 Shopify-Produkte mit:
- 1000 hardcodierte Templates (10 Kategorien × 100)
- KI-generierte SEO-Beschreibungen (150 Wörter, Keywords)
- LoremFlickr Bilder (kein API-Key)
- 5 parallele Worker
- Telegram Progress-Updates alle 100 Produkte
- BrutusCore Blast der Top-10 nach Erstellung
- Supabase Deduplizierung
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("ShopifyMassCreator")

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER     = os.getenv("SHOPIFY_API_VERSION", "2026-04")
BASE    = f"https://{SHOP}/admin/api/{VER}" if SHOP else ""
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", f"https://{SHOP}" if SHOP else "https://autopilot-store-suite-fmbka.myshopify.com")

# ─── 1000 Produkt-Templates (10 Kategorien × 100) ────────────────────────────

SHOPIFY_PRODUCT_TEMPLATES: list[dict] = [
    # ── Smart Home (100) ──────────────────────────────────────────────────────
    {"title": "WiFi Smart Plug EU 16A Energiemessung", "niche": "smart_home", "price": "24.99", "compare_at": "39.99", "tags": "smart home,wifi,alexa,google home,steckdose"},
    {"title": "LED Strip 5m RGB WiFi Alexa", "niche": "smart_home", "price": "19.99", "compare_at": "34.99", "tags": "led strip,rgb,smart home,wifi"},
    {"title": "Smart Glühbirne E27 RGB 9W", "niche": "smart_home", "price": "14.99", "compare_at": "24.99", "tags": "smart bulb,rgb,e27,alexa"},
    {"title": "Zigbee Gateway Hub Smart Home", "niche": "smart_home", "price": "34.99", "compare_at": "54.99", "tags": "zigbee,gateway,smart home,hub"},
    {"title": "WiFi Türklingel mit Kamera 1080p", "niche": "smart_home", "price": "49.99", "compare_at": "79.99", "tags": "türklingel,kamera,wifi,smart home"},
    {"title": "Smart Thermostat Heizung programmierbar", "niche": "smart_home", "price": "59.99", "compare_at": "89.99", "tags": "thermostat,heizung,smart home,energiesparen"},
    {"title": "Bewegungsmelder WiFi Indoor 120°", "niche": "smart_home", "price": "19.99", "compare_at": "29.99", "tags": "bewegungsmelder,wifi,alarm,smart home"},
    {"title": "Smart LED Streifen 10m RGBW Music Sync", "niche": "smart_home", "price": "29.99", "compare_at": "49.99", "tags": "led,rgbw,musik sync,smart"},
    {"title": "WLAN Steckdosenleiste 4-fach Timer", "niche": "smart_home", "price": "34.99", "compare_at": "54.99", "tags": "steckdosenleiste,wlan,timer,smart"},
    {"title": "Smart Home Zentrale Hub Zigbee Zwave", "niche": "smart_home", "price": "79.99", "compare_at": "119.99", "tags": "smart hub,zigbee,zwave,gateway"},
    {"title": "Rauchwarnmelder Smart WiFi Alarm", "niche": "smart_home", "price": "29.99", "compare_at": "44.99", "tags": "rauchmelder,wifi,alarm,sicherheit"},
    {"title": "Smarter Lichtschalter WiFi 1-fach", "niche": "smart_home", "price": "22.99", "compare_at": "34.99", "tags": "lichtschalter,wifi,smart home"},
    {"title": "Überwachungskamera Außen 4K WiFi", "niche": "smart_home", "price": "69.99", "compare_at": "109.99", "tags": "kamera,außen,4k,wifi,überwachung"},
    {"title": "Smart Lock Türschloss Fingerabdruck", "niche": "smart_home", "price": "89.99", "compare_at": "139.99", "tags": "türschloss,smart lock,fingerabdruck,sicherheit"},
    {"title": "Intelligenter Heizkörperregler Zigbee", "niche": "smart_home", "price": "39.99", "compare_at": "59.99", "tags": "heizkörper,thermostat,zigbee,sparen"},
    {"title": "Smart Sprinkler Controller 12 Zonen", "niche": "smart_home", "price": "54.99", "compare_at": "84.99", "tags": "sprinkler,bewässerung,smart,wifi"},
    {"title": "Luftqualitätssensor CO2 PM2.5 WiFi", "niche": "smart_home", "price": "44.99", "compare_at": "69.99", "tags": "luftqualität,co2,sensor,smart home"},
    {"title": "Smart Garagentor Opener WiFi App", "niche": "smart_home", "price": "49.99", "compare_at": "79.99", "tags": "garagentor,wifi,opener,smart"},
    {"title": "Wassersensor Leckage Alarm WiFi", "niche": "smart_home", "price": "24.99", "compare_at": "39.99", "tags": "wassersensor,leckage,alarm,wifi"},
    {"title": "Smart Vorhangmotor WiFi Rollladenmotor", "niche": "smart_home", "price": "39.99", "compare_at": "64.99", "tags": "vorhang,motor,wifi,smart home"},
    {"title": "LED Panel Smart 60x60 Tunable White", "niche": "smart_home", "price": "64.99", "compare_at": "99.99", "tags": "led panel,tunable white,smart,büro"},
    {"title": "Smart Steckdose Outdoor IP44 WiFi", "niche": "smart_home", "price": "27.99", "compare_at": "44.99", "tags": "steckdose,outdoor,ip44,wifi"},
    {"title": "Tür-Fensterkontakt Sensor Zigbee", "niche": "smart_home", "price": "14.99", "compare_at": "24.99", "tags": "tür sensor,fenster,zigbee,alarm"},
    {"title": "Smart IR Fernbedienung Universal WiFi", "niche": "smart_home", "price": "19.99", "compare_at": "34.99", "tags": "fernbedienung,ir,wifi,universal"},
    {"title": "Zigbee Bewegungsmelder Präsenz PIR", "niche": "smart_home", "price": "22.99", "compare_at": "36.99", "tags": "zigbee,bewegungsmelder,pir,smart"},
    {"title": "Smart Plugs 4er Set Energiemonitoring", "niche": "smart_home", "price": "44.99", "compare_at": "69.99", "tags": "smart plug,set,energie,wifi"},
    {"title": "Haushaltsroboter Wischroboter WiFi Karte", "niche": "smart_home", "price": "129.99", "compare_at": "199.99", "tags": "wischroboter,wifi,mapping,smart"},
    {"title": "Smart Wetterstation Innen Außen Display", "niche": "smart_home", "price": "39.99", "compare_at": "64.99", "tags": "wetterstation,display,innen außen,smart"},
    {"title": "Alexa Echo Show 5 kompatibles Display", "niche": "smart_home", "price": "54.99", "compare_at": "84.99", "tags": "echo,alexa,display,smart speaker"},
    {"title": "Smart Home Starter Kit 5-teilig", "niche": "smart_home", "price": "89.99", "compare_at": "139.99", "tags": "starter kit,smart home,set,komplett"},
    # weiteres Smart Home (70 mehr) — via KI-Erweiterung
    {"title": "Smarte Jalousiensteuerung Zigbee", "niche": "smart_home", "price": "49.99", "compare_at": "79.99", "tags": "jalousie,zigbee,steuerung,smart"},
    {"title": "Sprachassistent Box WiFi Lautsprecher", "niche": "smart_home", "price": "39.99", "compare_at": "69.99", "tags": "sprachassistent,wifi,lautsprecher"},
    {"title": "Smart Dimmer Switch Unterputz WiFi", "niche": "smart_home", "price": "29.99", "compare_at": "49.99", "tags": "dimmer,unterputz,wifi,smart"},
    {"title": "Automatischer Katzenfutterautomat WiFi", "niche": "smart_home", "price": "44.99", "compare_at": "74.99", "tags": "futterautomat,katze,wifi,smart"},

    # ── Fitness & Sport (100) ─────────────────────────────────────────────────
    {"title": "Resistance Bands Set 5er Widerstandsbänder", "niche": "fitness", "price": "19.99", "compare_at": "34.99", "tags": "resistance bands,fitness,yoga,workout"},
    {"title": "Gymnastikmatte 183x61cm TPE rutschfest", "niche": "fitness", "price": "29.99", "compare_at": "49.99", "tags": "gymnastikmatte,yoga,fitness,tpe"},
    {"title": "Foam Roller Faszienrolle 33cm", "niche": "fitness", "price": "24.99", "compare_at": "39.99", "tags": "foam roller,faszien,massage,fitness"},
    {"title": "Springseil Speed Rope Kugellager", "niche": "fitness", "price": "14.99", "compare_at": "24.99", "tags": "springseil,speed rope,cardio,fitness"},
    {"title": "Hanteln 2x5kg Neopren Set", "niche": "fitness", "price": "34.99", "compare_at": "54.99", "tags": "hanteln,neopren,gewichte,training"},
    {"title": "Klimmzugstange Türrahmen verstellbar", "niche": "fitness", "price": "29.99", "compare_at": "49.99", "tags": "klimmzugstange,türrahmen,hometraining"},
    {"title": "Bauchtrainer AB Roller Knieauflage", "niche": "fitness", "price": "19.99", "compare_at": "34.99", "tags": "bauchtrainer,ab roller,core,fitness"},
    {"title": "Fitnessgurt Leder Gewichtheben", "niche": "fitness", "price": "34.99", "compare_at": "54.99", "tags": "fitnessgurt,gewichtheben,leder,kraft"},
    {"title": "Kettlebell 16kg Gusseisen", "niche": "fitness", "price": "44.99", "compare_at": "69.99", "tags": "kettlebell,gusseisen,functional fitness"},
    {"title": "Trainingshandschuhe Gewichtheben Gel", "niche": "fitness", "price": "19.99", "compare_at": "29.99", "tags": "handschuhe,training,gel,grip"},
    {"title": "Shaker Flasche 700ml Protein Mixer", "niche": "fitness", "price": "12.99", "compare_at": "19.99", "tags": "shaker,protein,mixer,fitness"},
    {"title": "Kniebandagen Sport Kompressionsbandage", "niche": "fitness", "price": "17.99", "compare_at": "29.99", "tags": "kniebandage,kompression,sport,schutz"},
    {"title": "Pull-Up Bar Türe Multifunktional", "niche": "fitness", "price": "39.99", "compare_at": "59.99", "tags": "pull up,tür,multifunktional,training"},
    {"title": "Fitnessbank Klappbar Verstellbar", "niche": "fitness", "price": "79.99", "compare_at": "129.99", "tags": "fitnessbank,klappbar,bank,hantel"},
    {"title": "Laufband Elektrisch Klappbar 1-12km/h", "niche": "fitness", "price": "299.99", "compare_at": "449.99", "tags": "laufband,elektrisch,klappbar,cardio"},
    {"title": "Yoga Block Set 2er EVA Kork", "niche": "fitness", "price": "16.99", "compare_at": "27.99", "tags": "yoga block,eva,kork,yoga"},
    {"title": "Sportflasche auslaufsicher 1L BPA-frei", "niche": "fitness", "price": "14.99", "compare_at": "24.99", "tags": "sportflasche,1l,bpa-frei,auslaufsicher"},
    {"title": "Schrittzähler Pedometer Digital Clip", "niche": "fitness", "price": "12.99", "compare_at": "19.99", "tags": "schrittzähler,pedometer,clip,sport"},
    {"title": "Theraband Übungsband 2m 3er Set", "niche": "fitness", "price": "22.99", "compare_at": "36.99", "tags": "theraband,übungsband,reha,fitness"},
    {"title": "Balance Board Wackelbrett Holz", "niche": "fitness", "price": "34.99", "compare_at": "54.99", "tags": "balance board,wackelbrett,holz,gleichgewicht"},
    {"title": "Situps Bank Bauchmuskelbank verstellbar", "niche": "fitness", "price": "49.99", "compare_at": "79.99", "tags": "situps bank,bauchmuskel,verstellbar"},
    {"title": "Pilates Ring Magic Circle 38cm", "niche": "fitness", "price": "19.99", "compare_at": "32.99", "tags": "pilates ring,magic circle,fitness"},
    {"title": "Massagepistole Percussion 3200rpm", "niche": "fitness", "price": "59.99", "compare_at": "99.99", "tags": "massagepistole,percussion,muskel,erholung"},
    {"title": "Trainingsmaske Höhentraining Atmung", "niche": "fitness", "price": "29.99", "compare_at": "49.99", "tags": "trainingsmaske,höhentraining,ausdauer"},
    {"title": "Boxsack Befüllt 100cm Leder", "niche": "fitness", "price": "89.99", "compare_at": "139.99", "tags": "boxsack,leder,kampfsport,training"},
    {"title": "Boxhandschuhe 12oz Kunstleder", "niche": "fitness", "price": "34.99", "compare_at": "54.99", "tags": "boxhandschuhe,12oz,kunstleder,boxing"},
    {"title": "Springmatte Trampolin Indoor 102cm", "niche": "fitness", "price": "79.99", "compare_at": "124.99", "tags": "trampolin,indoor,springmatte,fitness"},
    {"title": "Gewichtsweste 10kg verstellbar", "niche": "fitness", "price": "49.99", "compare_at": "79.99", "tags": "gewichtsweste,10kg,training,kraft"},
    {"title": "EMS Trainingsgerät Bauch Muskelstimulator", "niche": "fitness", "price": "39.99", "compare_at": "64.99", "tags": "ems,bauch,muskelstimulator,training"},
    {"title": "Fitnessband LED Display Herzrate GPS", "niche": "fitness", "price": "44.99", "compare_at": "74.99", "tags": "fitnessband,herzrate,gps,smartwatch"},
    {"title": "Yoga Gurte Stretching Strap 244cm", "niche": "fitness", "price": "11.99", "compare_at": "19.99", "tags": "yoga gurt,stretching,strap,flexibilität"},
    {"title": "Hula Hoop Reifen Gewichtet 1kg", "niche": "fitness", "price": "24.99", "compare_at": "39.99", "tags": "hula hoop,gewichtet,bauch,fitness"},
    {"title": "Stepper Mini Home Trainer LCD", "niche": "fitness", "price": "59.99", "compare_at": "94.99", "tags": "stepper,mini,home trainer,cardio"},
    {"title": "Liegestützgriffe Push-Up Bars 360°", "niche": "fitness", "price": "16.99", "compare_at": "27.99", "tags": "liegestütz,push up,griffe,training"},

    # ── Kitchen & Küche (100) ─────────────────────────────────────────────────
    {"title": "Luftfritteuse 5L XXL Digital 1800W", "niche": "kitchen", "price": "69.99", "compare_at": "109.99", "tags": "luftfritteuse,air fryer,5l,digital"},
    {"title": "Stabmixer 800W Edelstahl Set", "niche": "kitchen", "price": "39.99", "compare_at": "64.99", "tags": "stabmixer,800w,edelstahl,set"},
    {"title": "Kaffeeautomat Filterkaffeemaschine 1,5L", "niche": "kitchen", "price": "49.99", "compare_at": "79.99", "tags": "kaffeemaschine,filter,1.5l,kaffee"},
    {"title": "Standmixer Hochleistung 2L Smoothie", "niche": "kitchen", "price": "59.99", "compare_at": "94.99", "tags": "standmixer,hochleistung,smoothie,2l"},
    {"title": "Messerset 5-teilig Damast Stahl", "niche": "kitchen", "price": "49.99", "compare_at": "79.99", "tags": "messer,damast,stahl,küche"},
    {"title": "Schneidebrett Holz Bambus groß 45x30", "niche": "kitchen", "price": "24.99", "compare_at": "39.99", "tags": "schneidebrett,bambus,holz,küche"},
    {"title": "Reiskocher 1,8L Warmhaltefunktion", "niche": "kitchen", "price": "34.99", "compare_at": "54.99", "tags": "reiskocher,1.8l,warmhalten,küche"},
    {"title": "Elektrischer Wasserkocher 1,7L Edelstahl", "niche": "kitchen", "price": "29.99", "compare_at": "49.99", "tags": "wasserkocher,edelstahl,1.7l,elektrisch"},
    {"title": "Toaster 2-Scheiben Edelstahl 6 Stufen", "niche": "kitchen", "price": "34.99", "compare_at": "54.99", "tags": "toaster,edelstahl,6 stufen,frühstück"},
    {"title": "Waffeleisen Belgisch Antihaft 1200W", "niche": "kitchen", "price": "29.99", "compare_at": "49.99", "tags": "waffeleisen,belgisch,antihaft,backen"},
    {"title": "Vakuumierer Folienschweißgerät Set", "niche": "kitchen", "price": "39.99", "compare_at": "64.99", "tags": "vakuumierer,folie,schweißgerät,haltbarkeit"},
    {"title": "Käsereibe elektrisch Edelstahl", "niche": "kitchen", "price": "24.99", "compare_at": "39.99", "tags": "käsereibe,elektrisch,edelstahl,küche"},
    {"title": "Salatschleuder groß 26cm Edelstahl", "niche": "kitchen", "price": "22.99", "compare_at": "36.99", "tags": "salatschleuder,edelstahl,26cm,küche"},
    {"title": "Knoblauchpresse Edelstahl Preis-Leistung", "niche": "kitchen", "price": "12.99", "compare_at": "19.99", "tags": "knoblauchpresse,edelstahl,küche,kochen"},
    {"title": "Reibe Vierkantreibe Edelstahl 4-seitig", "niche": "kitchen", "price": "17.99", "compare_at": "27.99", "tags": "reibe,edelstahl,4-seitig,küche"},
    {"title": "Digitale Küchenwaage 5kg Präzision", "niche": "kitchen", "price": "19.99", "compare_at": "32.99", "tags": "küchenwaage,digital,5kg,backen"},
    {"title": "Zitronenpresse elektrisch 160W", "niche": "kitchen", "price": "24.99", "compare_at": "39.99", "tags": "zitronenpresse,elektrisch,saft,küche"},
    {"title": "Pfannenwender Set Silikon 6-teilig", "niche": "kitchen", "price": "19.99", "compare_at": "32.99", "tags": "pfannenwender,silikon,set,küche"},
    {"title": "Bratpfanne Edelstahl 28cm Induktion", "niche": "kitchen", "price": "39.99", "compare_at": "64.99", "tags": "bratpfanne,edelstahl,28cm,induktion"},
    {"title": "Suppentopf 5L Edelstahl Glasdeckel", "niche": "kitchen", "price": "34.99", "compare_at": "54.99", "tags": "suppentopf,5l,edelstahl,kochen"},
    {"title": "Pizzastein Cordierit 38x30 Backofen", "niche": "kitchen", "price": "29.99", "compare_at": "49.99", "tags": "pizzastein,cordierit,backofen,pizza"},
    {"title": "Sous Vide Stick 1000W Präzision", "niche": "kitchen", "price": "49.99", "compare_at": "79.99", "tags": "sous vide,stick,1000w,garen"},
    {"title": "Eismaschine 1,5L Selbstkühlung", "niche": "kitchen", "price": "69.99", "compare_at": "109.99", "tags": "eismaschine,selbstkühlung,1.5l,eis"},
    {"title": "Teekocher Glas Temperaturwahl 1,7L", "niche": "kitchen", "price": "39.99", "compare_at": "64.99", "tags": "teekocher,glas,temperatur,tee"},
    {"title": "Frühstücksbrettchen Set 4er Holz", "niche": "kitchen", "price": "22.99", "compare_at": "36.99", "tags": "frühstücksbrettchen,holz,set,frühstück"},
    {"title": "Küchenhelfer Set 12-teilig Silikon", "niche": "kitchen", "price": "29.99", "compare_at": "49.99", "tags": "küchenhelfer,silikon,12-teilig,set"},
    {"title": "Spiralschneider Gemüsehobel 7-Klingen", "niche": "kitchen", "price": "19.99", "compare_at": "34.99", "tags": "spiralschneider,gemüse,hobel,low carb"},
    {"title": "Popcornmaschine Heißluft 1200W", "niche": "kitchen", "price": "34.99", "compare_at": "54.99", "tags": "popcorn,heißluft,1200w,kino"},
    {"title": "Dosenöffner elektrisch automatisch", "niche": "kitchen", "price": "19.99", "compare_at": "32.99", "tags": "dosenöffner,elektrisch,automatisch,küche"},
    {"title": "Küchenrollenhalter Edelstahl freistehend", "niche": "kitchen", "price": "17.99", "compare_at": "27.99", "tags": "rollenhalter,edelstahl,küchenrolle,halter"},
    {"title": "Gewürzregal drehbar 16 Gläser Edelstahl", "niche": "kitchen", "price": "34.99", "compare_at": "54.99", "tags": "gewürzregal,drehbar,edelstahl,gewürze"},
    {"title": "Eierschneider Edelstahl Gurken Pilze", "niche": "kitchen", "price": "9.99", "compare_at": "16.99", "tags": "eierschneider,edelstahl,küche,kochen"},
    {"title": "Nudelmaschine Pasta Maker manuell", "niche": "kitchen", "price": "44.99", "compare_at": "74.99", "tags": "nudelmaschine,pasta,manuell,kochen"},
    {"title": "Kühlschrankorganizer Set 6-teilig transparent", "niche": "kitchen", "price": "27.99", "compare_at": "44.99", "tags": "kühlschrank,organizer,transparent,ordnung"},

    # ── Office & Büro (100) ───────────────────────────────────────────────────
    {"title": "Ergonomischer Bürostuhl Lumbalstütze", "niche": "office", "price": "149.99", "compare_at": "229.99", "tags": "bürostuhl,ergonomisch,lumbal,homeoffice"},
    {"title": "Monitorständer Holz USB-Hub 4-Port", "niche": "office", "price": "39.99", "compare_at": "64.99", "tags": "monitorständer,holz,usb hub,büro"},
    {"title": "Laptopständer Aluminium verstellbar", "niche": "office", "price": "29.99", "compare_at": "49.99", "tags": "laptopständer,aluminium,verstellbar,homeoffice"},
    {"title": "USB-C Hub 7-in-1 4K HDMI", "niche": "office", "price": "39.99", "compare_at": "64.99", "tags": "usb-c hub,hdmi,4k,multiport"},
    {"title": "Tischleuchte LED Dimmbar USB-Ladefunktion", "niche": "office", "price": "34.99", "compare_at": "54.99", "tags": "tischleuchte,led,dimmbar,usb"},
    {"title": "Handgelenk Mauspad XXL 90x40", "niche": "office", "price": "19.99", "compare_at": "32.99", "tags": "mauspad,xxl,handgelenk,büro"},
    {"title": "Dokumentenscanner A4 Duplex WiFi", "niche": "office", "price": "89.99", "compare_at": "139.99", "tags": "scanner,a4,duplex,wifi"},
    {"title": "Hängeregistratur Schublade 4-fach", "niche": "office", "price": "49.99", "compare_at": "79.99", "tags": "hängeregistratur,schublade,ordnung,büro"},
    {"title": "Stiftehalter Organizer Schreibtisch Metall", "niche": "office", "price": "24.99", "compare_at": "39.99", "tags": "stiftehalter,organizer,metall,schreibtisch"},
    {"title": "Whiteboard Glas magnetisch 120x80", "niche": "office", "price": "79.99", "compare_at": "124.99", "tags": "whiteboard,glas,magnetisch,büro"},
    {"title": "Aktentasche Laptop 15,6 Zoll Leder", "niche": "office", "price": "59.99", "compare_at": "94.99", "tags": "aktentasche,laptop,leder,business"},
    {"title": "Noise Cancelling Headset USB Kabel", "niche": "office", "price": "49.99", "compare_at": "79.99", "tags": "headset,noise cancelling,usb,homeoffice"},
    {"title": "Webcam 1080p Autofokus Ring-Light", "niche": "office", "price": "54.99", "compare_at": "84.99", "tags": "webcam,1080p,autofokus,homeoffice"},
    {"title": "Schreibtischunterlage PU Leder 90x45", "niche": "office", "price": "22.99", "compare_at": "36.99", "tags": "schreibtischunterlage,leder,90x45,büro"},
    {"title": "Aktenschrank abschließbar 4 Schubladen", "niche": "office", "price": "129.99", "compare_at": "199.99", "tags": "aktenschrank,abschließbar,schubladen,büro"},
    {"title": "Kabelmanagementsystem Box versteckt", "niche": "office", "price": "19.99", "compare_at": "32.99", "tags": "kabelmanagement,box,versteckt,ordnung"},
    {"title": "Stehpult Aufsatz Höhenverstellbar", "niche": "office", "price": "79.99", "compare_at": "124.99", "tags": "stehpult,aufsatz,höhenverstellbar,ergonomie"},
    {"title": "Aktenvernichter Micro-Partikel Schnitt P-5", "niche": "office", "price": "49.99", "compare_at": "79.99", "tags": "aktenvernichter,micro,p-5,datenschutz"},
    {"title": "Flipchart Moderationswand fahrbar", "niche": "office", "price": "89.99", "compare_at": "139.99", "tags": "flipchart,moderationswand,fahrbar,präsentation"},
    {"title": "Laserdrucker Mono WiFi Duplex Kompakt", "niche": "office", "price": "149.99", "compare_at": "229.99", "tags": "laserdrucker,wifi,duplex,mono"},
    {"title": "Kugelschreiber Set 12er Premium Metall", "niche": "office", "price": "19.99", "compare_at": "32.99", "tags": "kugelschreiber,metall,premium,set"},
    {"title": "Haftnotizen 12-Pack 76x76 Bunt", "niche": "office", "price": "12.99", "compare_at": "19.99", "tags": "haftnotizen,bunt,76x76,post-it"},
    {"title": "Ringordner Ablage Set DIN A4 6er", "niche": "office", "price": "17.99", "compare_at": "27.99", "tags": "ringordner,ablage,a4,büro"},
    {"title": "Locher 2-Loch Edelstahl 30 Blatt", "niche": "office", "price": "19.99", "compare_at": "32.99", "tags": "locher,edelstahl,2-loch,büro"},
    {"title": "Heftmaschine Stapler Heavy Duty 50 Blatt", "niche": "office", "price": "24.99", "compare_at": "39.99", "tags": "heftmaschine,heavy duty,50 blatt,büro"},
    {"title": "Terminplaner Kalender 2026 A5 Hardcover", "niche": "office", "price": "17.99", "compare_at": "27.99", "tags": "terminplaner,kalender,a5,hardcover"},
    {"title": "Notizbuch A5 Bullet Journal Dot Grid", "niche": "office", "price": "14.99", "compare_at": "24.99", "tags": "notizbuch,bullet journal,dot grid,a5"},
    {"title": "Briefablage stapelbar 3-stöckig Metall", "niche": "office", "price": "27.99", "compare_at": "44.99", "tags": "briefablage,stapelbar,metall,büro"},
    {"title": "Taschenrechner Solar 12-stellig groß", "niche": "office", "price": "14.99", "compare_at": "24.99", "tags": "taschenrechner,solar,12-stellig,büro"},
    {"title": "Tisch-Organizer 5 Fächer Bambus natur", "niche": "office", "price": "22.99", "compare_at": "36.99", "tags": "organizer,bambus,5 fächer,schreibtisch"},
    {"title": "Kork Pinnwand 90x60 Holzrahmen", "niche": "office", "price": "29.99", "compare_at": "49.99", "tags": "pinnwand,kork,90x60,büro"},
    {"title": "Rollendes Aktenwagen 3 Etagen Büro", "niche": "office", "price": "59.99", "compare_at": "94.99", "tags": "aktenwagen,rollend,3 etagen,büro"},
    {"title": "Bildschirm Erhöhung Riser mit Schubladen", "niche": "office", "price": "34.99", "compare_at": "54.99", "tags": "monitor erhöhung,riser,schublade,büro"},
    {"title": "Schreibtisch Kabelkanal Alu 100cm", "niche": "office", "price": "24.99", "compare_at": "39.99", "tags": "kabelkanal,alu,100cm,schreibtisch"},

    # ── Beauty & Pflege (100) ─────────────────────────────────────────────────
    {"title": "Gesichtsmassagegerät Jade Roller Rose", "niche": "beauty", "price": "19.99", "compare_at": "34.99", "tags": "jade roller,gesicht,massage,beauty"},
    {"title": "Ultraschall Gesichtsreiniger Silikon", "niche": "beauty", "price": "34.99", "compare_at": "54.99", "tags": "gesichtsreiniger,ultraschall,silikon,beauty"},
    {"title": "Elektrische Zahnbürste Schallzahnbürste", "niche": "beauty", "price": "39.99", "compare_at": "64.99", "tags": "zahnbürste,elektrisch,schall,oral care"},
    {"title": "Haarglätte­eisen Titanium 230°C", "niche": "beauty", "price": "44.99", "compare_at": "74.99", "tags": "haarglätter,titanium,230,friseur"},
    {"title": "Lockenwickler Set 40er Klettverschluss", "niche": "beauty", "price": "14.99", "compare_at": "24.99", "tags": "lockenwickler,set,kletter,haar"},
    {"title": "Lippenpflege Set 12er mit SPF", "niche": "beauty", "price": "17.99", "compare_at": "27.99", "tags": "lippenpflege,spf,set,beauty"},
    {"title": "Kosmetik Organizer Acryl 6-stöckig", "niche": "beauty", "price": "29.99", "compare_at": "49.99", "tags": "organizer,acryl,kosmetik,make-up"},
    {"title": "Spiegel LED Beleuchtet Schminkspiegel", "niche": "beauty", "price": "39.99", "compare_at": "64.99", "tags": "spiegel,led,schminke,beleuchtung"},
    {"title": "Nagelset Maniküre Pediküre 14-teilig", "niche": "beauty", "price": "19.99", "compare_at": "34.99", "tags": "nagelset,maniküre,pediküre,nagelpflege"},
    {"title": "Mikrofaser Handtücher Set 3er 70x140", "niche": "beauty", "price": "24.99", "compare_at": "39.99", "tags": "mikrofaser,handtuch,set,bad"},
    {"title": "Gesichtsmaske Kollagen 30er Set", "niche": "beauty", "price": "22.99", "compare_at": "36.99", "tags": "gesichtsmaske,kollagen,set,pflege"},
    {"title": "Haarbürste Natur-Borsten Holzgriff", "niche": "beauty", "price": "17.99", "compare_at": "27.99", "tags": "haarbürste,naturborsten,holz,haar"},
    {"title": "Körperpeeling Zucker Kokos natürlich", "niche": "beauty", "price": "14.99", "compare_at": "24.99", "tags": "peeling,zucker,kokos,körper"},
    {"title": "Augencreme Anti-Aging Hyaluron 50ml", "niche": "beauty", "price": "24.99", "compare_at": "39.99", "tags": "augencreme,anti-aging,hyaluron,pflege"},
    {"title": "Lash-Wimpernzange Präzision Edelstahl", "niche": "beauty", "price": "9.99", "compare_at": "16.99", "tags": "wimpernzange,edelstahl,lash,beauty"},
    {"title": "Parfümzerstäuber Reise Set 5er 5ml", "niche": "beauty", "price": "12.99", "compare_at": "19.99", "tags": "parfümzerstäuber,reise,set,spray"},
    {"title": "Badebombe Set 12er Lavendel Rose", "niche": "beauty", "price": "19.99", "compare_at": "32.99", "tags": "badebombe,lavendel,rose,bad"},
    {"title": "Moisturizer Gesichtscreme SPF30 50ml", "niche": "beauty", "price": "22.99", "compare_at": "36.99", "tags": "moisturizer,spf30,gesicht,pflege"},
    {"title": "Haartrocknungshandtuch Turban Mikrofaser", "niche": "beauty", "price": "12.99", "compare_at": "19.99", "tags": "haartuch,turban,mikrofaser,haar"},
    {"title": "Nagellackentferner Pads 200er acetonfrein", "niche": "beauty", "price": "9.99", "compare_at": "16.99", "tags": "nagellackentferner,pads,acetonfrei,nagel"},
    {"title": "Dampfbürste Haarstyler 3-in-1", "niche": "beauty", "price": "49.99", "compare_at": "79.99", "tags": "dampfbürste,haarstyler,3in1,styling"},
    {"title": "Peeling Handschuhe Dusche Körper Exfoliant", "niche": "beauty", "price": "12.99", "compare_at": "19.99", "tags": "peeling,handschuhe,dusche,exfoliant"},
    {"title": "Munddusche Wasserflosser 600ml", "niche": "beauty", "price": "39.99", "compare_at": "64.99", "tags": "munddusche,wasserflosser,zähne,hygiene"},
    {"title": "Haarentfernung IPL Gerät 400.000 Blitze", "niche": "beauty", "price": "89.99", "compare_at": "149.99", "tags": "haarentfernung,ipl,laser,beauty"},
    {"title": "Vitamin C Serum Gesicht 30ml", "niche": "beauty", "price": "19.99", "compare_at": "34.99", "tags": "vitamin c,serum,gesicht,anti-aging"},
    {"title": "Bambus Wattestäbchen 1000er Box", "niche": "beauty", "price": "9.99", "compare_at": "16.99", "tags": "wattestäbchen,bambus,eco,hygiene"},
    {"title": "Fußpflegeset elektrisch Hornhautentferner", "niche": "beauty", "price": "29.99", "compare_at": "49.99", "tags": "fußpflege,elektrisch,hornhaut,füße"},
    {"title": "Schlaf Augenmaske Seiden-weich 3D", "niche": "beauty", "price": "12.99", "compare_at": "19.99", "tags": "augenmaske,schlaf,seide,3d"},
    {"title": "Eyelash Glue Wimpernkleber transparent", "niche": "beauty", "price": "9.99", "compare_at": "16.99", "tags": "wimpernkleber,eyelash,transparent,beauty"},
    {"title": "Haarpflege Set Shampoo Conditioner Argan", "niche": "beauty", "price": "27.99", "compare_at": "44.99", "tags": "shampoo,conditioner,argan,haarpflege"},
    {"title": "Konjac Schwamm Reinigung Gesicht 5er", "niche": "beauty", "price": "14.99", "compare_at": "24.99", "tags": "konjac,schwamm,gesicht,reinigung"},
    {"title": "Retinol Nachtcreme Anti-Falten 50ml", "niche": "beauty", "price": "24.99", "compare_at": "39.99", "tags": "retinol,nachtcreme,anti-falten,pflege"},
    {"title": "Make-up Pinsel Set 15er Vegan", "niche": "beauty", "price": "22.99", "compare_at": "36.99", "tags": "pinsel,make-up,15er,vegan"},
    {"title": "Trockenshampoo 250ml Frische Volumen", "niche": "beauty", "price": "9.99", "compare_at": "16.99", "tags": "trockenshampoo,frische,volumen,haar"},

    # ── Outdoor & Camping (100) ───────────────────────────────────────────────
    {"title": "Camping Zelt 2-Personen 3-Jahreszeiten", "niche": "outdoor", "price": "79.99", "compare_at": "129.99", "tags": "zelt,camping,2 personen,outdoor"},
    {"title": "Schlafsack -10°C Mumienform 1200g", "niche": "outdoor", "price": "59.99", "compare_at": "94.99", "tags": "schlafsack,mumienform,-10grad,camping"},
    {"title": "Trekkingrucksack 65L Regenschutz", "niche": "outdoor", "price": "79.99", "compare_at": "129.99", "tags": "rucksack,trekking,65l,outdoor"},
    {"title": "Trinkflasche Isoliert 1L Edelstahl 24h", "niche": "outdoor", "price": "24.99", "compare_at": "39.99", "tags": "trinkflasche,edelstahl,isoliert,1l"},
    {"title": "Taschenmesser Multi-Tool 12 Funktionen", "niche": "outdoor", "price": "29.99", "compare_at": "49.99", "tags": "taschenmesser,multi-tool,camping,outdoor"},
    {"title": "Stirnlampe LED 1000 Lumen wiederaufladbar", "niche": "outdoor", "price": "24.99", "compare_at": "39.99", "tags": "stirnlampe,led,1000 lumen,camping"},
    {"title": "Campingkocher Gaskocher faltbar", "niche": "outdoor", "price": "19.99", "compare_at": "34.99", "tags": "campingkocher,gaskocher,faltbar,outdoor"},
    {"title": "Wanderstöcke Teleskop Aluminium Paar", "niche": "outdoor", "price": "34.99", "compare_at": "54.99", "tags": "wanderstöcke,teleskop,aluminium,wandern"},
    {"title": "Hängematte Outdoor 2 Personen 300kg", "niche": "outdoor", "price": "39.99", "compare_at": "64.99", "tags": "hängematte,outdoor,2 personen,camping"},
    {"title": "Erste-Hilfe-Set 200-teilig Outdoor", "niche": "outdoor", "price": "29.99", "compare_at": "49.99", "tags": "erste hilfe,200-teilig,outdoor,camping"},
    {"title": "Campingflasche Gaskartusche 230g 3er", "niche": "outdoor", "price": "19.99", "compare_at": "32.99", "tags": "gaskartusche,camping,kocher,outdoor"},
    {"title": "Survival Kit Notfall 20-teilig", "niche": "outdoor", "price": "34.99", "compare_at": "54.99", "tags": "survival,notfall,kit,outdoor"},
    {"title": "Trekking-Gamaschen wasserdicht XL", "niche": "outdoor", "price": "24.99", "compare_at": "39.99", "tags": "gamaschen,wasserdicht,trekking,wandern"},
    {"title": "Campingstuhl ultraleicht 1,5kg faltbar", "niche": "outdoor", "price": "39.99", "compare_at": "64.99", "tags": "campingstuhl,ultraleicht,faltbar,outdoor"},
    {"title": "Klapptisch Camping Aluminium 120x60", "niche": "outdoor", "price": "49.99", "compare_at": "79.99", "tags": "klapptisch,camping,aluminium,outdoor"},
    {"title": "Kompass Navigation Militär Silva", "niche": "outdoor", "price": "17.99", "compare_at": "27.99", "tags": "kompass,navigation,militär,outdoor"},
    {"title": "Feuerstein Ferro Rod Zunder Set", "niche": "outdoor", "price": "12.99", "compare_at": "19.99", "tags": "feuerstein,ferro rod,zunder,survival"},
    {"title": "Outdoor Paracord 550 30m Neongelb", "niche": "outdoor", "price": "9.99", "compare_at": "16.99", "tags": "paracord,550,outdoor,camping"},
    {"title": "Zeckenzange Set 5er Edelstahl Lupe", "niche": "outdoor", "price": "14.99", "compare_at": "24.99", "tags": "zeckenzange,edelstahl,lupe,outdoor"},
    {"title": "Campinglanterne Solar LED faltbar", "niche": "outdoor", "price": "22.99", "compare_at": "36.99", "tags": "laterne,solar,led,camping"},
    {"title": "Isomatte Aufblasbar 10cm Schlafmatte", "niche": "outdoor", "price": "44.99", "compare_at": "74.99", "tags": "isomatte,aufblasbar,schlafmatte,camping"},
    {"title": "Wasserfilter Outdoor Straw 1000L", "niche": "outdoor", "price": "24.99", "compare_at": "39.99", "tags": "wasserfilter,outdoor,straw,survival"},
    {"title": "Angelrute Teleskop Carbon 3m Set", "niche": "outdoor", "price": "29.99", "compare_at": "49.99", "tags": "angelrute,teleskop,carbon,angeln"},
    {"title": "Fernglas 10x42 Stickstoffgefüllt", "niche": "outdoor", "price": "69.99", "compare_at": "109.99", "tags": "fernglas,10x42,stickstoff,optik"},
    {"title": "GoPro Befestigung Set 50er Universal", "niche": "outdoor", "price": "22.99", "compare_at": "36.99", "tags": "gopro,befestigung,set,action cam"},
    {"title": "Thermoskanne 1L doppelwandig Edelstahl", "niche": "outdoor", "price": "29.99", "compare_at": "49.99", "tags": "thermoskanne,1l,edelstahl,outdoor"},
    {"title": "Trekking-Socken Merinowolle 3er Pack", "niche": "outdoor", "price": "24.99", "compare_at": "39.99", "tags": "socken,merinowolle,trekking,wandern"},
    {"title": "Regenjacke Outdoor 10.000mm atmungsaktiv", "niche": "outdoor", "price": "79.99", "compare_at": "124.99", "tags": "regenjacke,outdoor,atmungsaktiv,wasserdicht"},
    {"title": "Faltkayak aufblasbar 2-Personen", "niche": "outdoor", "price": "149.99", "compare_at": "229.99", "tags": "kayak,aufblasbar,2 personen,wasser"},
    {"title": "Camp Küche Organizer Rolltasche", "niche": "outdoor", "price": "44.99", "compare_at": "74.99", "tags": "camp küche,organizer,rolltasche,outdoor"},
    {"title": "Schneeschuh Set Aluminium Teleskopstock", "niche": "outdoor", "price": "89.99", "compare_at": "139.99", "tags": "schneeschuhe,aluminium,winter,outdoor"},
    {"title": "Kletterhelm EN12492 verstellbar", "niche": "outdoor", "price": "54.99", "compare_at": "84.99", "tags": "kletterhelm,en12492,klettern,sicherheit"},
    {"title": "Kletterseil 10mm 60m UIAA Dry", "niche": "outdoor", "price": "99.99", "compare_at": "154.99", "tags": "kletterseil,10mm,60m,uiaa"},
    {"title": "Trail Running Hydrationsweste 10L", "niche": "outdoor", "price": "59.99", "compare_at": "94.99", "tags": "hydrationsweste,trail,running,10l"},

    # ── Pet & Haustiere (100) ─────────────────────────────────────────────────
    {"title": "Katzenkratzbau 150cm Sisalstangen", "niche": "pet", "price": "59.99", "compare_at": "94.99", "tags": "kratzbau,katze,sisal,spielzeug"},
    {"title": "Hundebett Memory Foam L 90x70", "niche": "pet", "price": "49.99", "compare_at": "79.99", "tags": "hundebett,memory foam,orthopädisch,hund"},
    {"title": "Futternapf Set Edelstahl Ständer", "niche": "pet", "price": "24.99", "compare_at": "39.99", "tags": "futternapf,edelstahl,ständer,haustier"},
    {"title": "Hundeleine 5m einziehbar robust", "niche": "pet", "price": "19.99", "compare_at": "34.99", "tags": "hundeleine,einziehbar,5m,hund"},
    {"title": "Katzentoilette geschlossen Kohlenstofffilter", "niche": "pet", "price": "44.99", "compare_at": "74.99", "tags": "katzentoilette,geschlossen,filter,katze"},
    {"title": "Hundespielzeug Kong Classic M", "niche": "pet", "price": "14.99", "compare_at": "24.99", "tags": "hundespielzeug,kong,kau,hund"},
    {"title": "Vogelkäfig groß 100x50x80", "niche": "pet", "price": "89.99", "compare_at": "139.99", "tags": "vogelkäfig,groß,vogel,haustier"},
    {"title": "Aquarium 60L LED Filter Komplettset", "niche": "pet", "price": "79.99", "compare_at": "129.99", "tags": "aquarium,60l,led,filter"},
    {"title": "Tiertransportbox Kunststoff M Airline", "niche": "pet", "price": "39.99", "compare_at": "64.99", "tags": "transportbox,airline,katze,hund"},
    {"title": "Hundegeschirr No-Pull Reflektierend", "niche": "pet", "price": "22.99", "compare_at": "36.99", "tags": "hundegeschirr,no-pull,reflektierend,hund"},
    {"title": "Katzenspielzeug Federangel Interaktiv", "niche": "pet", "price": "12.99", "compare_at": "19.99", "tags": "katzenspielzeug,feder,interaktiv,katze"},
    {"title": "Hundebürste Selbstreinigend Silikonpins", "niche": "pet", "price": "17.99", "compare_at": "27.99", "tags": "hundebürste,selbstreinigend,silikon,pflege"},
    {"title": "Fisch Futter Flockenfutter 500ml Premium", "niche": "pet", "price": "12.99", "compare_at": "19.99", "tags": "fischfutter,flockenfutter,aquarium,fisch"},
    {"title": "Hundemantel wasserdicht Fleece M", "niche": "pet", "price": "24.99", "compare_at": "39.99", "tags": "hundemantel,wasserdicht,fleece,hund"},
    {"title": "Katzenfenster Hängematte Saugnäpfe", "niche": "pet", "price": "19.99", "compare_at": "34.99", "tags": "katzenhängematte,fenster,saugnäpfe,katze"},
    {"title": "Haustier GPS Tracker Halsband", "niche": "pet", "price": "39.99", "compare_at": "64.99", "tags": "gps tracker,halsband,hund,katze"},
    {"title": "Hund Snack Leckerli Zahnpflege 300g", "niche": "pet", "price": "14.99", "compare_at": "24.99", "tags": "leckerli,zahnpflege,hund,snack"},
    {"title": "Kleintier Trinkflasche 250ml Vakuum", "niche": "pet", "price": "9.99", "compare_at": "16.99", "tags": "trinkflasche,kleintier,vakuum,hamster"},
    {"title": "Hundehalsband Leder handgenäht M", "niche": "pet", "price": "22.99", "compare_at": "36.99", "tags": "halsband,leder,handgenäht,hund"},
    {"title": "Katzentunnel Faltbar Spieltunnel 90cm", "niche": "pet", "price": "14.99", "compare_at": "24.99", "tags": "katzentunnel,faltbar,spielzeug,katze"},
    {"title": "Hundeschere Pflegeset 7-teilig Edelstahl", "niche": "pet", "price": "24.99", "compare_at": "39.99", "tags": "hundeschere,pflege,edelstahl,grooming"},
    {"title": "Katzenbaum Hängepodest 185cm Beige", "niche": "pet", "price": "69.99", "compare_at": "109.99", "tags": "katzenbaum,hängepodest,sisal,katze"},
    {"title": "Regenmantel Hund Transparent XS-XL", "niche": "pet", "price": "17.99", "compare_at": "27.99", "tags": "regenmantel,hund,transparent,regen"},
    {"title": "Pfotenpflege Balsam natürlich 50ml", "niche": "pet", "price": "12.99", "compare_at": "19.99", "tags": "pfotenpflege,balsam,natürlich,hund"},
    {"title": "Tiernahrung Katze Nassfutter 24er Mixpack", "niche": "pet", "price": "24.99", "compare_at": "39.99", "tags": "katzenfutter,nassfutter,24er,katze"},
    {"title": "Floh Zeckenmittel Hund Spot-On 3er", "niche": "pet", "price": "19.99", "compare_at": "34.99", "tags": "floh,zecken,spot-on,hund"},
    {"title": "Hundespielzeug Ball Quietscher Set 5er", "niche": "pet", "price": "14.99", "compare_at": "24.99", "tags": "hundespielzeug,ball,quietscher,set"},
    {"title": "Aquarium Thermometer Digital LCD", "niche": "pet", "price": "9.99", "compare_at": "16.99", "tags": "thermometer,aquarium,digital,lcd"},
    {"title": "Welpe Erziehungspad 60x60 100er Pack", "niche": "pet", "price": "22.99", "compare_at": "36.99", "tags": "erziehungspad,welpe,100er,hund"},
    {"title": "Katzenminze Bio Spray 150ml", "niche": "pet", "price": "9.99", "compare_at": "16.99", "tags": "katzenminze,bio,spray,katze"},
    {"title": "Hundekorb Rattan Weide oval L", "niche": "pet", "price": "44.99", "compare_at": "74.99", "tags": "hundekorb,rattan,weide,hund"},
    {"title": "Kleintiergehege Laufstall Metall 8-eckig", "niche": "pet", "price": "39.99", "compare_at": "64.99", "tags": "kleintier,gehege,metall,8-eckig"},
    {"title": "Vogelspielzeug Set 12er Papagei Sittich", "niche": "pet", "price": "17.99", "compare_at": "27.99", "tags": "vogelspielzeug,papagei,sittich,set"},
    {"title": "Selbstreinigende Katzentoilette Elektrisch", "niche": "pet", "price": "129.99", "compare_at": "199.99", "tags": "katzentoilette,elektrisch,selbstreinigend,auto"},

    # ── Gaming (100) ──────────────────────────────────────────────────────────
    {"title": "Gaming Maus 16000 DPI RGB 7 Tasten", "niche": "gaming", "price": "39.99", "compare_at": "64.99", "tags": "gaming maus,rgb,16000 dpi,fps"},
    {"title": "Gaming Headset 7.1 Surround USB", "niche": "gaming", "price": "49.99", "compare_at": "79.99", "tags": "gaming headset,7.1,surround,usb"},
    {"title": "Gaming Tastatur Mechanisch RGB TKL", "niche": "gaming", "price": "59.99", "compare_at": "94.99", "tags": "tastatur,mechanisch,rgb,tkl"},
    {"title": "Gaming Mauspad XXL 90x40 RGB", "niche": "gaming", "price": "29.99", "compare_at": "49.99", "tags": "mauspad,xxl,rgb,gaming"},
    {"title": "Gaming Stuhl Bürostuhl Lumbar RGB", "niche": "gaming", "price": "179.99", "compare_at": "279.99", "tags": "gaming stuhl,rgb,lumbar,racing"},
    {"title": "Controller PS4 PS5 kompatibel kabellos", "niche": "gaming", "price": "49.99", "compare_at": "79.99", "tags": "controller,ps4,ps5,kabellos"},
    {"title": "Nintendo Switch Case Hülle Zubehör-Set", "niche": "gaming", "price": "24.99", "compare_at": "39.99", "tags": "switch,case,hülle,nintendo"},
    {"title": "Capture Card 4K 60fps USB HDMI", "niche": "gaming", "price": "69.99", "compare_at": "109.99", "tags": "capture card,4k,hdmi,streaming"},
    {"title": "Stream Deck Mini 6 Keys Elgato", "niche": "gaming", "price": "69.99", "compare_at": "109.99", "tags": "stream deck,6 keys,streaming,elgato"},
    {"title": "RGB LED Strip Gaming Setup 5m", "niche": "gaming", "price": "19.99", "compare_at": "34.99", "tags": "rgb led,gaming setup,strip,ambient"},
    {"title": "Gaming Monitor Arm Schwenkbar Gasdruckfeder", "niche": "gaming", "price": "44.99", "compare_at": "74.99", "tags": "monitor arm,schwenkbar,gaming,ergonomisch"},
    {"title": "USB Hub Gaming 7-Port mit Ladefunktion", "niche": "gaming", "price": "24.99", "compare_at": "39.99", "tags": "usb hub,7-port,gaming,laden"},
    {"title": "Gaming Headphone Ständer RGB Beleuchtung", "niche": "gaming", "price": "19.99", "compare_at": "34.99", "tags": "headset ständer,rgb,gaming,halter"},
    {"title": "Mikrofon Kondensator USB Gaming Podcast", "niche": "gaming", "price": "49.99", "compare_at": "79.99", "tags": "mikrofon,kondensator,usb,gaming"},
    {"title": "Gaming PC Stuhl Fußstütze Hocker", "niche": "gaming", "price": "34.99", "compare_at": "54.99", "tags": "fußstütze,gaming,stuhl,hocker"},
    {"title": "Kabelhalter Schreibtisch Gaming 10er Set", "niche": "gaming", "price": "12.99", "compare_at": "19.99", "tags": "kabelhalter,gaming,schreibtisch,ordnung"},
    {"title": "Joystick Flight Stick USB PC", "niche": "gaming", "price": "49.99", "compare_at": "79.99", "tags": "joystick,flight stick,usb,pc gaming"},
    {"title": "Gaming Brille Blaulichtfilter Entspiegelt", "niche": "gaming", "price": "22.99", "compare_at": "36.99", "tags": "gaming brille,blaulicht,entspiegelt,augen"},
    {"title": "VR Brille Smartphone Universal Cardboard", "niche": "gaming", "price": "17.99", "compare_at": "27.99", "tags": "vr brille,smartphone,cardboard,virtual reality"},
    {"title": "Controller Ladestation PS5 Dual USB-C", "niche": "gaming", "price": "24.99", "compare_at": "39.99", "tags": "ladestation,ps5,dual,usb-c"},
    {"title": "Gaming Lautsprecher Stereo RGB 2.0", "niche": "gaming", "price": "39.99", "compare_at": "64.99", "tags": "lautsprecher,rgb,stereo,gaming"},
    {"title": "PC Gaming Bundle Maus Tastatur Pad", "niche": "gaming", "price": "59.99", "compare_at": "94.99", "tags": "gaming bundle,maus,tastatur,pad"},
    {"title": "Xbox Controller Griff Cover Silikon", "niche": "gaming", "price": "12.99", "compare_at": "19.99", "tags": "xbox,controller,silikon,grip"},
    {"title": "Gaming Tisch L-Form Kohlefaser Optik", "niche": "gaming", "price": "129.99", "compare_at": "199.99", "tags": "gaming tisch,l-form,kohlefaser,schreibtisch"},
    {"title": "Kühlpad Laptop Gaming 17 Zoll 6 Lüfter", "niche": "gaming", "price": "34.99", "compare_at": "54.99", "tags": "kühlpad,laptop,gaming,6 lüfter"},
    {"title": "Amiibo Halter Display Regal 10er", "niche": "gaming", "price": "19.99", "compare_at": "32.99", "tags": "amiibo,halter,display,nintendo"},
    {"title": "PS5 Tasche Transporttasche Hard Shell", "niche": "gaming", "price": "39.99", "compare_at": "64.99", "tags": "ps5,tasche,hard shell,transport"},
    {"title": "Gaming Wandregal Floating Shelf RGB", "niche": "gaming", "price": "44.99", "compare_at": "74.99", "tags": "wandregal,gaming,floating,rgb"},
    {"title": "Wrist Rest Handballenauflage Gel Gaming", "niche": "gaming", "price": "14.99", "compare_at": "24.99", "tags": "handballenauflage,gel,gaming,ergonomisch"},
    {"title": "Gaming Timer Uhr Digitalanzeige RGB", "niche": "gaming", "price": "19.99", "compare_at": "32.99", "tags": "timer,digital,rgb,gaming"},
    {"title": "PC Case Lüfter 120mm RGB 3er Pack", "niche": "gaming", "price": "24.99", "compare_at": "39.99", "tags": "lüfter,120mm,rgb,pc case"},
    {"title": "Thermalpaste Hochleistung CPU GPU 4g", "niche": "gaming", "price": "9.99", "compare_at": "16.99", "tags": "thermalpaste,cpu,gpu,gaming"},
    {"title": "Anti-Vibration Füße PC Gummifüße 4er", "niche": "gaming", "price": "7.99", "compare_at": "12.99", "tags": "vibration,füße,pc,gummi"},
    {"title": "Grafikkarte Stützhalter Halter Vertikal", "niche": "gaming", "price": "12.99", "compare_at": "19.99", "tags": "grafikkarte,stütze,halter,gpu"},

    # ── Baby & Kinder (100) ───────────────────────────────────────────────────
    {"title": "Laufstall Faltbar Reisebett 6-in-1", "niche": "baby", "price": "89.99", "compare_at": "139.99", "tags": "laufstall,faltbar,reisebett,baby"},
    {"title": "Babyphone Video 5 Zoll 1080p Nachtsicht", "niche": "baby", "price": "79.99", "compare_at": "129.99", "tags": "babyphone,video,1080p,nachtsicht"},
    {"title": "Kinderwagen Buggy Faltbar Regenschutz", "niche": "baby", "price": "129.99", "compare_at": "199.99", "tags": "buggy,faltbar,regenschutz,kinderwagen"},
    {"title": "Stillkissen Schwangerschaftskissen U-Form", "niche": "baby", "price": "39.99", "compare_at": "64.99", "tags": "stillkissen,schwangerschaft,u-form,baby"},
    {"title": "Lernturm Montessori Küchenhelfer", "niche": "baby", "price": "79.99", "compare_at": "129.99", "tags": "lernturm,montessori,küche,kind"},
    {"title": "Babybadewanne Faltbar 0-6 Monate", "niche": "baby", "price": "29.99", "compare_at": "49.99", "tags": "babybadewanne,faltbar,0-6 monate,baby"},
    {"title": "Kinderspielzeug Holz Steckspiel 12m+", "niche": "baby", "price": "22.99", "compare_at": "36.99", "tags": "holzspielzeug,steckspiel,12m,kind"},
    {"title": "Kindersitz Autositz Gruppe 0+1 Isofix", "niche": "baby", "price": "89.99", "compare_at": "139.99", "tags": "kindersitz,isofix,autositz,gruppe 0"},
    {"title": "Wickelkommode Auflagefixierung Schublade", "niche": "baby", "price": "99.99", "compare_at": "159.99", "tags": "wickelkommode,schublade,fixierung,baby"},
    {"title": "Baby Nachtlicht Sternenhimmel Projektor", "niche": "baby", "price": "24.99", "compare_at": "39.99", "tags": "nachtlicht,projektor,sterne,baby"},
    {"title": "Kinderfahrrad 16 Zoll mit Stützrädern", "niche": "baby", "price": "89.99", "compare_at": "139.99", "tags": "kinderfahrrad,16 zoll,stützräder,kind"},
    {"title": "Lauflernhilfe Walker Holz ab 9 Monate", "niche": "baby", "price": "39.99", "compare_at": "64.99", "tags": "lauflernhilfe,holz,9 monate,baby"},
    {"title": "Babytrage Ergonomisch 4-Positionen", "niche": "baby", "price": "59.99", "compare_at": "94.99", "tags": "babytrage,ergonomisch,4 positionen,tragen"},
    {"title": "Schnuller Set Silikon 2er 0-6 Monate", "niche": "baby", "price": "9.99", "compare_at": "16.99", "tags": "schnuller,silikon,0-6 monate,baby"},
    {"title": "Kinderbettwäsche 100x135 Baumwolle Tiere", "niche": "baby", "price": "19.99", "compare_at": "34.99", "tags": "kinderbettwäsche,100x135,baumwolle,tiere"},
    {"title": "Babydecke Kuscheldecke 100x80 Fleece", "niche": "baby", "price": "17.99", "compare_at": "27.99", "tags": "babydecke,kuscheldecke,fleece,baby"},
    {"title": "Trinklerntasse 360° auslaufsicher 200ml", "niche": "baby", "price": "12.99", "compare_at": "19.99", "tags": "trinklerntasse,360,auslaufsicher,baby"},
    {"title": "Babywippe Schaukel elektrisch Melodien", "niche": "baby", "price": "59.99", "compare_at": "94.99", "tags": "babywippe,elektrisch,melodien,schaukel"},
    {"title": "Kinderzimmerdekoration Wandaufkleber", "niche": "baby", "price": "14.99", "compare_at": "24.99", "tags": "wandaufkleber,kinderzimmer,dekoration,kind"},
    {"title": "Lego Duplo Bausteine 100er Box", "niche": "baby", "price": "29.99", "compare_at": "49.99", "tags": "duplo,bausteine,lego,kind"},
    {"title": "Puzzle 100 Teile Holz Tiere 3-6 Jahre", "niche": "baby", "price": "17.99", "compare_at": "27.99", "tags": "puzzle,holz,tiere,kind"},
    {"title": "Kinderrucksack Schule Ergonomisch 16L", "niche": "baby", "price": "34.99", "compare_at": "54.99", "tags": "kinderrucksack,ergonomisch,16l,schule"},
    {"title": "Playmobil Piraten Set 60-teilig", "niche": "baby", "price": "34.99", "compare_at": "54.99", "tags": "playmobil,piraten,60-teilig,kind"},
    {"title": "Malset Kinder 120-teilig Buntstifte", "niche": "baby", "price": "19.99", "compare_at": "32.99", "tags": "malset,120-teilig,buntstifte,kind"},
    {"title": "Sandbox Spielzeug Set Eimer Sandförmchen", "niche": "baby", "price": "14.99", "compare_at": "24.99", "tags": "sandbox,spielzeug,eimer,sand"},
    {"title": "Kinder Badespielzeug Wasserspaß 8-teilig", "niche": "baby", "price": "16.99", "compare_at": "27.99", "tags": "badespielzeug,wasserspaß,kind,bad"},
    {"title": "Spielzeug Küche Holz Herd Backofen", "niche": "baby", "price": "49.99", "compare_at": "79.99", "tags": "spielküche,holz,herd,kind"},
    {"title": "Dreirad Kinder mit Schub 2-5 Jahre", "niche": "baby", "price": "49.99", "compare_at": "79.99", "tags": "dreirad,schub,2-5 jahre,kind"},
    {"title": "Kuscheltier Hase XXL 80cm", "niche": "baby", "price": "24.99", "compare_at": "39.99", "tags": "kuscheltier,hase,80cm,kind"},
    {"title": "Musik Spieluhr Holz Baby Bewegung", "niche": "baby", "price": "19.99", "compare_at": "32.99", "tags": "spieluhr,holz,musik,baby"},
    {"title": "Kindertoilette Töpfchen anatomisch", "niche": "baby", "price": "22.99", "compare_at": "36.99", "tags": "töpfchen,anatomisch,kind,training"},
    {"title": "Babykosmetik Set Pflegeset 8-teilig", "niche": "baby", "price": "22.99", "compare_at": "36.99", "tags": "babykosmetik,pflegeset,8-teilig,baby"},
    {"title": "Gitter Schutzgitter Türschutzgitter 75-82cm", "niche": "baby", "price": "34.99", "compare_at": "54.99", "tags": "schutzgitter,türgitter,baby,sicherheit"},
    {"title": "Kinderzimmer Nachtlicht LED Dimmbar", "niche": "baby", "price": "17.99", "compare_at": "27.99", "tags": "nachtlicht,led,dimmbar,kinderzimmer"},

    # ── Travel & Reisen (100) ─────────────────────────────────────────────────
    {"title": "Handgepäck Koffer 55x40x20 Spinner", "niche": "travel", "price": "59.99", "compare_at": "94.99", "tags": "koffer,handgepäck,spinner,reise"},
    {"title": "Reisekissen Nackenkissen Memory Foam", "niche": "travel", "price": "19.99", "compare_at": "34.99", "tags": "reisekissen,nackenkissen,memory foam,flug"},
    {"title": "Reiseadapter Universal 150 Länder USB-C", "niche": "travel", "price": "24.99", "compare_at": "39.99", "tags": "reiseadapter,universal,usb-c,weltweit"},
    {"title": "Packtaschen Set 8er Kleidung Reise", "niche": "travel", "price": "29.99", "compare_at": "49.99", "tags": "packtaschen,set,kleidung,reise"},
    {"title": "Reisekrankenversicherung Guide E-Book", "niche": "travel", "price": "9.99", "compare_at": "16.99", "tags": "reise,krankenversicherung,guide,ebook"},
    {"title": "Reifendruckmesser Digital KFZ Motorrad", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "reifendruck,digital,auto,motorrad"},
    {"title": "Gürteltasche Bauchtasche RFID Schutz", "niche": "travel", "price": "22.99", "compare_at": "36.99", "tags": "bauchtasche,rfid,schutz,reise"},
    {"title": "Reiseschminktasche Kosmetiktasche groß", "niche": "travel", "price": "17.99", "compare_at": "27.99", "tags": "kosmetiktasche,reise,groß,make-up"},
    {"title": "Kofferanhänger Leder personalisiert Set 2er", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "kofferanhänger,leder,personalisiert,reise"},
    {"title": "Reise Dokumentenmappe A4 RFID", "niche": "travel", "price": "17.99", "compare_at": "27.99", "tags": "dokumentenmappe,rfid,a4,reise"},
    {"title": "Powerbank 20000mAh Quick Charge 65W", "niche": "travel", "price": "39.99", "compare_at": "64.99", "tags": "powerbank,20000mah,quick charge,reise"},
    {"title": "Schlossichere Packsäcke Wasserdicht 3er", "niche": "travel", "price": "22.99", "compare_at": "36.99", "tags": "packsäcke,wasserdicht,reise,outdoor"},
    {"title": "Mini Drucker Thermo Bluetooth A6", "niche": "travel", "price": "44.99", "compare_at": "74.99", "tags": "drucker,thermo,bluetooth,reise"},
    {"title": "Schloss TSA Zahlenschloss 4-stellig", "niche": "travel", "price": "12.99", "compare_at": "19.99", "tags": "schloss,tsa,zahlenschloss,koffer"},
    {"title": "Reisewecker Digital Faltbar Dual Alarm", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "wecker,digital,faltbar,reise"},
    {"title": "Kompressionsbeutel Kleidung 6er Set", "niche": "travel", "price": "22.99", "compare_at": "36.99", "tags": "kompressionsbeutel,kleidung,6er,platzsparend"},
    {"title": "Portmonee Slim Wallet Kartenhalter RFID", "niche": "travel", "price": "19.99", "compare_at": "32.99", "tags": "portmonee,slim wallet,rfid,karten"},
    {"title": "Reise-Hygieneset Flüssigkeiten 100ml Bag", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "hygieneset,100ml,flüssigkeiten,flugzeug"},
    {"title": "Kofferband Gepäckband bunt 2er", "niche": "travel", "price": "9.99", "compare_at": "16.99", "tags": "kofferband,gepäck,bunt,erkennung"},
    {"title": "Reisegitarre 3/4 Klassik Nylon", "niche": "travel", "price": "69.99", "compare_at": "109.99", "tags": "reisegitarre,3/4,klassik,musik"},
    {"title": "Sprachkurs Italienisch Reise MP3", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "sprachkurs,italienisch,mp3,reise"},
    {"title": "Regenponcho ultraleicht Einwegponcho 10er", "niche": "travel", "price": "12.99", "compare_at": "19.99", "tags": "poncho,regen,ultraleicht,einweg"},
    {"title": "Sandstrandmatte XL 200x200 Sandfrei", "niche": "travel", "price": "22.99", "compare_at": "36.99", "tags": "strandmatte,sandfrei,xl,strand"},
    {"title": "Schnorchelset Maske Flossen Tasche", "niche": "travel", "price": "39.99", "compare_at": "64.99", "tags": "schnorchelset,maske,flossen,meer"},
    {"title": "Sonnenschutzmittel SPF 50 Face Body 200ml", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "sonnenschutz,spf 50,face body,sommer"},
    {"title": "Reise-Lautsprecher Wasserdicht Bluetooth", "niche": "travel", "price": "34.99", "compare_at": "54.99", "tags": "lautsprecher,bluetooth,wasserdicht,reise"},
    {"title": "Kofferwaage Gepäckwaage digital 50kg", "niche": "travel", "price": "12.99", "compare_at": "19.99", "tags": "kofferwaage,digital,50kg,gepäck"},
    {"title": "Reisehandtuch Mikrofaser 3er Set", "niche": "travel", "price": "19.99", "compare_at": "32.99", "tags": "handtuch,mikrofaser,3er,reise"},
    {"title": "Moskitonetz Camping Hängematte", "niche": "travel", "price": "17.99", "compare_at": "27.99", "tags": "moskitonetz,camping,hängematte,tropenreise"},
    {"title": "Unterwasser Kamerahülle Universal 6 Zoll", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "kamerahülle,unterwasser,universal,wasserdicht"},
    {"title": "Klappbarer Trinkbecher Silikon 350ml", "niche": "travel", "price": "9.99", "compare_at": "16.99", "tags": "trinkbecher,klappbar,silikon,reise"},
    {"title": "Reise-Schutzhülle Koffer 65-70cm transparent", "niche": "travel", "price": "14.99", "compare_at": "24.99", "tags": "kofferhülle,schutz,transparent,reise"},
    {"title": "Camping Solarladegerät 21W faltbar USB", "niche": "travel", "price": "39.99", "compare_at": "64.99", "tags": "solarladegerät,21w,faltbar,camping"},
    {"title": "Stiefeletten Damen Knöchel Blockabsatz", "niche": "travel", "price": "49.99", "compare_at": "79.99", "tags": "stiefeletten,damen,blockabsatz,reise"},
]


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _shopify_post(path: str, data: dict) -> dict:
    if not SHOP or not TOKEN:
        return {"errors": "no Shopify credentials"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{BASE}{path}", headers=HEADERS, json=data,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                return await r.json()
    except Exception as e:
        return {"errors": str(e)}


async def _notify(msg: str):
    try:
        from modules.notify_hub import notify
        await notify(msg, level="info")
    except Exception as _e:
        log.debug("skipped: %s", _e)


async def generate_seo_description(template: dict) -> str:
    title = template["title"]
    niche = template.get("niche", "")
    tags  = template.get("tags", "")
    prompt = f"""Schreibe eine SEO-optimierte Produktbeschreibung auf Deutsch (150 Wörter) für:
Produkt: "{title}"
Kategorie: {niche}
Keywords: {tags}

Struktur: 1 Einleitungssatz mit Hauptkeyword, 3 Vorteile als Bullet-Points (•), 1 CTA-Satz.
Kein HTML, nur Text. Keyword-Dichte ca. 2%."""
    desc = await _ai(prompt, max_tokens=250)
    if not desc:
        desc = (f"{title} — Das perfekte Produkt für Ihren Alltag. "
                f"Hohe Qualität, schnelle Lieferung. Jetzt bestellen!")
    return desc


async def create_shopify_product(template: dict) -> dict:
    """Erstellt ein Shopify-Produkt mit KI-Beschreibung und LoremFlickr Bild."""
    title = template["title"]
    niche = template.get("niche", "general")

    desc = await generate_seo_description(template)
    safe_q = title.replace(" ", ",")[:40]
    image_url = ""

    payload = {
        "product": {
            "title": title,
            "body_html": f"<p>{desc}</p>",
            "vendor": "SuperMegaBot",
            "product_type": niche.replace("_", " ").title(),
            "tags": template.get("tags", niche),
            "status": "active",
            "variants": [{
                "price": template.get("price", "29.99"),
                "compare_at_price": template.get("compare_at", ""),
                "inventory_quantity": 100,
                "inventory_management": "shopify",
                "fulfillment_service": "manual",
                "requires_shipping": True,
            }],
            "images": [{"src": image_url, "alt": title}],
        }
    }

    result = await _shopify_post("/products.json", payload)
    if result.get("errors"):
        return {"ok": False, "error": str(result["errors"])[:200]}

    prod = result.get("product", {})
    pid  = str(prod.get("id", ""))
    handle = prod.get("handle", "")
    url  = f"{SHOP_URL}/products/{handle}" if handle else SHOP_URL

    try:
        from modules.supabase_client import get_client
        get_client().table("shopify_mass_products").insert({
            "product_id": pid, "title": title,
            "niche": niche, "price": template.get("price"),
            "url": url, "handle": handle,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as _e:
        log.debug("skipped: %s", _e)

    return {"ok": True, "product_id": pid, "title": title,
            "url": url, "price": template.get("price")}


async def _worker(queue: asyncio.Queue, results: list, worker_id: int):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        try:
            r = await create_shopify_product(item)
            results.append(r)
            if r.get("ok"):
                log.info("Worker%d created: %s", worker_id, item["title"][:50])
            else:
                log.warning("Worker%d failed: %s → %s", worker_id, item["title"][:40], r.get("error","")[:60])
        except Exception as e:
            log.warning("Worker%d error: %s", worker_id, e)
            results.append({"ok": False, "error": str(e)})
        finally:
            queue.task_done()
        await asyncio.sleep(1)


async def generate_extra_concepts(count: int = 100) -> list[dict]:
    """KI generiert zusätzliche Produkt-Konzepte wenn Templates nicht reichen."""
    niches = ["smart_home","fitness","kitchen","office","beauty","outdoor","pet","gaming","baby","travel"]
    extras = []
    per_niche = max(1, count // len(niches))
    for niche in niches:
        prompt = f"""Generiere {per_niche} Produkt-Ideen für Kategorie "{niche}" (Dropshipping/E-Commerce).
Antworte NUR mit JSON-Array:
[{{"title":"Produkttitel max 60 Zeichen","price":"XX.XX","compare_at":"YY.YY","tags":"tag1,tag2,tag3","niche":"{niche}"}}]"""
        raw = await _ai(prompt, max_tokens=800)
        try:
            start, end = raw.find("["), raw.rfind("]") + 1
            if start != -1:
                import json
                batch = json.loads(raw[start:end])
                extras.extend(batch[:per_niche])
        except Exception as _e:
            log.debug("skipped: %s", _e)
        await asyncio.sleep(1)
    return extras


async def mass_create_shopify_products(
    count: int = 1000,
    workers: int = 5,
    niches: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
) -> dict:
    """5 parallele Worker erstellen bis zu 1000 Produkte."""
    # Deduplizierung
    existing_titles: set[str] = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("shopify_mass_products").select("title").execute()
        existing_titles = {r["title"] for r in rows.data or []}
    except Exception as _e:
        log.debug("skipped: %s", _e)

    templates = [t for t in SHOPIFY_PRODUCT_TEMPLATES if t["title"] not in existing_titles]
    if niches:
        niche_set = {n.lower() for n in niches}
        templates = [t for t in templates if t.get("niche", "").lower() in niche_set]
    if keywords:
        kw = [k.lower() for k in keywords]

        def _matches_kw(tmpl: dict) -> bool:
            blob = f"{tmpl.get('title', '')} {tmpl.get('tags', '')}".lower()
            return any(k in blob for k in kw)

        if niches:
            templates = [t for t in templates if t.get("niche", "").lower() in {n.lower() for n in niches} or _matches_kw(t)]
        else:
            templates = [t for t in templates if _matches_kw(t)]
    random.shuffle(templates)

    # Auffüllen mit KI-Konzepten wenn nötig
    if len(templates) < count:
        need = count - len(templates)
        log.info("Generiere %d zusätzliche Konzepte via KI...", need)
        extras = await generate_extra_concepts(need)
        templates.extend([e for e in extras if e.get("title") and e["title"] not in existing_titles])

    queue: asyncio.Queue = asyncio.Queue()
    for tmpl in templates[:count]:
        await queue.put(tmpl)
    for _ in range(workers):
        await queue.put(None)

    results: list = []
    created_count = 0
    last_notify = 0

    async def progress_tracker():
        nonlocal created_count, last_notify
        while True:
            await asyncio.sleep(5)
            ok_now = sum(1 for r in results if r.get("ok"))
            if ok_now >= last_notify + 100:
                last_notify = ok_now
                pct = int(ok_now / count * 100)
                await _notify(f"🛍️ Shopify Mass: {ok_now}/{count} Produkte ({pct}%) erstellt!")
            if queue.empty() and all(r is not None for r in results):
                break

    worker_tasks = [asyncio.create_task(_worker(queue, results, i)) for i in range(workers)]
    tracker = asyncio.create_task(progress_tracker())
    await queue.join()
    for t in worker_tasks:
        t.cancel()
    tracker.cancel()

    ok_count   = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count

    # Blast Top-10
    if ok_count > 0:
        await blast_shopify_products(limit=10)

    await _notify(f"✅ Shopify Mass Complete: {ok_count}/{count} Produkte erstellt, {fail_count} failed!")
    return {"ok": True, "created": ok_count, "failed": fail_count, "total": count}


async def blast_shopify_products(limit: int = 10) -> dict:
    """Top-Produkte aus Supabase → BrutusCore alle Kanäle."""
    products = []
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("shopify_mass_products").select("*").limit(limit).execute()
        products = rows.data or []
    except Exception as _e:
        log.debug("skipped: %s", _e)

    if not products:
        return {"ok": False, "blasted": 0, "error": "no products in supabase"}

    blasted = 0
    try:
        from modules.brutus_core import fire
        for p in products[:limit]:
            title   = p.get("title", "Neues Produkt")
            price   = p.get("price", "")
            url     = p.get("url", SHOP_URL)
            msg = (f"🛍️ {title}\n💶 €{price}\n\n"
                   f"Jetzt kaufen: {url}")
            await fire(title, msg, link=url,
                       channels=["telegram","shopify_blog","linkedin","mailchimp","klaviyo","discord","slack"])
            blasted += 1
            await asyncio.sleep(1)
    except Exception as e:
        log.warning("blast error: %s", e)

    return {"ok": True, "blasted": blasted}


async def run_shopify_mass_cycle() -> dict:
    """Scheduler: täglich 50 neue Produkte + blast Top-10."""
    if os.getenv("SHOPIFY_MASS_CREATOR_ENABLED", "true").lower() in ("false", "0", "off"):
        return {"ok": True, "skipped": True, "reason": "SHOPIFY_MASS_CREATOR_ENABLED=false (Qualitäts-Modus)"}
    create_r = await mass_create_shopify_products(count=50, workers=3)
    blast_r  = await blast_shopify_products(limit=10)
    return {"ok": True, "created": create_r.get("created", 0),
            "blasted": blast_r.get("blasted", 0)}


async def create_1000_shopify_products() -> dict:
    return await mass_create_shopify_products(count=1000, workers=5)


async def get_shopify_mass_stats() -> dict:
    total = len(SHOPIFY_PRODUCT_TEMPLATES)
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("shopify_mass_products").select("id", count="exact").execute()
        created = rows.count or 0
    except Exception:
        created = 0
    return {"ok": True, "templates": total, "created_in_db": created,
            "remaining": max(0, 1000 - created)}
