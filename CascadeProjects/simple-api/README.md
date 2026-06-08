# Simple API

Kleine Node.js + Express API als Starter.

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

## Routen

- `GET /` Basisinfo
- `GET /health` Healthcheck
- `POST /api/echo` Gibt JSON zurück
- `POST /api/send-test-email` Sendet Test-Mail über Resend

## Beispiel Request

```bash
curl -X POST http://localhost:3000/api/echo \
  -H "Content-Type: application/json" \
  -d '{"hello":"world"}'
```

## Test-Mail

```bash
curl -X POST http://localhost:3000/api/send-test-email \
  -H "Content-Type: application/json" \
  -d '{"to":"deine@email.de","subject":"Test","html":"<h1>Hallo</h1>"}'
```

Dafür brauchst du `RESEND_API_KEY` in deiner `.env`.
