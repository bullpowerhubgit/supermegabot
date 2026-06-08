# App Frontend

Modern React frontend application for the Rudibot ecosystem with real-time dashboard and management interface.

## Features

- 🎨 Modern UI with Tailwind CSS and shadcn/ui
- 📊 Real-time dashboard with WebSocket updates
- 🔐 Authentication and user management
- 📱 Responsive design for mobile and desktop
- 🚀 Performance optimized with React 18
- 🔄 Live data synchronization

## Tech Stack

- **Framework**: React 18 with TypeScript
- **Styling**: Tailwind CSS + shadcn/ui components
- **State Management**: React Context + Zustand
- **Routing**: React Router v6
- **Real-time**: Socket.IO Client
- **API**: Axios for HTTP requests
- **Build**: Vite

## Quick Start

```bash
npm install
npm run dev
```

## Development

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run tests
npm run test

# Lint code
npm run lint
```

## Environment Variables

Create a `.env.local` file:

```env
VITE_API_URL=http://localhost:3000
VITE_WS_URL=ws://localhost:3000
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

## Project Structure

```
src/
├── components/          # Reusable UI components
├── pages/              # Page components
├── hooks/              # Custom React hooks
├── stores/             # State management
├── services/           # API services
├── utils/              # Utility functions
├── types/              # TypeScript definitions
└── styles/             # Global styles
```

## License

MIT
