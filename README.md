# Jarvis — One companion. Every device.

**Live:** [https://jarvis-kumar-shaurya.vercel.app/](https://jarvis-kumar-shaurya.vercel.app/) — landing page at `/`, the app at `/mobile/`

## What it is

Jarvis is a personal AI assistant that lives entirely in the cloud. Open the web app, sign in with Google, add your own free Gemini API key, and start chatting. Your chats, notes, memories, and reminders are stored per user in the cloud, so the same account shows the same state on your laptop, phone, or tablet.

There is no shared server API key: every user brings their own Gemini key (free from Google AI Studio), so nobody can spend anyone else's quota.

## Features

- **Chat that remembers the thread** — Jarvis keeps your conversation history, so it can follow up and answer in context.
- **26 tools** — files and notes, reminders, user-approved memory, web search, daily briefing, and browser help on domains you approve.
- **Companion app** — the app at `/mobile/` (also `/companion/`): chat, voice input, stop control, a 3-step setup wizard, synced chat history, and an installable app.
- **Landing page** — a black-hole themed homepage at `/` with live backend status.
- **Confirmations first** — anything that changes your data asks for your approval before it happens, and every action is logged for you to review.
- **Chrome extension** — reads the page you choose and summarises it. It works with a local setup only; it does not use the cloud backend yet.
- **Safety by design** — Jarvis never submits forms, quizzes, exams, or purchases, and never asks you to share passwords or API keys in chat.

## How to start

1. **Open the app** — the Companion at `/mobile/` (or the landing page at `/`, then "Open app").
2. **Sign in with Google** — one tap. Google handles sign-in; no password is typed into Jarvis.
3. **Add your free Gemini key** — Settings → Your Gemini key. Get one free from [Google AI Studio](https://aistudio.google.com/) (Get API key → copy → paste → Save). Your key is encrypted on the server and never shown again.
4. **Start chatting** — ask questions, take notes, set reminders, get a briefing. Sign in on another device and everything is there.

## Usage limits

- **30 Gemini calls per hour, 100 per day, per user** — a guard against runaway use, even with your own key.
- **First reply can take a few seconds** — the app wakes up after being idle. Your sign-in and data are unaffected.
- **No push notifications** — reminders are stored and shown when you open the app.

## Privacy

- Sign-in is required for everything except the public health check — without it, nothing loads.
- You only ever see your own data. Your chats, notes, memories, and reminders belong to your Google account alone.
- Your Gemini key is encrypted, never shown again, and never shared with anyone.
- Jarvis never asks for your passwords, API keys, or card details in chat — and never submits anything in your name.

## Things to know

- **Gmail and Calendar are not available in the cloud app.** They work only in a local setup.
- **Windows-only features** (like opening apps on your laptop) do not work in the cloud app.
- **Browser help** works only on domains you approve, and never submits forms or completes checkouts.
- **No push notifications.** Reminders are stored and shown when you open the app.

## If something goes wrong

- **Chat replies "add your Gemini key"** — no key is saved for your account yet. Go to Settings → Your Gemini key, paste a key from [Google AI Studio](https://aistudio.google.com/), and save it.
- **"Sign-in required"** — your session expired (24 hours). Sign in with Google again from Settings.
- **"Too many requests"** — you hit the hourly or daily cap. Wait a bit and try again.

## Author

**Kumar Shaurya**

- GitHub: [https://github.com/Kshaurya-07](https://github.com/Kshaurya-07)
