// Identity-provider library templates — shared between the admin "Add provider"
// modal and the settings page that consumes a picked template. Kept in a plain
// module (not inside an SFC <script setup>, which cannot have named exports).

export interface IdpTemplate {
  key: string
  name: string
  type: string
  logo: string
  issuerPattern: string
  scopes: string[]
  groupClaim: string
}

export const IDP_TEMPLATES: IdpTemplate[] = [
  { key: 'okta', name: 'Okta', type: 'OIDC', logo: 'okta', issuerPattern: 'https://{your-domain}.okta.com', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'auth0', name: 'Auth0', type: 'OIDC', logo: 'auth0', issuerPattern: 'https://{your-tenant}.auth0.com', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'keycloak', name: 'Keycloak', type: 'OIDC', logo: 'keycloak', issuerPattern: 'https://{host}/realms/{realm}', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'onelogin', name: 'OneLogin', type: 'OIDC', logo: 'onelogin', issuerPattern: 'https://{subdomain}.onelogin.com/oidc/2', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'ping', name: 'Ping Identity', type: 'OIDC', logo: 'ping', issuerPattern: 'https://auth.pingone.com/{envId}/as', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'jumpcloud', name: 'JumpCloud', type: 'OIDC', logo: 'jumpcloud', issuerPattern: 'https://oauth.id.jumpcloud.com', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'adfs', name: 'MS AD FS', type: 'OIDC', logo: 'adfs', issuerPattern: 'https://{adfs-host}/adfs', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
  { key: 'oidc', name: 'Generic OIDC', type: 'OIDC', logo: 'oidc', issuerPattern: '', scopes: ['openid', 'profile', 'email'], groupClaim: 'groups' },
]
