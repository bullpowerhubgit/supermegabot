# Taxonomy Rules — ineedit.com.co
**Stand:** 2026-07-04 | Store: I Want That! I Need It!

---

## Grundprinzip

Jedes Produkt braucht genau EINEN `product_type`, sinnvolle `tags` im `attribute-value`-Format, und gehört zu mindestens EINER Smart Collection.

---

## Product Type — Mapping-Regeln

### Solar & Off-Grid Power
| Keywords im Titel/Body | product_type |
|------------------------|--------------|
| powerstation, power station, solar generator | `Powerstation` |
| balkonkraftwerk, balcony solar, 600w solar, 800w solar | `Balkonkraftwerk` |
| solar panel + battery / kit / set | `Solar-Komplettsystem` |
| solar panel (allein, ohne Set) | `Solar-Panel` |
| mppt, solar laderegler, charge controller | `Solar-Laderegler` |
| lifepo4, lithium battery, power bank solar | `Solarbatterie` |
| solar lamp, solar licht, solar gartenlampe | `Solar-Lampe` |

### Smart Home & Security
| Keywords | product_type |
|----------|--------------|
| ip kamera, security camera, überwachungskamera | `IP-Kamera` |
| türklingel, doorbell, video doorbell | `Video-Türklingel` |
| smart lock, türschloss, biometric lock | `Smart-Schloss` |
| smart plug, wlan steckdose, wifi socket | `Smart-Steckdose` |
| smart bulb, wifi lampe, rgb lampe, led strip smart | `Smart-Lampe` |
| smart thermostat, heizungssteuerung | `Smart-Thermostat` |
| smart hub, gateway, zigbee hub | `Smart-Hub` |
| motion sensor, bewegungsmelder | `Bewegungssensor` |
| door sensor, window sensor, türsensor | `Tür-/Fenstersensor` |
| air quality, luftqualität, pm2.5 sensor | `Luftqualitätssensor` |

### Wearables & Health Tech
| Keywords | product_type |
|----------|--------------|
| smartwatch, smart watch | `Smartwatch` |
| fitness tracker, activity tracker | `Fitness-Tracker` |
| smart ring | `Smart-Ring` |
| bluetooth earbuds, true wireless, tws | `True-Wireless-Earbuds` |
| bluetooth headphones, kopfhörer | `Bluetooth-Kopfhörer` |

### High-Tech Gadgets & Electronics
| Keywords | product_type |
|----------|--------------|
| mini projector, beamer, projektor | `Mini-Beamer` |
| usb-c hub, docking station, multiport | `USB-C-Hub` |
| wireless charger, magsafe, qi charger | `Wireless-Ladepad` |
| bluetooth tracker, gps tracker, airtag | `Bluetooth-Tracker` |
| power bank, powerbank (ohne Solar) | `Powerbank` |
| dashcam, dash camera | `Dashcam` |
| drone, drohne, mini drone | `Drohne` |
| action cam, action camera, gopro alternative | `Action-Kamera` |
| robot vacuum, saugroboter | `Saugroboter` |
| air purifier, luftreiniger | `Luftreiniger` |

### Kitchen & Home Tech (nur mit Smart-Feature)
| Keywords | product_type |
|----------|--------------|
| smart scale, küchenwaage app | `Smart-Küchenwaage` |
| smart coffee, kaffee app | `Smart-Kaffeemaschine` |
| air fryer smart, heißluft app | `Smart-Heißluftfritteuse` |
| milchaufschäumer elektrisch, milk frother | `Elektrischer-Milchaufschäumer` |

---

## Tags — Pflicht-Format: `attribut-wert`

### Segment (immer einer)
- `segment-solar` — alle Solar-Produkte
- `segment-smart-home` — Smart Home / IoT
- `segment-wearable` — Wearables
- `segment-gadget` — High-Tech Gadgets
- `segment-kitchen-tech` — Smart Kitchen

### Feature (mehrere erlaubt)
- `feature-app-control` — App-steuerbar
- `feature-voice-control` — Alexa/Google-Home
- `feature-wifi` — WLAN-fähig
- `feature-bluetooth` — Bluetooth
- `feature-solar` — Solarenergie genutzt
- `feature-battery-backup` — eigener Akku
- `feature-motion-detection` — Bewegungserkennung
- `feature-night-vision` — Nachtsicht
- `feature-waterproof` — wasserdicht (IP65+)
- `feature-fast-charge` — Schnellladen
- `feature-magnetic` — magnetisch/MagSafe

### Battery Type (für Solar/Power)
- `battery-lifepo4` — LiFePO4 Zellen
- `battery-lithium` — Li-Ion
- `battery-none` — kein eigener Akku

### Power/Kapazität (für Solar/Power)
- `power-100w`, `power-200w`, `power-400w`, `power-600w`, `power-800w`
- `capacity-100ah`, `capacity-200wh`, `capacity-500wh`, `capacity-1000wh`

### Verbindung
- `connection-wifi` — WLAN
- `connection-bluetooth` — Bluetooth
- `connection-zigbee` — Zigbee
- `connection-zwave` — Z-Wave

### Audience
- `audience-home` — Haushalt/Wohnen
- `audience-outdoor` — Outdoor/Camping
- `audience-office` — Büro/Home-Office
- `audience-security` — Sicherheit

### Sonstige Pflicht-Tags
- `source-aliexpress` oder `source-cj` oder `source-printify` — Import-Quelle
- `new-arrival` — frisch importiert (30 Tage)

---

## Smart Collections — Aufbau

| Collection-Name | Regel(n) |
|-----------------|----------|
| Solar & Off-Grid Power | `product_type` CONTAINS "Solar" OR CONTAINS "Powerstation" OR CONTAINS "Balkonkraftwerk" OR tag = `segment-solar` |
| Smart Home & Security | `product_type` CONTAINS "IP-Kamera" OR "Smart-" OR "Bewegungssensor" OR tag = `segment-smart-home` |
| Wearables & Health Tech | `product_type` CONTAINS "Smartwatch" OR "Tracker" OR "Earbuds" OR "Kopfhörer" OR tag = `segment-wearable` |
| High-Tech Gadgets | tag = `segment-gadget` |
| Solar-Komplettsysteme | `product_type` = "Solar-Komplettsystem" OR = "Balkonkraftwerk" |
| Powerstations & Speicher | `product_type` = "Powerstation" OR = "Solarbatterie" |
| Smart Kitchen Tech | tag = `segment-kitchen-tech` |
| New Arrivals | tag = `new-arrival` |
| Best Sellers | `product_type` IS NOT EMPTY (sortiert nach Bestseller) |

---

## Was NICHT in den Shop kommt (Ausschlussliste)

- Digitale Produkte (Guides, eBooks, Plans, Apps)
- Kleidung ohne Tech-Feature
- Haushaltswaren ohne Smart-Funktion (Schüsseln, Pfannen, Kissen)
- Tiere / Haustier-Artikel ohne Tech (normales Spielzeug, normale Näpfe)
- Möbel ohne Smart-Feature
- Bücher, Zeitschriften, Papierwaren
- Retro-/Vintage-Produkte
- Produkte ohne Bild → DRAFT bis Bild vorhanden
- Preis = €0 → DRAFT bis Preis gesetzt
