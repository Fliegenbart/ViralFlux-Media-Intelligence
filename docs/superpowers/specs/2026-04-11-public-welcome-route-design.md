# Public Welcome Route Design

**Goal:** Make `/welcome` publicly accessible without opening the protected working areas, so buyers and new users can see the product before logging in.

**Why this matters:** Right now the app shows the login screen before the router is even mounted. That means the product story exists in the code, but visitors never actually reach it. For demos and buyer conversations, this feels unfinished.

## Current Problem

- In [App.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/App.tsx), unauthenticated users are short-circuited directly to [LoginPage.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/pages/LoginPage.tsx).
- The router and the `/welcome` route are only mounted after authentication.
- Result: `/welcome` exists, but cannot be reached by a logged-out visitor.

## Recommended Approach

Use one shared router with two route groups:

1. **Public routes**
- `/welcome`
- `/login`

2. **Protected routes**
- `/virus-radar`
- `/jetzt`
- `/zeitgraph`
- `/regionen`
- `/kampagnen`
- `/evidenz`
- existing legacy redirects that should still land inside the protected app

This is the cleanest option because it keeps one routing tree, keeps the working app protected, and avoids a fragile special-case hack around `/welcome`.

## Routing Behavior

### Logged-out visitor

- `/` should redirect to `/welcome`
- `/welcome` should render normally
- `/login` should render normally
- any protected route should redirect to `/login`

### Logged-in user

- `/` should redirect to `/virus-radar`
- `/welcome` can stay accessible
- `/login` should redirect into the app, ideally to `/virus-radar`
- protected routes should render normally

## Component Shape

### App shell

In [App.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/App.tsx):

- keep the existing `authReady` loading gate
- remove the early `if (!authenticated) return <LoginPage ... />` shortcut
- always mount the router once auth state is known
- add a tiny protected-route wrapper that checks auth and redirects to `/login`

### Public welcome behavior

In [LandingPage.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/pages/landing/LandingPage.tsx):

- the main CTA should no longer assume access to the work area
- when logged in, it can still open `/jetzt`
- when logged out, it should send users to `/login`

This keeps the welcome page honest: it is public, but it does not secretly open protected workflow pages.

### Login behavior

In [LoginPage.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/pages/LoginPage.tsx):

- keep the current form and wording
- after a successful login, preserve the current simple behavior and enter the working area
- optionally accept redirect state from the router, so someone who tried to open `/kampagnen` can be sent there after login

If redirect-state support makes the change noticeably bigger, we can keep the first version simple and always send users into the main app after login.

## Testing

We should update [App.test.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/App.test.tsx) to cover:

- logged-out `/` goes to `/welcome`
- logged-out `/welcome` renders the landing page
- logged-out `/virus-radar` redirects to `/login`
- logged-in `/` goes to `/virus-radar`
- logged-in `/virus-radar` still stays on `/virus-radar`

We should also update [LandingPage.test.tsx](/Users/davidwegener/Desktop/viralflux/.worktrees/public-welcome-route/frontend/src/pages/landing/LandingPage.test.tsx) if needed so the CTA behavior matches the new public flow.

## Boundaries

- Do not redesign the landing page visually in this task.
- Do not rebuild auth.
- Do not make the work areas public.
- Do not change backend auth or session behavior.

## Success Criteria

- A logged-out user can open `/welcome`
- A logged-out user cannot open the protected working pages
- The app still behaves exactly like before once the user is logged in
- Routing is cleaner than the current pre-router login gate
