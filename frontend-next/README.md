# AiFactChecker Frontend - Next.js

AI-powered fact checking platform frontend built with Next.js, TypeScript, Tailwind CSS, and shadcn/ui following a "Clean Tech/SaaS" aesthetic with a playful pizza-themed branding.

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Components**: shadcn/ui (Radix primitives + Tailwind)
- **Icons**: Lucide React
- **State Management**: React Query (TanStack Query)
- **API Client**: Axios

## Design System

### Visual Style
- **Clean Tech/SaaS aesthetic** inspired by modern job boards
- **Color Palette**: Slate/Zinc scale with Indigo-600 accent
- **Typography**: Inter font (clean sans-serif)
- **Layout**: Bento grids, high whitespace, minimal design
- **Components**: Rounded cards (rounded-xl), subtle borders, flat design

### Key Features
- ✅ Sticky navbar with smooth scroll effects
- ✅ Command Palette (Cmd+K) with semantic chat search
- ✅ Real-time chat search powered by Qdrant vector DB
- ✅ Responsive bento grid layouts
- ✅ Clean card-based UI
- ✅ Pill-shaped badges for tags
- ✅ Hover effects on interactive elements
- ✅ Custom pizza-themed logo and branding

## Getting Started

### Prerequisites
- Node.js 18+ or Yarn

### Installation

```bash
# Install dependencies
yarn install

# Run development server
yarn dev

# Build for production
yarn build

# Start production server
yarn start
```

The app will be available at [http://localhost:3000](http://localhost:3000)

## Project Structure

```
frontend-next/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx         # Root layout with navbar
│   ├── page.tsx           # Landing page
│   ├── dashboard/         # Dashboard page
│   ├── login/             # Login page
│   ├── register/          # Register page
│   └── chats/             # Chat pages
│       ├── page.tsx       # Chats list
│       └── [id]/          # Individual chat
├── components/            # React components
│   ├── ui/                # shadcn/ui components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   └── command.tsx
│   ├── navbar.tsx         # Main navigation
│   └── command-palette.tsx # Cmd+K semantic search
├── lib/                   # Utilities
│   ├── utils.ts           # cn() utility
│   └── api.ts             # API client & types
├── hooks/                 # Custom React hooks
│   └── useDebounce.ts     # Debounce for search input
├── providers/             # React providers
│   └── react-query.tsx    # React Query setup
└── styles/
    └── globals.css        # Global styles + theme
```

## Pages

### Landing Page (`/`)
- Hero section with CTA buttons
- Feature cards with bento grid layout
- Gradient CTA section

### Authentication
- `/login` - Clean login form
- `/register` - Registration form with validation

### Dashboard (`/dashboard`)
- Stats cards with metrics
- Recent chats list
- Quick actions cards
- Pro tip banner

### Chats
- `/chats` - Grid of all chats with tags
- `/chats/[id]` - Individual chat interface with message bubbles

## API Integration

The frontend connects to the FastAPI backend at `http://localhost:8000`

Configure the API URL in `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### API Client Usage

```typescript
import { authApi, chatsApi, messagesApi } from '@/lib/api'

// Login
const { access_token } = await authApi.login(email, password)
localStorage.setItem('access_token', access_token)

// Fetch chats
const chats = await chatsApi.list()

// Semantic search (Qdrant vector search)
const results = await chatsApi.search('machine learning', page, pageSize)
// Returns: { data: SearchResult[], pagination: {...} }

// Send message
const message = await messagesApi.send(chatId, content)
```

### React Query Hooks

```typescript
import { useQuery, useMutation } from '@tanstack/react-query'
import { chatsApi } from '@/lib/api'

// Fetch chats
const { data: chats } = useQuery({
  queryKey: ['chats'],
  queryFn: chatsApi.list
})

// Create chat
const createChat = useMutation({
  mutationFn: (title: string) => chatsApi.create(title)
})
```

## Components

### shadcn/ui Components

All components follow the shadcn/ui philosophy:
- **Copy-paste friendly**: Components are in your codebase
- **Customizable**: Full control over styling
- **Accessible**: Built on Radix UI primitives

Available components:
- `Button` - Multiple variants (default, outline, ghost)
- `Card` - Container with header, content, footer
- `Badge` - Pill-shaped tags
- `Command` - Command palette with search

### Custom Components

- `Navbar` - Sticky navigation with scroll effects
- `CommandPalette` - Keyboard-driven semantic search (Cmd+K)
  - Real-time chat search with Qdrant
  - Debounced input (400ms)
  - Shows similarity scores and timestamps
  - User-scoped results (security)

## Styling

### Tailwind Utilities

Use Tailwind classes exclusively - no arbitrary values:

```tsx
// Good ✅
<div className="rounded-xl border border-slate-200 bg-white p-6">

// Bad ❌
<div className="rounded-[12px] border-[#e2e8f0]">
```

### Theme Colors

- **Background**: `bg-white`, `bg-slate-50`
- **Text**: `text-slate-900`, `text-slate-500`
- **Borders**: `border-slate-200`
- **Accent**: `bg-indigo-600`, `text-indigo-600`

### cn() Utility

Merge Tailwind classes safely:

```tsx
import { cn } from '@/lib/utils'

<div className={cn(
  "base classes",
  condition && "conditional classes",
  className
)} />
```

## Keyboard Shortcuts

- **Cmd/Ctrl + K**: Open command palette with semantic search
- **Enter**: Send message in chat (or select search result)
- **Shift + Enter**: New line in chat input
- **Escape**: Close command palette

## Development

### Adding New Pages

1. Create file in `app/` directory
2. Export default React component
3. Use layout components (Navbar is automatic)

### Adding New Components

1. Create in `components/` or `components/ui/`
2. Use TypeScript for type safety
3. Follow shadcn/ui patterns

### Environment Variables

- `NEXT_PUBLIC_API_URL` - Backend API URL

## Build & Deploy

```bash
# Production build
yarn build

# Analyze bundle
ANALYZE=true yarn build

# Run production server
yarn start
```

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

---

Built with ❤️ using Next.js, Tailwind CSS, and shadcn/ui
