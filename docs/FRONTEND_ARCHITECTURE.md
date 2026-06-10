# Frontend Architecture

React SPA architecture designed for 100K users with enterprise SaaS UX patterns.

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | React 18 + TypeScript | Type safety, ecosystem |
| Build | Vite | Fast HMR, optimized builds |
| Styling | Tailwind CSS + ShadCN | Consistent design system |
| Server State | TanStack React Query | Caching, mutations, retry |
| Client State | Zustand | Minimal boilerplate, persist |
| Routing | React Router v7 | Standard SPA routing |
| Charts | Recharts | Analytics dashboards |
| HTTP | Axios | Interceptors for auth refresh |

## Application Structure

```
src/
├── main.tsx              # Entry point, QueryClient provider
├── App.tsx               # Router, auth guards
├── pages/                # Route-level components (lazy-loadable)
│   ├── Login.tsx         # Public
│   ├── Dashboard.tsx     # Protected
│   ├── Chat.tsx          # Protected, SSE streaming
│   ├── Documents.tsx     # Protected, file upload
│   ├── Workspaces.tsx    # Protected
│   ├── Users.tsx         # Protected, admin
│   ├── Analytics.tsx     # Protected, charts
│   └── Settings.tsx      # Protected
├── components/
│   ├── ui/               # ShadCN primitives (Button, Card, Input)
│   └── layout/           # Sidebar, AppLayout
├── stores/
│   ├── authStore.ts      # JWT tokens, user, persist
│   └── appStore.ts       # Current workspace, UI state
├── lib/
│   ├── api.ts            # Axios client, interceptors, API methods
│   └── utils.ts          # cn() helper, formatters
├── hooks/                # Custom hooks (future)
└── types/                # TypeScript interfaces
```

## Authentication Flow

```
Login Page
  → POST /auth/login
  → Store access + refresh tokens (Zustand persist → localStorage)
  → GET /auth/me (populate user)
  → Redirect to /dashboard

Every API request:
  → Axios interceptor adds Bearer token
  → On 401: attempt refresh with refresh_token
  → On refresh success: retry original request
  → On refresh failure: logout, redirect to /login
```

## Scaling Considerations (100K Users)

### Frontend Does Not Scale Like Backend

The frontend is a static SPA — scaling is about **delivery**, not **compute**:

| Concern | Solution |
|---------|----------|
| Asset delivery | CloudFront CDN, gzip/brotli |
| Bundle size | Code splitting per route (React.lazy) |
| API load | React Query caching reduces redundant calls |
| SSE connections | Not held by frontend — backend concern |
| Token refresh storms | Exponential backoff on 401, single refresh in flight |

### React Query Cache Strategy

| Query | Stale Time | Refetch |
|-------|-----------|---------|
| Workspaces list | 30s | On window focus |
| Documents list | 10s | Polling during processing |
| Conversations | 30s | On new message |
| Analytics | 5 min | Manual refresh |
| User profile | 5 min | On mount |

### Performance Targets

| Metric | Target |
|--------|--------|
| First Contentful Paint | < 1.5s |
| Time to Interactive | < 3s |
| Bundle size (gzipped) | < 500KB initial |
| Lighthouse score | > 90 |

### Code Splitting (Production)

```typescript
// Lazy load heavy pages
const Analytics = React.lazy(() => import("@/pages/Analytics"));
const Chat = React.lazy(() => import("@/pages/Chat"));

// Route-level Suspense boundaries
<Suspense fallback={<PageSkeleton />}>
  <Route path="/analytics" element={<Analytics />} />
</Suspense>
```

## Chat UX at Scale

### Streaming Architecture

```
User types message → POST /chat/stream (SSE)
  → Receive metadata event (conversation_id, citations)
  → Receive content events (token chunks)
  → Render incrementally in message bubble
  → Receive done event (message_id)
```

### Chat State Management

- Messages stored in component state during active session
- Conversation list fetched via React Query (server state)
- Switching conversations loads messages from API
- No local persistence of chat content (security: no PII in localStorage)

## Accessibility & Enterprise UX

- Keyboard navigation for chat input (Enter to send, Shift+Enter for newline)
- Loading states for all async operations
- Error boundaries per page (prevent full app crash)
- Responsive layout (sidebar collapses on mobile)
- Dark mode support via CSS variables (configured, toggle in Settings future)

## Deployment

```dockerfile
# Production build
npm run build  # → dist/ (static files)

# Served by:
# - Nginx in Docker (production Dockerfile)
# - CloudFront + S3 (AWS production)
# - Kubernetes deployment (2 replicas, stateless)
```

Production frontend is fully stateless — scale by adding CDN edge locations, not app replicas.
