# Public Welcome Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/welcome` and `/login` reachable before login while keeping all working pages behind the existing auth gate.

**Architecture:** Keep the current `authReady` loading check, but remove the early "show login before router exists" shortcut. Mount one shared router after auth rehydration, split it into public routes (`/welcome`, `/login`) and protected routes (working pages plus legacy aliases), and let the welcome CTA decide between `/login` and `/jetzt` based on auth state.

**Tech Stack:** React 18, React Router, Jest, React Testing Library, TypeScript

---

## File Map

- `frontend/src/App.tsx`
  Responsible for auth rehydration, top-level routing, theme/toast providers, and route guards.
- `frontend/src/App.test.tsx`
  Responsible for route-level behavior tests with mocked auth and mocked lazy pages.
- `frontend/src/pages/landing/LandingPage.tsx`
  Responsible for the public welcome experience and the main CTA into the product.
- `frontend/src/pages/landing/LandingPage.test.tsx`
  Responsible for welcome-page copy and CTA behavior with mocked auth state.

### Task 1: Shared Router With Public And Protected Routes

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing route tests for logged-out visitors**

Add a landing-page mock near the other route mocks in `frontend/src/App.test.tsx`:

```tsx
jest.mock('./pages/LandingPage', () => ({
  __esModule: true,
  default: () => <div>Landing Mock</div>,
}));
```

Add these tests inside `describe('App routing', ...)`:

```tsx
it('redirects logged-out root visitors to /welcome', async () => {
  mockRehydrateAuth.mockResolvedValue(false);

  render(<App />);

  expect(await screen.findByText('Landing Mock')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/welcome');
});

it('renders the public welcome page for logged-out visitors', async () => {
  mockRehydrateAuth.mockResolvedValue(false);
  window.history.pushState({}, '', '/welcome');

  render(<App />);

  expect(await screen.findByText('Landing Mock')).toBeInTheDocument();
  expect(screen.queryByText('Login Mock')).not.toBeInTheDocument();
});

it('redirects logged-out protected routes to /login', async () => {
  mockRehydrateAuth.mockResolvedValue(false);
  window.history.pushState({}, '', '/virus-radar');

  render(<App />);

  expect(await screen.findByText('Login Mock')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/login');
});
```

- [ ] **Step 2: Run the route tests to verify the new expectations fail**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand App.test.tsx
```

Expected:
- `redirects logged-out root visitors to /welcome` fails because the app still renders `Login Mock`
- `renders the public welcome page for logged-out visitors` fails because `/welcome` is never mounted for logged-out users
- `redirects logged-out protected routes to /login` may partially pass visually, but the path stays wrong because the router never handled it

- [ ] **Step 3: Implement the shared router and route guards**

In `frontend/src/App.tsx`, add small route helpers above `const App: React.FC = () => {`:

```tsx
const RootRedirect: React.FC<{ authenticated: boolean }> = ({ authenticated }) => (
  <Navigate to={authenticated ? '/virus-radar' : '/welcome'} replace />
);

const LoginRoute: React.FC<{ authenticated: boolean; onLogin: () => void }> = ({
  authenticated,
  onLogin,
}) => (
  authenticated ? <Navigate to="/virus-radar" replace /> : <LoginPage onLogin={onLogin} />
);

const ProtectedRoute: React.FC<{
  authenticated: boolean;
  children: React.ReactElement;
}> = ({ authenticated, children }) => (
  authenticated ? children : <Navigate to="/login" replace />
);
```

Then replace the early unauthenticated return:

```tsx
if (!authenticated) {
  return (
    <ThemeProvider>
      <LoginPage onLogin={handleLogin} />
    </ThemeProvider>
  );
}
```

with a single router tree that always mounts after `authReady`:

```tsx
<Router>
  <Suspense fallback={<PageFallback />}>
    <Routes>
      <Route path="/" element={<RootRedirect authenticated={authenticated} />} />
      <Route path="/welcome" element={<LandingPage />} />
      <Route
        path="/login"
        element={<LoginRoute authenticated={authenticated} onLogin={handleLogin} />}
      />

      <Route
        element={(
          <ProtectedRoute authenticated={authenticated}>
            <MediaShell />
          </ProtectedRoute>
        )}
      >
        <Route path="/virus-radar" element={<VirusRadarPage />} />
        <Route path="/jetzt" element={<NowPage />} />
        <Route path="/zeitgraph" element={<TimegraphPage />} />
        <Route path="/regionen" element={<RegionsPage />} />
        <Route path="/kampagnen" element={<CampaignsPage />} />
        <Route path="/kampagnen/:id" element={<CampaignsPage />} />
        <Route path="/evidenz" element={<EvidencePage />} />
      </Route>
```

Keep the existing providers exactly as they are. Do not change auth logic, only where the router mounts and how it guards routes.

- [ ] **Step 4: Protect the legacy aliases with the same guard**

Still in `frontend/src/App.tsx`, wrap legacy redirects so logged-out visitors land on `/login` instead of hopping through protected URLs first:

```tsx
<Route
  path="/dashboard"
  element={(
    <ProtectedRoute authenticated={authenticated}>
      <Navigate to="/virus-radar" replace />
    </ProtectedRoute>
  )}
/>
<Route
  path="/entscheidung"
  element={(
    <ProtectedRoute authenticated={authenticated}>
      <Navigate to="/virus-radar" replace />
    </ProtectedRoute>
  )}
/>
<Route
  path="/empfehlungen/:id"
  element={(
    <ProtectedRoute authenticated={authenticated}>
      <LegacyRecommendationRedirect />
    </ProtectedRoute>
  )}
/>
```

Apply the same pattern to `/lagebild`, `/pilot`, `/bericht`, `/empfehlungen`, `/validierung`, `/dashboard/recommendations/:id`, and `/backtest`.

- [ ] **Step 5: Run the route tests to verify the shared router works**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand App.test.tsx
```

Expected:
- PASS for the three new logged-out tests
- existing authenticated route tests still PASS

- [ ] **Step 6: Commit the router change**

Run:

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: expose welcome route before login"
```

### Task 2: Logged-In Login Redirect And Legacy Alias Coverage

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing tests for `/login` and legacy aliases**

Add these tests to `frontend/src/App.test.tsx`:

```tsx
it('redirects authenticated visitors away from /login to /virus-radar', async () => {
  mockRehydrateAuth.mockResolvedValue(true);
  window.history.pushState({}, '', '/login');

  render(<App />);

  expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/virus-radar');
});

it('redirects logged-out legacy aliases to /login', async () => {
  mockRehydrateAuth.mockResolvedValue(false);
  window.history.pushState({}, '', '/dashboard');

  render(<App />);

  expect(await screen.findByText('Login Mock')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/login');
});
```

- [ ] **Step 2: Run the route tests to verify the new cases fail**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand App.test.tsx
```

Expected:
- `/login` for authenticated users fails because there is no dedicated login route yet
- `/dashboard` for logged-out users may bounce through `/virus-radar` instead of going directly to `/login`

- [ ] **Step 3: Finish the `LoginRoute` and legacy guard behavior in `App.tsx`**

Make sure the route tree from Task 1 contains this exact login route:

```tsx
<Route
  path="/login"
  element={<LoginRoute authenticated={authenticated} onLogin={handleLogin} />}
/>
```

and keep the `LoginRoute` helper as:

```tsx
const LoginRoute: React.FC<{ authenticated: boolean; onLogin: () => void }> = ({
  authenticated,
  onLogin,
}) => (
  authenticated ? <Navigate to="/virus-radar" replace /> : <LoginPage onLogin={onLogin} />
);
```

If any legacy alias is still defined as a plain `<Navigate ... />`, convert it to the guarded form from Task 1 so every alias follows the same rule.

- [ ] **Step 4: Run the route tests again**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand App.test.tsx
```

Expected:
- PASS for authenticated `/login`
- PASS for logged-out `/dashboard`
- the older authenticated alias tests still PASS

- [ ] **Step 5: Commit the route polish**

Run:

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "test: cover public and protected route redirects"
```

### Task 3: Welcome CTA Respects Auth State

**Files:**
- Modify: `frontend/src/pages/landing/LandingPage.tsx`
- Modify: `frontend/src/pages/landing/LandingPage.test.tsx`

- [ ] **Step 1: Write the failing CTA tests**

Replace the current `jest.mock('../../App', ...)` in `frontend/src/pages/landing/LandingPage.test.tsx` with a shared auth toggle:

```tsx
let mockAuthenticated = false;

jest.mock('../../App', () => ({
  useTheme: () => ({
    theme: 'light',
    toggle: jest.fn(),
  }),
  useAuth: () => ({
    authenticated: mockAuthenticated,
    handleLogin: jest.fn(),
    handleLogout: jest.fn(),
  }),
}));
```

Add a location probe and two CTA tests:

```tsx
import { MemoryRouter, useLocation } from 'react-router-dom';

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname}</div>;
};

it('sends logged-out visitors from the hero CTA to /login', async () => {
  mockAuthenticated = false;

  render(
    <MemoryRouter initialEntries={['/welcome']}>
      <LandingPage />
      <LocationProbe />
    </MemoryRouter>,
  );

  await resolveLandingFetch();
  fireEvent.click(
    within(screen.getByRole('region', { name: 'Wochenbriefing Einstieg' })).getByRole('button', {
      name: 'Wochenplan öffnen',
    }),
  );

  expect(screen.getByTestId('location-probe')).toHaveTextContent('/login');
});

it('keeps the hero CTA inside the work area for logged-in users', async () => {
  mockAuthenticated = true;

  render(
    <MemoryRouter initialEntries={['/welcome']}>
      <LandingPage />
      <LocationProbe />
    </MemoryRouter>,
  );

  await resolveLandingFetch();
  fireEvent.click(
    within(screen.getByRole('region', { name: 'Wochenbriefing Einstieg' })).getByRole('button', {
      name: 'Wochenplan öffnen',
    }),
  );

  expect(screen.getByTestId('location-probe')).toHaveTextContent('/jetzt');
});
```

Also update the import line at the top:

```tsx
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
```

- [ ] **Step 2: Run the landing tests to verify the logged-out CTA fails**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand landing/LandingPage.test.tsx
```

Expected:
- logged-out CTA test fails because the button still navigates to `/jetzt`
- logged-in CTA test may pass already, which is fine

- [ ] **Step 3: Implement the auth-aware CTA**

In `frontend/src/pages/landing/LandingPage.tsx`, import `useAuth` alongside `useTheme`:

```tsx
import { useAuth, useTheme } from '../../App';
```

Inside the component, read the auth state and update the CTA helper:

```tsx
const { authenticated } = useAuth();

const openCockpit = () => navigate(authenticated ? '/jetzt' : '/login');
```

Do not change the rest of the landing page copy or layout in this task.

- [ ] **Step 4: Run the landing tests again**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand landing/LandingPage.test.tsx
```

Expected:
- PASS for both CTA tests
- existing landing-copy assertions still PASS

- [ ] **Step 5: Run the focused frontend regression suite**

Run:

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test npm --prefix frontend test -- --runInBand App.test.tsx landing/LandingPage.test.tsx LoginPage.test.tsx
npm --prefix frontend run build
```

Expected:
- `App.test.tsx`, `landing/LandingPage.test.tsx`, and `LoginPage.test.tsx` all PASS
- the frontend build completes successfully

- [ ] **Step 6: Commit the landing CTA change**

Run:

```bash
git add frontend/src/pages/landing/LandingPage.tsx frontend/src/pages/landing/LandingPage.test.tsx
git commit -m "feat: route public welcome CTA through login"
```

## Self-Review

- Spec coverage: the plan covers public `/welcome`, public `/login`, protected working pages, logged-in `/login` redirect, and auth-aware CTA behavior. No spec requirement is left without a task.
- Placeholder scan: no `TODO`, `TBD`, or "implement later" placeholders remain.
- Type consistency: the plan uses one helper naming scheme throughout: `RootRedirect`, `LoginRoute`, `ProtectedRoute`, and `authenticated`.
