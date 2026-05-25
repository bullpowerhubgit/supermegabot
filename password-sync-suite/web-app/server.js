require('dotenv').config();
const express = require('express');
const session = require('express-session');
const passport = require('passport');
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const bodyParser = require('body-parser');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3005;

const DEFAULT_EMAILS = 'dragonadnp@gmail.com,aiitecbuuss@gmail.com,bullpowersrtkennels@gmail.com';
const ALLOWED_EMAILS = (process.env.ALLOWED_EMAILS || DEFAULT_EMAILS)
  .split(',')
  .map(e => e.trim().toLowerCase())
  .filter(Boolean);

// In-Memory Stores (produktion: Redis / DB)
const syncStore = new Map();
const users = new Map();

app.use(bodyParser.json());
app.use(session({
  secret: process.env.SESSION_SECRET || 'default-secret-change-me',
  resave: false,
  saveUninitialized: false,
  cookie: { secure: false, maxAge: 24 * 60 * 60 * 1000 }
}));
app.use(passport.initialize());
app.use(passport.session());
app.use(express.static(path.join(__dirname, 'public')));

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;

if (GOOGLE_CLIENT_ID && GOOGLE_CLIENT_SECRET) {
  passport.use(new GoogleStrategy({
    clientID: GOOGLE_CLIENT_ID,
    clientSecret: GOOGLE_CLIENT_SECRET,
    callbackURL: '/auth/google/callback'
  }, (accessToken, refreshToken, profile, done) => {
  const email = (profile.emails && profile.emails[0] && profile.emails[0].value) || '';
  const normalized = email.toLowerCase();
  if (!ALLOWED_EMAILS.includes(normalized)) {
    return done(null, false, { message: 'E-Mail nicht autorisiert.' });
  }
  const user = {
    id: profile.id,
    email: normalized,
    name: profile.displayName,
    photo: profile.photos?.[0]?.value,
    accessToken,
    refreshToken
  };
    users.set(normalized, user);
    return done(null, user);
  }));
} else {
  console.warn('[Warn] GOOGLE_CLIENT_ID/SECRET nicht gesetzt. OAuth-Login ist deaktiviert.');
}

passport.serializeUser((user, done) => done(null, user.email));
passport.deserializeUser((email, done) => done(null, users.get(email) || null));

// Routes
if (GOOGLE_CLIENT_ID && GOOGLE_CLIENT_SECRET) {
  app.get('/auth/google',
    passport.authenticate('google', { scope: ['profile', 'email', 'https://www.googleapis.com/auth/gmail.readonly'] })
  );

  app.get('/auth/google/callback',
    passport.authenticate('google', { failureRedirect: '/?error=unauthorized' }),
    (req, res) => res.redirect('/dashboard')
  );
} else {
  app.get('/auth/google', (req, res) => {
    res.status(503).send('<h1>OAuth nicht konfiguriert</h1><p>Bitte .env mit GOOGLE_CLIENT_ID und GOOGLE_CLIENT_SECRET anlegen.</p>');
  });
  app.get('/auth/google/callback', (req, res) => res.redirect('/?error=oauth-not-configured'));
}

app.get('/auth/logout', (req, res) => {
  req.logout(() => res.redirect('/'));
});

app.get('/api/me', (req, res) => {
  if (!req.user) return res.status(401).json({ error: 'Nicht eingeloggt.' });
  res.json({ email: req.user.email, name: req.user.name, photo: req.user.photo });
});

app.get('/api/accounts', (req, res) => {
  if (!req.user) return res.status(401).json({ error: 'Nicht eingeloggt.' });
  const all = ALLOWED_EMAILS.map(email => {
    const u = users.get(email);
    return { email, name: u?.name || email.split('@')[0], connected: !!u };
  });
  res.json(all);
});

// Sync endpoint (called by browser extension)
app.post('/api/sync', (req, res) => {
  const { clientId, accounts, passwords, timestamp } = req.body;
  if (!clientId) return res.status(400).json({ error: 'clientId required' });

  syncStore.set(clientId, {
    accounts,
    passwords,
    lastSync: timestamp || Date.now()
  });

  console.log(`[Sync] Client ${clientId} synced ${passwords?.length || 0} passwords.`);
  res.json({ ok: true, syncedAt: Date.now() });
});

app.get('/api/sync/:clientId', (req, res) => {
  const data = syncStore.get(req.params.clientId);
  if (!data) return res.status(404).json({ error: 'Not found' });
  res.json(data);
});

// Dashboard data
app.get('/api/dashboard', (req, res) => {
  if (!req.user) return res.status(401).json({ error: 'Nicht eingeloggt.' });
  const allPasswords = [];
  for (const [, data] of syncStore) {
    if (data.passwords) allPasswords.push(...data.passwords);
  }
  res.json({
    user: req.user,
    totalPasswords: allPasswords.length,
    clients: syncStore.size,
    accounts: ALLOWED_EMAILS.map(e => ({ email: e, connected: !!users.get(e) }))
  });
});

app.get('/dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Health endpoint (für PM2 + SuperMegaBot Hub)
app.get('/health', (req, res) => {
  res.json({
    ok: true,
    service: 'password-sync-suite',
    port: PORT,
    uptime: Math.floor(process.uptime()),
    clients: syncStore.size,
    oauth: !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET),
    allowedEmails: ALLOWED_EMAILS.length
  });
});

// API Stats (öffentlich — kein Login nötig für Monitoring)
app.get('/api/stats', (req, res) => {
  let totalPasswords = 0;
  for (const [, data] of syncStore) {
    totalPasswords += data.passwords?.length || 0;
  }
  res.json({
    totalPasswords,
    clients: syncStore.size,
    uptime: Math.floor(process.uptime())
  });
});

app.listen(PORT, () => {
  console.log(`[Password Sync Web] http://localhost:${PORT}`);
  console.log(`[Allowed emails] ${ALLOWED_EMAILS.join(', ')}`);
  console.log(`[Health] http://localhost:${PORT}/health`);
});
