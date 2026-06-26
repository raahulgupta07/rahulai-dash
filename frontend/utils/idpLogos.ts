/**
 * IDP brand logo utilities.
 * Each logo is a self-contained inline SVG string (viewBox 0 0 18 18).
 * SVG paths are copied verbatim from the identity-provider-mockup.html <defs> block.
 */

export const IDP_PRESET_KEYS: string[] = [
  'google',
  'microsoft',
  'okta',
  'keycloak',
  'auth0',
  'onelogin',
  'ping',
  'jumpcloud',
  'adfs',
  'oidc',
  'saml',
  'ldap',
  'scim',
  'shield',
]

export const IDP_LOGOS: Record<string, string> = {
  google: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><path fill="#4285F4" d="M17.6 9.2c0-.6-.1-1.2-.2-1.8H9v3.5h4.8a4.1 4.1 0 0 1-1.8 2.7v2.3h2.9c1.7-1.6 2.7-3.9 2.7-6.7z"/><path fill="#34A853" d="M9 18c2.4 0 4.5-.8 6-2.2l-2.9-2.3c-.8.6-1.8.9-3.1.9-2.3 0-4.3-1.6-5-3.7H1v2.3A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M4 10.7a5.4 5.4 0 0 1 0-3.4V5H1a9 9 0 0 0 0 8.1l3-2.4z"/><path fill="#EA4335" d="M9 3.6c1.3 0 2.5.5 3.4 1.3L15 2.3A9 9 0 0 0 1 5l3 2.3C4.7 5.2 6.7 3.6 9 3.6z"/></svg>`,

  microsoft: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="7.6" height="7.6" fill="#F25022"/><rect x="9.4" y="1" width="7.6" height="7.6" fill="#7FBA00"/><rect x="1" y="9.4" width="7.6" height="7.6" fill="#00A4EF"/><rect x="9.4" y="9.4" width="7.6" height="7.6" fill="#FFB900"/></svg>`,

  okta: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="8" fill="none" stroke="#007DC1" stroke-width="3.4"/></svg>`,

  keycloak: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><circle cx="7.2" cy="9" r="5.2" fill="none" stroke="#008AAA" stroke-width="2"/><path d="M11.5 9H17M14.4 6.2V11.8M16.8 6.6V11.4" stroke="#33648C" stroke-width="2" stroke-linecap="round"/></svg>`,

  auth0: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><path d="M9 1l2.5 6.6H17l-4.4 3.6 1.7 6.2L9 13.8 3.7 17.4l1.7-6.2L1 7.6h5.5z" fill="#EB5424"/></svg>`,

  onelogin: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="2" width="14" height="14" rx="3" fill="#1C1F2A"/><path d="M9 5.5v7" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>`,

  ping: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.2" fill="none" stroke="#B81B1C" stroke-width="2"/><path d="M9 4.5v9" stroke="#B81B1C" stroke-width="2" stroke-linecap="round"/></svg>`,

  jumpcloud: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7" fill="#179DD9"/><path d="M6 9.5l2 2 4-4.5" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,

  adfs: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><path d="M9 1.5l6.5 3v5c0 4-2.8 6.5-6.5 8C5.3 15 2.5 12.5 2.5 8.5v-5L9 1.5z" fill="none" stroke="#0078D4" stroke-width="1.6" stroke-linejoin="round"/><path d="M6.4 9l1.8 1.8L11.8 7" stroke="#0078D4" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,

  oidc: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.2" fill="none" stroke="#999" stroke-width="1.6"/><text x="9" y="12.4" text-anchor="middle" font-size="7" font-family="monospace" fill="#666">{}</text></svg>`,

  saml: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="3" width="14" height="12" rx="2" fill="none" stroke="#5C6BC0" stroke-width="1.6"/><path d="M5 7h8M5 10h5" stroke="#5C6BC0" stroke-width="1.6" stroke-linecap="round"/></svg>`,

  ldap: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><ellipse cx="9" cy="4.5" rx="6" ry="2.4" fill="none" stroke="#3A7" stroke-width="1.6"/><path d="M3 4.5v9c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4v-9M3 9c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4" fill="none" stroke="#3A7" stroke-width="1.6" stroke-linecap="round"/></svg>`,

  scim: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><path d="M4 6h7l-2-2M14 12H7l2 2" stroke="#7A57D1" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,

  shield: `<svg viewBox="0 0 18 18" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><path d="M9 1.5l6.5 3v5c0 4-2.8 6.5-6.5 8C5.3 15 2.5 12.5 2.5 8.5v-5L9 1.5z" fill="none" stroke="#C2541E" stroke-width="1.6" stroke-linejoin="round"/></svg>`,
}

/**
 * Returns an HTML string suitable for v-html rendering.
 * - Known preset key  → inline SVG
 * - data:image/ URL   → <img> tag
 * - anything else     → oidc fallback SVG
 */
export function idpLogoSvg(logo: string): string {
  if (logo && IDP_LOGOS[logo]) {
    return IDP_LOGOS[logo]
  }
  if (logo && logo.startsWith('data:image/')) {
    return `<img src="${logo}" style="width:100%;height:100%;object-fit:contain;display:block;" alt="custom logo" />`
  }
  return IDP_LOGOS['oidc']
}
