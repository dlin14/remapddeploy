/**
 * Single source of truth for the backend API base URL.
 *
 * In development:  set NEXT_PUBLIC_API_URL in frontend/.env.local (defaults to localhost:8000)
 * In production:   set NEXT_PUBLIC_API_URL in your Vercel project environment variables
 *                  to point at your deployed backend (e.g. https://remapd-api.railway.app)
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
