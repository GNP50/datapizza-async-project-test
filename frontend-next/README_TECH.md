# Frontend - Next.js

## Descrizione
Interfaccia web per chatbot AI con upload documenti e visualizzazione fact-checking.

## Stack Tecnologico
- **Next.js 15** - Framework React con App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling utility-first
- **shadcn/ui** - Componenti accessibili
- **TanStack Query** - State management server
- **Axios** - Client HTTP

## Struttura
```
app/                        # Next.js App Router
├── layout.tsx             # Layout root
├── page.tsx               # Landing page
├── auth/                  # Login/Register
├── dashboard/             # Dashboard utente
└── chats/                 # Chat interface
    ├── page.tsx           # Lista chat
    └── [id]/page.tsx      # Chat singola

components/
├── ui/                    # shadcn/ui components
├── chat/                  # Componenti chat
│   ├── chat-window.tsx
│   ├── message-bubble.tsx
│   └── file-upload.tsx
└── layout/                # Navbar, Footer

lib/
├── api.ts                 # Client API + types
├── utils.ts               # Utilities (cn, ecc)
└── validators.ts          # Form validation

contexts/
└── auth-context.tsx       # Auth state globale
```

## Installazione
```bash
yarn install
```

## Esecuzione
```bash
# Development
yarn dev

# Build production
yarn build

# Start production
yarn start
```

## Configurazione
`.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Funzionalità Implementate

### Autenticazione
- Login/Registro con JWT
- Refresh token automatico
- Protected routes

### Chat
- Lista chat con paginazione
- Creazione chat
- Invio messaggi con allegati PDF
- Polling stato processamento
- Visualizzazione risposta AI

### Upload Documenti
- Drag & drop
- Validazione PDF
- Progress bar
- Preview file

### Fact-Checking
- Lista claim estratti
- Badge status (verified/disputed/unknown)
- Modal con sorgenti verificazione

## API Client
```typescript
import { authApi, chatsApi, messagesApi } from '@/lib/api'

// Login
await authApi.login(email, password)

// Lista chat
const chats = await chatsApi.list()

// Invia messaggio
await messagesApi.send(chatId, content, files)
```

## Docker
```bash
docker build -f Dockerfile -t frontend:latest .
docker run -p 3000:3000 frontend:latest
```

## Testing

### Note Testing
Per questo MVP, il testing frontend non è stato implementato con framework di testing automatizzati (Jest/Vitest).

**Testing Approach utilizzato**:
- ✅ **Manual testing** tramite interfaccia UI durante sviluppo
- ✅ **API testing** tramite Postman collection (vedi `../postman_collection.json`)
- ✅ **Browser testing** su Chrome/Firefox/Safari per compatibilità

**Testing Setup** (disponibile ma non utilizzato per MVP):
```bash
# Il comando test è configurato in package.json ma non ci sono test
yarn test        # Al momento: nessun test implementato
```

**Rationale**:
Per un MVP, il focus è stato sulla implementazione features core e testing manuale end-to-end risulta più efficiente rispetto a setup completo di unit/integration tests. Per produzione, si raccomanda:
- Unit tests per componenti critici (ChatWindow, MessageBubble)
- Integration tests per auth flow
- E2E tests con Playwright/Cypress

### Manual Testing Checklist
- ✅ Registration flow completo
- ✅ Login/Logout funzionante
- ✅ Token refresh automatico
- ✅ Chat creation e listing
- ✅ Message sending con/senza PDF
- ✅ File upload drag & drop
- ✅ Fact-checking panel expansion
- ✅ Responsive layout mobile
- ✅ Error handling e feedback utente
