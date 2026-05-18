/** Matches backend REXUS_ENV (injected via vite.config from root .env). */
export const isLocalDevelopment =
  (import.meta.env.VITE_REXUS_ENV ?? 'development').toLowerCase() === 'development';
