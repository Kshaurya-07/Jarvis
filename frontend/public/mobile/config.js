/* Jarvis Companion configuration.
 *
 * apiBaseUrl: where the cloud backend lives.
 *   "" (default) = same origin as this page. On Vercel the frontend and the
 *   backend are the SAME project, so same-origin /api calls just work and
 *   there is nothing to configure.
 *   Set a full URL here (or in Settings > Cloud backend address) ONLY if
 *   the backend is deployed somewhere else — never hardcode a backend URL
 *   that does not exist yet.
 */
window.JARVIS_CONFIG = {
  apiBaseUrl: "",
};
