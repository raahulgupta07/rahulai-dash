<template>
  <div class="mt-4 space-y-8">

    <!-- ================================================================== -->
    <!-- SSO Section                                                         -->
    <!-- ================================================================== -->
    <div>
      <div class="mb-4">
        <h2 class="text-sm font-medium text-[#1f2328]">Single Sign-On</h2>
        <p class="text-xs text-[#6b6b6b] mt-0.5">Let members sign in with Google, Microsoft, or any OIDC provider.</p>
      </div>

      <div class="border border-[#E9E0D3] rounded-2xl overflow-hidden bg-white">

        <!-- Provider rows: Google · Microsoft · Okta · Keycloak · custom OIDC -->
        <div
          v-for="row in ssoRows"
          :key="row.id"
          class="flex items-center gap-3 px-5 py-3.5 border-b border-[#E9E0D3]"
        >
          <span class="w-7 h-7 rounded-md border border-[#E9E0D3] bg-white flex items-center justify-center flex-shrink-0 p-1 [&_svg]:w-full [&_svg]:h-full [&_img]:w-full [&_img]:h-full" v-html="idpLogoSvg(row.logo)"></span>
          <span class="text-sm font-medium text-[#1f2328] flex-1 truncate">{{ row.name }}</span>
          <span class="text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap" :class="pillClass(row.enabled, row.configured)">{{ pillText(row.enabled, row.configured) }}</span>
          <button
            type="button"
            class="px-3 py-2 text-xs rounded-lg transition-colors cursor-pointer whitespace-nowrap"
            :class="(row.enabled && !row.configured) ? 'border border-[#e7c79a] text-[#9A5A12] bg-[#FBEEDD] hover:bg-[#f6e3c8]' : 'border border-[#E9E0D3] text-[#1f2328] bg-white hover:bg-[#F4EEE5]'"
            @click="row.configure()"
          >{{ (row.enabled && !row.configured) ? 'Set up →' : 'Configure' }}</button>
          <button
            type="button"
            class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
            :class="row.enabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
            :title="row.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'"
            @click="row.toggle()"
          >
            <span class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all" :class="row.enabled ? 'left-[18px]' : 'left-0.5'"></span>
          </button>
          <button
            v-if="row.removable"
            type="button"
            class="text-xs text-red-400 hover:text-red-600 px-1"
            title="Remove provider"
            @click="row.remove && row.remove()"
          >&#x2715;</button>
        </div>

        <!-- Add provider (opens the provider library) -->
        <div class="px-5 py-3.5 border-b border-[#E9E0D3]">
          <button
            type="button"
            class="flex items-center gap-2 text-xs text-[#C2541E] font-medium border border-dashed border-[#E9E0D3] rounded-xl px-4 py-2.5 hover:border-[#C2541E] hover:bg-[#FBEFE4] transition-colors"
            @click="showLibrary = true"
          >
            <span>+</span>
            <span>Add provider</span>
            <span class="text-[#9a958c] font-normal">· Okta · Auth0 · Keycloak · OneLogin · Ping · Generic OIDC …</span>
          </button>
        </div>

        <!-- Auth mode -->
        <div class="px-5 py-3.5 border-b border-[#E9E0D3]">
          <div class="flex items-center gap-6 flex-wrap">
            <span class="text-xs text-[#6b6b6b] w-20 flex-shrink-0">Auth mode</span>
            <label
              v-for="opt in authModeOptions"
              :key="opt.value"
              class="flex items-center gap-2 cursor-pointer text-xs text-[#6b6b6b]"
            >
              <span
                class="w-3.5 h-3.5 rounded-full border flex-shrink-0 relative"
                :class="ssoAuthMode === opt.value ? 'border-[#C2541E]' : 'border-[#E9E0D3]'"
              >
                <span
                  v-if="ssoAuthMode === opt.value"
                  class="absolute inset-[3px] rounded-full bg-[#C2541E]"
                ></span>
              </span>
              <input
                type="radio"
                :value="opt.value"
                v-model="ssoAuthMode"
                class="sr-only"
                @change="handleAuthModeChange(opt.value)"
              />
              {{ opt.label }}
            </label>
          </div>
        </div>

        <!-- Allow public sign-up toggle (Task 3) -->
        <div class="px-5 py-3.5">
          <div class="flex items-center gap-4">
            <span class="text-xs text-[#6b6b6b] flex-1">Allow public sign-up</span>
            <span class="text-[11px] text-[#9a958c]">Let anyone register without an invite</span>
            <label class="flex items-center gap-2 cursor-pointer">
              <button
                type="button"
                class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
                :class="signupEnabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
                @click="handleSignupToggle"
              >
                <span
                  class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all"
                  :class="signupEnabled ? 'left-[18px]' : 'left-0.5'"
                ></span>
              </button>
              <span class="text-xs text-[#6b6b6b]">{{ signupEnabled ? 'On' : 'Off' }}</span>
            </label>
          </div>
        </div>

      </div>
    </div>

    <!-- ================================================================== -->
    <!-- SCIM Provisioning Section                                           -->
    <!-- ================================================================== -->
    <div>
      <div class="mb-4">
        <h2 class="text-sm font-medium text-[#1f2328]">{{ $t('settings.identityProvider.scimTitle') }}</h2>
        <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('settings.identityProvider.scimSubtitle') }}</p>
      </div>

      <!-- Enterprise Gate for SCIM -->
      <template v-if="!hasFeature('scim')">
        <div class="rounded-lg border border-[#E9E0D3] p-4 bg-[#F4EEE5]">
          <p class="text-xs text-[#6b6b6b] mb-2">
            {{ $t('settings.identityProvider.enterpriseScim') }}
          </p>
          <a
            href="https://docs.bagofwords.com/enterprise"
            target="_blank"
            rel="noopener noreferrer"
            class="text-xs text-[#C2541E] hover:text-[#A8330F]"
          >
            {{ $t('settings.identityProvider.learnMore') }}
          </a>
        </div>
      </template>

      <template v-else>
        <!-- SCIM row -->
        <div class="border border-[#E9E0D3] rounded-2xl overflow-hidden bg-white">
          <div class="flex items-center gap-3 px-5 py-3.5">
            <span class="w-7 h-7 rounded-md border border-[#E9E0D3] bg-white flex items-center justify-center flex-shrink-0 p-1 [&_svg]:w-full [&_svg]:h-full" v-html="idpLogoSvg('scim')"></span>
            <span class="text-sm font-medium text-[#1f2328] flex-1">SCIM Provisioning</span>
            <span
              class="text-[11px] font-medium px-2 py-0.5 rounded-full"
              :class="tokens.length > 0 ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-[#F4EEE5] text-[#6b6b6b] border border-[#E9E0D3]'"
            >{{ tokens.length > 0 ? 'Active' : 'Not configured' }}</span>
            <button
              type="button"
              class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer"
              @click="openModal('scim')"
            >Configure</button>
          </div>
        </div>
      </template>
    </div>

    <!-- ================================================================== -->
    <!-- LDAP Directory Sync Section                                         -->
    <!-- ================================================================== -->
    <div>
      <div class="mb-4">
        <h2 class="text-sm font-medium text-[#1f2328]">{{ $t('settings.identityProvider.ldapTitle') }}</h2>
        <p class="text-xs text-[#6b6b6b] mt-0.5">{{ $t('settings.identityProvider.ldapSubtitle') }}</p>
      </div>

      <!-- Enterprise Gate for LDAP -->
      <template v-if="!hasFeature('ldap')">
        <div class="rounded-lg border border-[#E9E0D3] p-4 bg-[#F4EEE5]">
          <p class="text-xs text-[#6b6b6b] mb-2">
            {{ $t('settings.identityProvider.enterpriseLdap') }}
          </p>
          <a
            href="https://docs.bagofwords.com/enterprise"
            target="_blank"
            rel="noopener noreferrer"
            class="text-xs text-[#C2541E] hover:text-[#A8330F]"
          >
            {{ $t('settings.identityProvider.learnMore') }}
          </a>
        </div>
      </template>

      <template v-else>
        <div class="border border-[#E9E0D3] rounded-2xl overflow-hidden bg-white">
          <!-- LDAP row -->
          <div class="flex items-center gap-3 px-5 py-3.5" :class="ldapStatus?.ldap_configured ? 'border-b border-[#E9E0D3]' : ''">
            <span class="w-7 h-7 rounded-md border border-[#E9E0D3] bg-white flex items-center justify-center flex-shrink-0 p-1 [&_svg]:w-full [&_svg]:h-full [&_img]:w-full [&_img]:h-full" v-html="idpLogoSvg(ldapForm.logo || 'ldap')"></span>
            <span class="text-sm font-medium text-[#1f2328] flex-1">LDAP Directory Sync</span>
            <span class="text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap" :class="pillClass(ldapForm.enabled, !!ldapStatus?.ldap_configured)">{{ pillText(ldapForm.enabled, !!ldapStatus?.ldap_configured) }}</span>
            <button
              type="button"
              class="px-3 py-2 text-xs rounded-lg transition-colors cursor-pointer whitespace-nowrap"
              :class="(ldapForm.enabled && !ldapStatus?.ldap_configured) ? 'border border-[#e7c79a] text-[#9A5A12] bg-[#FBEEDD] hover:bg-[#f6e3c8]' : 'border border-[#E9E0D3] text-[#1f2328] bg-white hover:bg-[#F4EEE5]'"
              @click="openModal('ldap')"
            >{{ (ldapForm.enabled && !ldapStatus?.ldap_configured) ? 'Set up →' : 'Configure' }}</button>
            <button
              type="button"
              class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
              :class="ldapForm.enabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
              :title="ldapForm.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'"
              @click="quickToggleLdap()"
            >
              <span class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all" :class="ldapForm.enabled ? 'left-[18px]' : 'left-0.5'"></span>
            </button>
          </div>

          <!-- Configured status + sync actions (only when connected) -->
          <template v-if="ldapStatus?.ldap_configured">

            <!-- Connection status -->
            <div class="p-5 border-b border-[#E9E0D3]">
              <div class="flex items-center justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <div
                      class="w-2 h-2 rounded-full"
                      :class="ldapTestResult?.connected ? 'bg-green-500' : (ldapTestResult ? 'bg-red-500' : 'bg-[#E9E0D3]')"
                    ></div>
                    <span class="text-xs font-medium text-[#6b6b6b]">
                      {{ ldapTestResult?.connected ? $t('settings.identityProvider.statusConnected') : (ldapTestResult ? $t('settings.identityProvider.statusFailed') : $t('settings.identityProvider.statusNotTested')) }}
                    </span>
                  </div>
                  <p v-if="ldapTestResult?.connected" class="text-[11px] text-[#9a958c] mt-0.5 ms-4">
                    {{ ldapTestResult.server }}
                    <template v-if="ldapTestResult.vendor"> · {{ ldapTestResult.vendor }}</template>
                    <template v-if="ldapTestResult.user_count !== null"> · {{ ldapTestResult.user_count }} users</template>
                    <template v-if="ldapTestResult.group_count !== null"> · {{ ldapTestResult.group_count }} groups</template>
                  </p>
                  <p v-if="ldapTestResult && !ldapTestResult.connected" class="text-[11px] text-red-400 mt-0.5 ms-4">
                    {{ ldapTestResult.error }}
                  </p>
                </div>
                <button
                  class="px-3 py-2 text-xs text-[#1f2328] bg-white border border-[#E9E0D3] rounded-lg hover:bg-[#F4EEE5] transition-colors cursor-pointer"
                  :disabled="ldapLoading"
                  @click="handleTestConnection"
                >
                  {{ ldapLoading ? $t('settings.identityProvider.testing') : $t('settings.identityProvider.testConnection') }}
                </button>
              </div>
            </div>

            <!-- Last sync info -->
            <div v-if="ldapStatus?.last_sync" class="p-5 border-b border-[#E9E0D3]">
              <div class="flex items-center justify-between">
                <div>
                  <span class="text-xs font-medium text-[#6b6b6b]">{{ $t('settings.identityProvider.lastSync') }}</span>
                  <p class="text-[11px] text-[#9a958c] mt-0.5">
                    {{ ldapStatus.last_sync.timestamp ? formatRelativeTime(ldapStatus.last_sync.timestamp) : $t('settings.identityProvider.unknown') }}
                    {{ $t('settings.identityProvider.lastSyncDetail', {
                      gCreated: ldapStatus.last_sync.groups_created,
                      gUpdated: ldapStatus.last_sync.groups_updated,
                      gRemoved: ldapStatus.last_sync.groups_removed,
                      mAdded: ldapStatus.last_sync.memberships_added,
                      mRemoved: ldapStatus.last_sync.memberships_removed,
                    }) }}
                  </p>
                  <p v-if="ldapStatus.last_sync.errors.length" class="text-[11px] text-red-400 mt-0.5">
                    {{ $t('settings.identityProvider.errorCount', { n: ldapStatus.last_sync.errors.length, first: ldapStatus.last_sync.errors[0] }) }}
                  </p>
                </div>
              </div>
            </div>

            <!-- Sync actions -->
            <div class="p-5">
              <div class="flex items-center gap-2 flex-wrap">
                <button
                  class="px-3 py-2.5 text-xs text-white bg-[#C2541E] hover:bg-[#A8330F] rounded-xl transition-colors cursor-pointer disabled:opacity-65"
                  :disabled="ldapLoading"
                  @click="handleSync"
                >
                  {{ ldapLoading ? $t('settings.identityProvider.syncing') : $t('settings.identityProvider.syncNow') }}
                </button>
                <button
                  class="px-3 py-2 text-xs text-[#1f2328] bg-white border border-[#E9E0D3] rounded-lg hover:bg-[#F4EEE5] transition-colors cursor-pointer disabled:opacity-65"
                  :disabled="ldapLoading"
                  @click="handlePreview"
                >
                  {{ $t('settings.identityProvider.previewChanges') }}
                </button>
              </div>

              <!-- Sync result flash -->
              <div v-if="lastSyncResult" class="mt-3 rounded-lg border border-green-200 bg-green-50 p-3">
                <p class="text-xs text-green-700">
                  {{ $t('settings.identityProvider.syncCompletedSummary', {
                    gCreated: lastSyncResult.groups_created,
                    gUpdated: lastSyncResult.groups_updated,
                    gRemoved: lastSyncResult.groups_removed,
                    mAdded: lastSyncResult.memberships_added,
                    mRemoved: lastSyncResult.memberships_removed,
                  }) }}
                  <template v-if="lastSyncResult.users_not_found">
                    {{ $t('settings.identityProvider.ldapUsersNotFound', { n: lastSyncResult.users_not_found }) }}
                  </template>
                </p>
              </div>

              <!-- Preview results -->
              <div v-if="ldapPreview" class="mt-3">
                <div class="rounded-lg border border-[#E9E0D3] overflow-hidden">
                  <div class="bg-[#F4EEE5] px-3 py-2 border-b border-[#E9E0D3]">
                    <span class="text-xs font-medium text-[#6b6b6b]">{{ $t('settings.identityProvider.preview') }} </span>
                    <span class="text-xs text-[#6b6b6b]">
                      {{ $t('settings.identityProvider.previewSummary', {
                        create: ldapPreview.groups_to_create,
                        update: ldapPreview.groups_to_update,
                        remove: ldapPreview.groups_to_remove,
                        changes: ldapPreview.total_membership_changes,
                      }) }}
                    </span>
                  </div>
                  <div v-if="ldapPreview.groups.length" class="max-h-64 overflow-y-auto">
                    <div
                      v-for="(group, idx) in ldapPreview.groups"
                      :key="group.dn"
                      class="flex items-center px-3 py-2 text-xs"
                      :class="{ 'border-t border-[#E9E0D3]': idx > 0 }"
                    >
                      <span class="flex-1 text-[#6b6b6b] truncate" :title="group.dn">{{ group.name }}</span>
                      <span class="w-20 text-[#9a958c] text-[11px]">{{ $t('settings.identityProvider.memberCount', { n: group.member_count }) }}</span>
                      <span class="w-24 text-[11px]" :class="group.exists_in_app ? 'text-[#9a958c]' : 'text-[#C2541E]'">
                        {{ group.exists_in_app ? $t('settings.identityProvider.groupExists') : $t('settings.identityProvider.groupNew') }}
                      </span>
                      <span v-if="group.members_to_add" class="text-[11px] text-green-600 me-2">+{{ group.members_to_add }}</span>
                      <span v-if="group.members_to_remove" class="text-[11px] text-red-500">-{{ group.members_to_remove }}</span>
                    </div>
                  </div>
                  <div v-else class="py-4 text-center text-xs text-[#9a958c]">
                    {{ $t('settings.identityProvider.noLdapGroups') }}
                  </div>
                </div>
              </div>

              <!-- LDAP Error -->
              <div v-if="ldapError" class="mt-3 text-xs text-red-500">
                {{ ldapError }}
              </div>
            </div>

          </template>
        </div>
      </template>
    </div>

    <!-- ================================================================== -->
    <!-- PROVIDER CONFIG MODALS                                             -->
    <!-- ================================================================== -->

    <!-- Google Modal -->
    <SettingsProviderConfigModal :model-value="activeModal === 'google'" title="Configure Google SSO" @close="closeModal">
      <IdpLogoPicker v-model="ssoGoogle.logo" />
      <!-- Redirect URI -->
      <div class="mb-4 rounded-xl border border-[#E9E0D3] bg-[#faf8f3] px-3 py-2.5">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-[#6b6b6b]">Redirect URI</span>
          <button type="button" class="text-[11px] text-[#C2541E] hover:text-[#A8330F] font-medium" @click="copyToClipboard(googleRedirectUri, 'google-redirect')">
            {{ copied === 'google-redirect' ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <code class="text-[11px] font-mono text-[#6b6b6b] break-all">{{ googleRedirectUri }}</code>
        <p class="text-[11px] text-[#9a958c] mt-1">Paste this into the Google Cloud Console OAuth 2.0 authorized redirect URIs.</p>
      </div>

      <div class="flex items-center justify-between mb-4">
        <span class="text-xs font-semibold text-[#6b6b6b]">Enable Google SSO</span>
        <label class="flex items-center gap-2 cursor-pointer">
          <button
            type="button"
            class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
            :class="ssoGoogle.enabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
            @click="ssoGoogle.enabled = !ssoGoogle.enabled"
          >
            <span
              class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all"
              :class="ssoGoogle.enabled ? 'left-[18px]' : 'left-0.5'"
            ></span>
          </button>
          <span class="text-xs text-[#6b6b6b]">{{ ssoGoogle.enabled ? 'Enabled' : 'Disabled' }}</span>
        </label>
      </div>

      <div class="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2.5 items-center">
        <span class="text-xs text-[#6b6b6b]">Client ID</span>
        <input
          v-model="ssoGoogle.client_id"
          type="text"
          placeholder="1234-abc.apps.googleusercontent.com"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="text-xs text-[#6b6b6b]">Client secret</span>
        <input
          v-model="ssoGoogle.client_secret"
          type="password"
          :placeholder="ssoGoogle.client_secret_set ? 'configured' : 'paste secret…'"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="col-start-2 text-[11px] text-[#9a958c]">Encrypted at rest (Fernet). Write-only — never echoed back.</span>
      </div>

      <div v-if="ssoGoogleTestResult" class="mt-3 text-xs" :class="ssoGoogleTestResult.ok ? 'text-green-600' : 'text-red-500'">
        {{ ssoGoogleTestResult.text }}
      </div>

      <!-- Modal footer -->
      <div class="flex items-center gap-2 mt-5 pt-4 border-t border-[#E9E0D3]">
        <button
          type="button"
          class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer disabled:opacity-65"
          :disabled="ssoGoogleTesting"
          @click="handleTestGoogle"
        >{{ ssoGoogleTesting ? 'Testing…' : 'Test' }}</button>
        <button
          type="button"
          class="px-4 py-2.5 text-xs bg-[#C2541E] hover:bg-[#A8330F] text-white rounded-xl font-semibold transition-colors cursor-pointer disabled:opacity-65"
          :disabled="ssoGoogleSaving"
          @click="handleSaveGoogleAndClose"
        >{{ ssoGoogleSaving ? 'Saving…' : 'Save' }}</button>
        <button type="button" class="ms-auto px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="closeModal">Cancel</button>
      </div>
    </SettingsProviderConfigModal>

    <!-- Microsoft Modal -->
    <SettingsProviderConfigModal :model-value="activeModal === 'microsoft'" title="Configure Microsoft / Entra SSO" @close="closeModal">
      <IdpLogoPicker v-model="ssoMicrosoft.logo" />
      <!-- Redirect URI -->
      <div class="mb-4 rounded-xl border border-[#E9E0D3] bg-[#faf8f3] px-3 py-2.5">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-[#6b6b6b]">Redirect URI</span>
          <button type="button" class="text-[11px] text-[#C2541E] hover:text-[#A8330F] font-medium" @click="copyToClipboard(microsoftRedirectUri, 'ms-redirect')">
            {{ copied === 'ms-redirect' ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <code class="text-[11px] font-mono text-[#6b6b6b] break-all">{{ microsoftRedirectUri }}</code>
        <p class="text-[11px] text-[#9a958c] mt-1">Paste this into the Azure app registration redirect URIs.</p>
      </div>

      <div class="flex items-center justify-between mb-4">
        <span class="text-xs font-semibold text-[#6b6b6b]">Enable Microsoft SSO</span>
        <label class="flex items-center gap-2 cursor-pointer">
          <button
            type="button"
            class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
            :class="ssoMicrosoft.enabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
            @click="ssoMicrosoft.enabled = !ssoMicrosoft.enabled"
          >
            <span
              class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all"
              :class="ssoMicrosoft.enabled ? 'left-[18px]' : 'left-0.5'"
            ></span>
          </button>
          <span class="text-xs text-[#6b6b6b]">{{ ssoMicrosoft.enabled ? 'Enabled' : 'Disabled' }}</span>
        </label>
      </div>

      <div class="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2.5 items-center">
        <span class="text-xs text-[#6b6b6b]">Tenant ID</span>
        <input
          v-model="ssoMicrosoft.tenant_id"
          type="text"
          placeholder="00000000-0000-0000-0000-000000000000"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="text-xs text-[#6b6b6b]">Client ID</span>
        <input
          v-model="ssoMicrosoft.client_id"
          type="text"
          placeholder="application (client) id"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="text-xs text-[#6b6b6b]">Client secret</span>
        <input
          v-model="ssoMicrosoft.client_secret"
          type="password"
          :placeholder="ssoMicrosoft.client_secret_set ? 'configured' : 'paste secret…'"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="col-start-2 text-[11px] text-[#9a958c]">Encrypted at rest (Fernet). Write-only — never echoed back.</span>
        <label class="col-span-2 flex items-center gap-2 cursor-pointer mt-1">
          <input v-model="ssoMicrosoft.sync_groups" type="checkbox" class="accent-[#C2541E] w-3.5 h-3.5" />
          <span class="text-xs text-[#6b6b6b]">Sync groups from Entra (Microsoft Graph) — maps Entra groups to Dash Groups</span>
        </label>
      </div>
      <p class="text-[11px] text-[#9a958c] mt-2">
        Issuer auto-built:
        <code class="font-mono">https://login.microsoftonline.com/{{ ssoMicrosoft.tenant_id || '&lt;tenant&gt;' }}/v2.0</code>
      </p>

      <div v-if="ssoMicrosoftTestResult" class="mt-3 text-xs" :class="ssoMicrosoftTestResult.ok ? 'text-green-600' : 'text-red-500'">
        {{ ssoMicrosoftTestResult.text }}
      </div>

      <!-- Modal footer -->
      <div class="flex items-center gap-2 mt-5 pt-4 border-t border-[#E9E0D3]">
        <button
          type="button"
          class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer disabled:opacity-65"
          :disabled="ssoMicrosoftTesting"
          @click="handleTestMicrosoft"
        >{{ ssoMicrosoftTesting ? 'Testing…' : 'Test' }}</button>
        <button
          type="button"
          class="px-4 py-2.5 text-xs bg-[#C2541E] hover:bg-[#A8330F] text-white rounded-xl font-semibold transition-colors cursor-pointer disabled:opacity-65"
          :disabled="ssoMicrosoftSaving"
          @click="handleSaveMicrosoftAndClose"
        >{{ ssoMicrosoftSaving ? 'Saving…' : 'Save' }}</button>
        <button type="button" class="ms-auto px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="closeModal">Cancel</button>
      </div>
    </SettingsProviderConfigModal>

    <!-- Custom OIDC Modal -->
    <SettingsProviderConfigModal :model-value="activeModal === 'oidc'" :title="activeOidcIdx !== null && oidcProviders[activeOidcIdx] ? `Configure ${oidcProviders[activeOidcIdx].label || oidcProviders[activeOidcIdx].name || 'OIDC Provider'}` : 'Configure OIDC Provider'" @close="closeModal">
      <template v-if="activeOidcIdx !== null && oidcProviders[activeOidcIdx]">
        <IdpLogoPicker v-model="oidcProviders[activeOidcIdx].logo" />
        <!-- Redirect URI -->
        <div class="mb-4 rounded-xl border border-[#E9E0D3] bg-[#faf8f3] px-3 py-2.5">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-[#6b6b6b]">Redirect URI</span>
            <button type="button" class="text-[11px] text-[#C2541E] hover:text-[#A8330F] font-medium" @click="copyToClipboard(oidcRedirectUri(oidcProviders[activeOidcIdx].name), 'oidc-redirect')">
              {{ copied === 'oidc-redirect' ? 'Copied!' : 'Copy' }}
            </button>
          </div>
          <code class="text-[11px] font-mono text-[#6b6b6b] break-all">{{ oidcRedirectUri(oidcProviders[activeOidcIdx].name) }}</code>
          <p class="text-[11px] text-[#9a958c] mt-1">Paste this into your identity provider's authorized redirect URIs.</p>
        </div>

        <div class="flex items-center justify-between mb-4">
          <span class="text-xs font-semibold text-[#6b6b6b]">Enable this provider</span>
          <label class="flex items-center gap-2 cursor-pointer">
            <button
              type="button"
              class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
              :class="oidcProviders[activeOidcIdx].enabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
              @click="oidcProviders[activeOidcIdx].enabled = !oidcProviders[activeOidcIdx].enabled"
            >
              <span
                class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all"
                :class="oidcProviders[activeOidcIdx].enabled ? 'left-[18px]' : 'left-0.5'"
              ></span>
            </button>
            <span class="text-xs text-[#6b6b6b]">{{ oidcProviders[activeOidcIdx].enabled ? 'Enabled' : 'Disabled' }}</span>
          </label>
        </div>

        <div class="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2.5 items-center">
          <span class="text-xs text-[#6b6b6b]">Name (slug)</span>
          <input
            v-model="oidcProviders[activeOidcIdx].name"
            type="text"
            placeholder="e.g. okta"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
          />
          <span class="text-xs text-[#6b6b6b]">Label</span>
          <input
            v-model="oidcProviders[activeOidcIdx].label"
            type="text"
            placeholder="e.g. Okta"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#C2541E]"
          />
          <span class="text-xs text-[#6b6b6b]">Issuer URL</span>
          <input
            v-model="oidcProviders[activeOidcIdx].issuer"
            type="text"
            placeholder="https://your-idp.example.com"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
          />
          <span class="text-xs text-[#6b6b6b]">Client ID</span>
          <input
            v-model="oidcProviders[activeOidcIdx].client_id"
            type="text"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
          />
          <span class="text-xs text-[#6b6b6b]">Client secret</span>
          <input
            v-model="oidcProviders[activeOidcIdx].client_secret"
            type="password"
            :placeholder="oidcProviders[activeOidcIdx].client_secret_set ? 'configured' : 'paste secret…'"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
          />
          <span class="text-xs text-[#6b6b6b]">Scopes (csv)</span>
          <input
            v-model="oidcProviders[activeOidcIdx].scopesCsv"
            type="text"
            placeholder="openid,profile,email"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
          />
          <span class="text-xs text-[#6b6b6b]">Group claim</span>
          <input
            v-model="oidcProviders[activeOidcIdx].group_claim"
            type="text"
            placeholder="groups"
            class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
          />
          <label class="col-span-2 flex items-center gap-2 cursor-pointer mt-1">
            <input v-model="oidcProviders[activeOidcIdx].sync_groups" type="checkbox" class="accent-[#C2541E] w-3.5 h-3.5" />
            <span class="text-xs text-[#6b6b6b]">Sync groups from this provider</span>
          </label>
        </div>

        <!-- Modal footer -->
        <div class="flex items-center gap-2 mt-5 pt-4 border-t border-[#E9E0D3]">
          <button
            type="button"
            class="px-4 py-2.5 text-xs bg-[#C2541E] hover:bg-[#A8330F] text-white rounded-xl font-semibold transition-colors cursor-pointer disabled:opacity-65"
            :disabled="ssoOidcSaving"
            @click="handleSaveOidcAndClose"
          >{{ ssoOidcSaving ? 'Saving…' : 'Save' }}</button>
          <button type="button" class="ms-auto px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="closeModal">Cancel</button>
        </div>
      </template>
    </SettingsProviderConfigModal>

    <!-- SCIM Modal -->
    <SettingsProviderConfigModal :model-value="activeModal === 'scim'" title="Configure SCIM Provisioning" @close="closeModal">
      <!-- SCIM Endpoint URL -->
      <div class="mb-4 rounded-lg border border-[#E9E0D3] p-3">
        <label class="block text-xs font-medium text-[#6b6b6b] mb-1">{{ $t('settings.identityProvider.scimBaseUrl') }}</label>
        <div class="flex items-center gap-2">
          <code class="flex-1 text-xs bg-[#F4EEE5] px-2 py-1.5 rounded-lg border border-[#E9E0D3] text-[#6b6b6b] font-mono">
            {{ scimBaseUrl }}
          </code>
          <button
            class="px-3 py-2 text-xs text-[#1f2328] bg-white border border-[#E9E0D3] rounded-lg hover:bg-[#F4EEE5] transition-colors cursor-pointer"
            @click="copyToClipboard(scimBaseUrl)"
          >
            {{ copied === 'url' ? $t('settings.identityProvider.copied') : $t('settings.identityProvider.copy') }}
          </button>
        </div>
        <p class="text-[11px] text-[#9a958c] mt-1">{{ $t('settings.identityProvider.scimBaseUrlHint') }}</p>
      </div>

      <!-- Token Management -->
      <div class="mb-3 flex items-center justify-between">
        <label class="text-xs font-medium text-[#6b6b6b]">{{ $t('settings.identityProvider.bearerTokens') }}</label>
        <button
          class="px-3 py-2.5 text-xs text-white bg-[#C2541E] hover:bg-[#A8330F] rounded-xl transition-colors cursor-pointer"
          @click="showCreateModal = true"
        >
          {{ $t('settings.identityProvider.generateToken') }}
        </button>
      </div>

      <!-- Loading State -->
      <div v-if="scimLoading" class="py-8 text-center">
        <div class="inline-block w-4 h-4 border-2 border-[#E9E0D3] border-t-[#9a958c] rounded-full animate-spin"></div>
      </div>

      <!-- Error State -->
      <div v-else-if="scimError" class="py-6 text-center text-xs text-red-500">
        {{ scimError }}
      </div>

      <!-- Tokens List -->
      <div v-else class="border border-[#E9E0D3] rounded-lg overflow-hidden">
        <template v-if="tokens.length > 0">
          <div
            v-for="(token, idx) in tokens"
            :key="token.id"
            class="flex items-center px-3 py-2.5 text-xs"
            :class="{ 'border-t border-[#E9E0D3]': idx > 0 }"
          >
            <span class="w-36 flex-shrink-0 text-[#6b6b6b] font-medium truncate">{{ token.name }}</span>
            <span class="w-36 flex-shrink-0 text-[#9a958c] font-mono text-[11px]">{{ token.token_prefix }}...</span>
            <span class="flex-1 text-[#9a958c] text-[11px]">
              <template v-if="token.last_used_at">
                {{ $t('settings.identityProvider.lastUsed', { when: formatRelativeTime(token.last_used_at) }) }}
              </template>
              <template v-else>
                {{ $t('settings.identityProvider.neverUsed') }}
              </template>
            </span>
            <span class="w-24 flex-shrink-0 text-[#9a958c] text-[11px]">
              {{ formatRelativeTime(token.created_at) }}
            </span>
            <button
              class="text-[11px] text-red-500 hover:text-red-700 ms-2"
              @click="confirmRevoke(token)"
            >
              {{ $t('settings.identityProvider.revoke') }}
            </button>
          </div>
        </template>

        <!-- Empty State -->
        <div v-else class="py-8 text-center">
          <p class="text-xs text-[#9a958c]">{{ $t('settings.identityProvider.noTokens') }}</p>
          <p class="text-[11px] text-[#9a958c] mt-1">{{ $t('settings.identityProvider.noTokensHint') }}</p>
        </div>
      </div>

      <!-- Modal footer -->
      <div class="flex justify-end mt-5 pt-4 border-t border-[#E9E0D3]">
        <button type="button" class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="closeModal">Close</button>
      </div>
    </SettingsProviderConfigModal>

    <!-- LDAP Modal -->
    <SettingsProviderConfigModal :model-value="activeModal === 'ldap'" title="Configure LDAP Directory Sync" @close="closeModal">
      <IdpLogoPicker v-model="ldapForm.logo" />
      <!-- Enable toggle -->
      <div class="flex items-center justify-between mb-4">
        <span class="text-sm font-semibold text-[#1f2328]">LDAP Configuration</span>
        <label class="flex items-center gap-2 cursor-pointer">
          <button
            type="button"
            class="relative w-9 h-5 rounded-full transition-colors focus:outline-none flex-shrink-0"
            :class="ldapForm.enabled ? 'bg-[#C2541E]' : 'bg-[#E9E0D3]'"
            @click="ldapForm.enabled = !ldapForm.enabled"
          >
            <span
              class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all"
              :class="ldapForm.enabled ? 'left-[18px]' : 'left-0.5'"
            ></span>
          </button>
          <span class="text-xs text-[#6b6b6b]">{{ ldapForm.enabled ? 'Enabled' : 'Enable' }}</span>
        </label>
      </div>

      <!-- Core fields -->
      <div class="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2.5 items-center">
        <span class="text-xs text-[#6b6b6b]">Server URL</span>
        <input
          v-model="ldapForm.url"
          type="text"
          placeholder="ldaps://ad.corp.com:636"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="text-xs text-[#6b6b6b]">Bind DN</span>
        <input
          v-model="ldapForm.bind_dn"
          type="text"
          placeholder="cn=svc,ou=Services,dc=corp,dc=com"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="text-xs text-[#6b6b6b]">Bind password</span>
        <input
          v-model="ldapForm.bind_password"
          type="password"
          :placeholder="ldapForm.bind_password_set ? 'configured' : 'paste bind password…'"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />
        <span class="col-start-2 text-[11px] text-[#9a958c]">Encrypted at rest. Write-only.</span>
        <span class="text-xs text-[#6b6b6b]">Base DN</span>
        <input
          v-model="ldapForm.base_dn"
          type="text"
          placeholder="dc=corp,dc=com"
          class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
        />

        <!-- Advanced collapsible -->
        <details class="col-span-2 mt-1">
          <summary class="cursor-pointer text-xs text-[#C2541E] font-medium list-none py-1 select-none">
            <span class="inline-flex items-center gap-1">
              <span>{{ ldapAdvOpen ? '▾' : '▸' }}</span>
              Advanced (search bases · filters · attributes · member format)
            </span>
          </summary>
          <div
            class="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2.5 items-center mt-2 bg-[#faf8f3] border border-[#E9E0D3] rounded-xl p-4"
            @toggle.capture="ldapAdvOpen = !ldapAdvOpen"
          >
            <span class="text-xs text-[#6b6b6b]">User search base</span>
            <input
              v-model="ldapForm.user_search_base"
              type="text"
              placeholder="ou=Users,dc=corp,dc=com"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">Group search base</span>
            <input
              v-model="ldapForm.group_search_base"
              type="text"
              placeholder="ou=Groups,dc=corp,dc=com"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">User filter</span>
            <input
              v-model="ldapForm.user_search_filter"
              type="text"
              placeholder="(objectClass=person)"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">Group filter</span>
            <input
              v-model="ldapForm.group_search_filter"
              type="text"
              placeholder="(objectClass=group)"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">Email attr</span>
            <input
              v-model="ldapForm.user_email_attribute"
              type="text"
              placeholder="mail"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">Name attr</span>
            <input
              v-model="ldapForm.user_name_attribute"
              type="text"
              placeholder="cn"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">Group name attr</span>
            <input
              v-model="ldapForm.group_name_attribute"
              type="text"
              placeholder="cn"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
            />
            <span class="text-xs text-[#6b6b6b]">Member attr</span>
            <select
              v-model="ldapForm.group_member_attribute"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#C2541E]"
            >
              <option value="member">member (AD / RFC 2256)</option>
              <option value="memberUid">memberUid (OpenLDAP posixGroup)</option>
            </select>
            <span class="text-xs text-[#6b6b6b]">Member format</span>
            <select
              v-model="ldapForm.group_member_format"
              class="w-full border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#C2541E]"
            >
              <option value="dn">DN (full distinguished name)</option>
              <option value="uid">UID (username only)</option>
            </select>
            <span class="text-xs text-[#6b6b6b]">Sync interval</span>
            <div class="flex items-center gap-2">
              <input
                v-model.number="ldapForm.sync_interval_minutes"
                type="number"
                min="5"
                max="1440"
                class="w-24 border border-[#E9E0D3] rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-[#C2541E]"
              />
              <span class="text-xs text-[#9a958c]">minutes</span>
            </div>
            <label class="col-span-2 flex items-center gap-2 cursor-pointer mt-1">
              <input v-model="ldapForm.auto_provision_users" type="checkbox" class="accent-[#C2541E] w-3.5 h-3.5" />
              <span class="text-xs text-[#6b6b6b]">Auto-provision users on first login</span>
            </label>
          </div>
        </details>
      </div>

      <!-- Test result flash -->
      <div v-if="ldapNewTestResult" class="mt-3 rounded-lg border px-3 py-2 text-xs"
        :class="ldapNewTestResult.connected
          ? 'border-green-200 bg-green-50 text-green-700'
          : 'border-red-200 bg-red-50 text-red-600'"
      >
        <template v-if="ldapNewTestResult.connected">
          Connected
          <template v-if="ldapNewTestResult.server"> · {{ ldapNewTestResult.server }}</template>
          <template v-if="ldapNewTestResult.user_count !== null"> · {{ ldapNewTestResult.user_count }} users</template>
          <template v-if="ldapNewTestResult.group_count !== null"> · {{ ldapNewTestResult.group_count }} groups</template>
        </template>
        <template v-else>
          {{ ldapNewTestResult.error || 'Connection failed' }}
        </template>
      </div>

      <!-- Modal footer -->
      <div class="flex items-center gap-2 mt-5 pt-4 border-t border-[#E9E0D3]">
        <button
          type="button"
          class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer disabled:opacity-65"
          :disabled="ldapFormTesting"
          @click="handleLdapTestNew"
        >{{ ldapFormTesting ? 'Testing…' : 'Test connection' }}</button>
        <button
          type="button"
          class="px-4 py-2.5 text-xs bg-[#C2541E] hover:bg-[#A8330F] text-white rounded-xl font-semibold transition-colors cursor-pointer disabled:opacity-65"
          :disabled="ldapFormSaving"
          @click="handleLdapSaveAndClose"
        >{{ ldapFormSaving ? 'Saving…' : 'Save' }}</button>
        <button type="button" class="ms-auto px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="closeModal">Cancel</button>
      </div>
    </SettingsProviderConfigModal>

    <!-- ================================================================== -->
    <!-- SCIM Modals (Create + Revoke)                                       -->
    <!-- ================================================================== -->

    <!-- Create Token Modal -->
    <div v-if="showCreateModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]" @click.self="dismissCreateModal">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-sm p-4">
        <h3 class="text-sm font-medium text-[#1f2328] mb-3">{{ $t('settings.identityProvider.generateTokenTitle') }}</h3>

        <template v-if="!createdToken">
          <div class="mb-3">
            <label class="block text-xs text-[#6b6b6b] mb-1">{{ $t('settings.identityProvider.nameLabel') }}</label>
            <input
              v-model="newTokenName"
              type="text"
              :placeholder="$t('settings.identityProvider.namePlaceholder')"
              class="w-full px-2 py-1.5 text-xs border border-[#E9E0D3] rounded-lg focus:outline-none focus:border-[#C2541E]"
              @keydown.enter="handleCreateToken"
            />
          </div>
          <div class="flex justify-end gap-2">
            <button class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="dismissCreateModal">{{ $t('settings.identityProvider.cancel') }}</button>
            <button
              class="px-4 py-2.5 text-xs text-white bg-[#C2541E] hover:bg-[#A8330F] rounded-xl transition-colors cursor-pointer disabled:opacity-65"
              :disabled="!newTokenName.trim() || creating"
              @click="handleCreateToken"
            >
              {{ creating ? $t('settings.identityProvider.generating') : $t('settings.identityProvider.generate') }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="rounded-lg border border-amber-200 bg-amber-50 p-3 mb-3">
            <div class="flex items-start gap-2">
              <svg class="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
              <p class="text-xs font-medium text-amber-800">{{ $t('settings.identityProvider.copyWarning') }}</p>
            </div>
          </div>
          <div class="flex items-center gap-2 mb-3">
            <code class="flex-1 text-[11px] bg-[#F4EEE5] px-2 py-1.5 rounded-lg border border-[#E9E0D3] text-[#6b6b6b] font-mono truncate">
              {{ createdToken }}
            </code>
            <button
              class="px-3 py-2 text-xs text-[#1f2328] bg-white border border-[#E9E0D3] rounded-lg hover:bg-[#F4EEE5] transition-colors cursor-pointer flex-shrink-0"
              @click="copyToClipboard(createdToken!, 'token')"
            >
              {{ copied === 'token' ? $t('settings.identityProvider.copied') : $t('settings.identityProvider.copy') }}
            </button>
          </div>
          <div class="flex justify-end">
            <button class="px-4 py-2.5 text-xs text-white bg-[#C2541E] hover:bg-[#A8330F] rounded-xl transition-colors cursor-pointer" @click="dismissCreateModal">{{ $t('settings.identityProvider.done') }}</button>
          </div>
        </template>
      </div>
    </div>

    <!-- Revoke Confirmation Modal -->
    <div v-if="tokenToRevoke" class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]" @click.self="tokenToRevoke = null">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-sm p-4">
        <h3 class="text-sm font-medium text-[#1f2328] mb-2">{{ $t('settings.identityProvider.revokeTitle') }}</h3>
        <p class="text-xs text-[#6b6b6b] mb-3">
          {{ $t('settings.identityProvider.revokeWarning', { name: tokenToRevoke.name }) }}
        </p>
        <div class="flex justify-end gap-2">
          <button class="px-3 py-2 text-xs border border-[#E9E0D3] rounded-lg text-[#1f2328] bg-white hover:bg-[#F4EEE5] transition-colors cursor-pointer" @click="tokenToRevoke = null">{{ $t('settings.identityProvider.cancel') }}</button>
          <button class="px-3 py-2 text-xs text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors cursor-pointer" @click="handleRevoke">{{ $t('settings.identityProvider.revoke') }}</button>
        </div>
      </div>
    </div>

    <!-- Provider library (Add provider) -->
    <IdpProviderLibraryModal :open="showLibrary" @close="showLibrary = false" @select="onLibrarySelect" />

  </div>
</template>

<script setup lang="ts">
import { useScimTokens, type ScimToken } from '~/ee/composables/useScimTokens'
import { useLdapSync, type SyncResult as LDAPSyncResult } from '~/ee/composables/useLdapSync'
import { idpLogoSvg } from '~/utils/idpLogos'
import { IDP_TEMPLATES, type IdpTemplate } from '~/utils/idpTemplates'

definePageMeta({
  auth: true,
  permissions: ['manage_identity_providers'],
  layout: 'settings'
})

const { hasFeature, license } = useEnterprise()
const toast = useToast()

// ── Modal state ───────────────────────────────────────────────────────────
type ModalKey = 'google' | 'microsoft' | 'oidc' | 'scim' | 'ldap' | null
const activeModal = ref<ModalKey>(null)
const activeOidcIdx = ref<number | null>(null)

function openModal(key: Exclude<ModalKey, null>, oidcIdx?: number) {
  activeModal.value = key
  if (key === 'oidc' && oidcIdx !== undefined) {
    activeOidcIdx.value = oidcIdx
  }
}

function closeModal() {
  activeModal.value = null
  activeOidcIdx.value = null
  // clear transient test results
  ssoGoogleTestResult.value = null
  ssoMicrosoftTestResult.value = null
  ldapNewTestResult.value = null
}

// ── SSO state ──────────────────────────────────────────────────────────────

const ssoAuthMode = ref<'local_only' | 'hybrid' | 'sso_only'>('hybrid')
const authModeOptions = [
  { value: 'local_only', label: 'Local only' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'sso_only', label: 'SSO only' },
]

const ssoGoogle = reactive({
  enabled: false,
  logo: 'google',
  client_id: '',
  client_secret: '',
  client_secret_set: false,
})
const ssoGoogleSaving = ref(false)
const ssoGoogleTesting = ref(false)
const ssoGoogleTestResult = ref<{ ok: boolean; text: string } | null>(null)

const ssoMicrosoft = reactive({
  enabled: false,
  logo: 'microsoft',
  tenant_id: '',
  client_id: '',
  client_secret: '',
  client_secret_set: false,
  sync_groups: false,
})
const ssoMicrosoftSaving = ref(false)
const ssoMicrosoftTesting = ref(false)
const ssoMicrosoftTestResult = ref<{ ok: boolean; text: string } | null>(null)

interface OidcProvider {
  name: string
  label: string
  enabled: boolean
  logo: string
  issuer: string
  client_id: string
  client_secret: string
  client_secret_set: boolean
  scopesCsv: string
  sync_groups: boolean
  group_claim: string
}

const oidcProviders = ref<OidcProvider[]>([])
const ssoOidcSaving = ref(false)

// ── Redirect URI helpers ──────────────────────────────────────────────────
const googleRedirectUri = computed(() => {
  if (process.client) return `${window.location.origin}/api/auth/google/callback`
  return '/api/auth/google/callback'
})
const microsoftRedirectUri = computed(() => {
  if (process.client) return `${window.location.origin}/api/auth/microsoft/callback`
  return '/api/auth/microsoft/callback'
})
function oidcRedirectUri(name: string) {
  if (process.client) return `${window.location.origin}/api/auth/${name || '<name>'}/callback`
  return `/api/auth/${name || '<name>'}/callback`
}

const ssoLoaded = ref(false)

async function loadSso() {
  try {
    const res = await useMyFetch('/api/organization/sso')
    const data = res.data.value as any
    if (!data) return
    ssoAuthMode.value = data.auth_mode || 'hybrid'
    if (data.google) {
      ssoGoogle.enabled = data.google.enabled ?? false
      ssoGoogle.logo = data.google.logo || 'google'
      ssoGoogle.client_id = data.google.client_id || ''
      ssoGoogle.client_secret_set = data.google.client_secret_set ?? false
    }
    const providers: OidcProvider[] = []
    for (const p of (data.oidc || [])) {
      if (p.name === 'microsoft') {
        // Parse tenant from issuer: https://login.microsoftonline.com/<tenant>/v2.0
        const m = (p.issuer || '').match(/microsoftonline\.com\/([^/]+)\/v2\.0/)
        ssoMicrosoft.enabled = p.enabled ?? false
        ssoMicrosoft.logo = p.logo || 'microsoft'
        ssoMicrosoft.tenant_id = m ? m[1] : ''
        ssoMicrosoft.client_id = p.client_id || ''
        ssoMicrosoft.client_secret_set = p.client_secret_set ?? false
        ssoMicrosoft.sync_groups = p.sync_groups ?? false
      } else {
        providers.push({
          name: p.name || '',
          label: p.label || '',
          enabled: p.enabled ?? false,
          logo: p.logo || p.name || 'oidc',
          issuer: p.issuer || '',
          client_id: p.client_id || '',
          client_secret: '',
          client_secret_set: p.client_secret_set ?? false,
          scopesCsv: (p.scopes || []).join(','),
          sync_groups: p.sync_groups ?? false,
          group_claim: p.group_claim || 'groups',
        })
      }
    }
    oidcProviders.value = providers
  } catch {
    // ignore — SSO not yet configured
  }
}

async function handleSaveGoogle() {
  ssoGoogleSaving.value = true
  try {
    const body: any = { enabled: ssoGoogle.enabled, logo: ssoGoogle.logo, client_id: ssoGoogle.client_id }
    if (ssoGoogle.client_secret) body.client_secret = ssoGoogle.client_secret
    const res = await useMyFetch('/api/organization/sso/google', { method: 'PUT', body })
    if (res.status.value === 'success') {
      toast.add({ title: 'Google SSO saved', color: 'green' })
      ssoGoogle.client_secret_set = ssoGoogle.client_secret_set || !!ssoGoogle.client_secret
      ssoGoogle.client_secret = ''
    } else {
      toast.add({ title: 'Failed to save Google SSO', description: (res.error.value as any)?.data?.detail || 'Error', color: 'red' })
    }
  } finally {
    ssoGoogleSaving.value = false
  }
}

async function handleSaveGoogleAndClose() {
  await handleSaveGoogle()
  if (!ssoGoogleSaving.value) closeModal()
}

async function handleTestGoogle() {
  ssoGoogleTesting.value = true
  ssoGoogleTestResult.value = null
  try {
    const res = await useMyFetch('/api/organization/sso/google/test', { method: 'POST' })
    const data = res.data.value as any
    if (res.status.value === 'success' && data?.success) {
      ssoGoogleTestResult.value = { ok: true, text: 'Connection OK — redirect URI is reachable.' }
    } else {
      ssoGoogleTestResult.value = { ok: false, text: data?.detail || 'Test failed — check Client ID and secret.' }
    }
  } catch {
    ssoGoogleTestResult.value = { ok: false, text: 'Test failed — check Client ID and secret.' }
  } finally {
    ssoGoogleTesting.value = false
  }
}

function buildMicrosoftOidcPayload() {
  const tenantId = ssoMicrosoft.tenant_id.trim()
  const p: any = {
    name: 'microsoft',
    label: 'Microsoft',
    enabled: ssoMicrosoft.enabled,
    logo: ssoMicrosoft.logo || 'microsoft',
    issuer: `https://login.microsoftonline.com/${tenantId}/v2.0`,
    client_id: ssoMicrosoft.client_id,
    sync_groups: ssoMicrosoft.sync_groups,
    group_claim: 'groups',
    scopes: ['openid', 'profile', 'email'],
  }
  if (ssoMicrosoft.client_secret) p.client_secret = ssoMicrosoft.client_secret
  return p
}

async function handleSaveMicrosoft() {
  ssoMicrosoftSaving.value = true
  try {
    const msPayload = buildMicrosoftOidcPayload()
    // Build the full oidc list: replace/add microsoft entry, keep others
    const others = oidcProviders.value.map(buildOidcPayload)
    const res = await useMyFetch('/api/organization/sso/oidc', {
      method: 'PUT',
      body: { providers: [msPayload, ...others] },
    })
    if (res.status.value === 'success') {
      toast.add({ title: 'Microsoft SSO saved', color: 'green' })
      ssoMicrosoft.client_secret_set = ssoMicrosoft.client_secret_set || !!ssoMicrosoft.client_secret
      ssoMicrosoft.client_secret = ''
    } else {
      toast.add({ title: 'Failed to save Microsoft SSO', description: (res.error.value as any)?.data?.detail || 'Error', color: 'red' })
    }
  } finally {
    ssoMicrosoftSaving.value = false
  }
}

async function handleSaveMicrosoftAndClose() {
  await handleSaveMicrosoft()
  if (!ssoMicrosoftSaving.value) closeModal()
}

async function handleTestMicrosoft() {
  ssoMicrosoftTesting.value = true
  ssoMicrosoftTestResult.value = null
  try {
    const res = await useMyFetch('/api/organization/sso/oidc/microsoft/test', { method: 'POST' })
    const data = res.data.value as any
    if (res.status.value === 'success' && data?.success) {
      ssoMicrosoftTestResult.value = { ok: true, text: 'Connection OK — OIDC discovery endpoint reachable.' }
    } else {
      ssoMicrosoftTestResult.value = { ok: false, text: data?.detail || 'Test failed — check Tenant ID, Client ID and secret.' }
    }
  } catch {
    ssoMicrosoftTestResult.value = { ok: false, text: 'Test failed — check Tenant ID, Client ID and secret.' }
  } finally {
    ssoMicrosoftTesting.value = false
  }
}

function buildOidcPayload(p: OidcProvider) {
  const out: any = {
    name: p.name,
    label: p.label,
    enabled: p.enabled,
    logo: p.logo || p.name || 'oidc',
    issuer: p.issuer,
    client_id: p.client_id,
    sync_groups: p.sync_groups,
    group_claim: p.group_claim,
    scopes: p.scopesCsv.split(',').map((s) => s.trim()).filter(Boolean),
  }
  if (p.client_secret) out.client_secret = p.client_secret
  return out
}

async function handleSaveOidc() {
  ssoOidcSaving.value = true
  try {
    const msPayload = buildMicrosoftOidcPayload()
    const others = oidcProviders.value.map(buildOidcPayload)
    const res = await useMyFetch('/api/organization/sso/oidc', {
      method: 'PUT',
      body: { providers: [msPayload, ...others] },
    })
    if (res.status.value === 'success') {
      toast.add({ title: 'OIDC providers saved', color: 'green' })
      // Clear secrets
      for (const p of oidcProviders.value) {
        if (p.client_secret) {
          p.client_secret_set = true
          p.client_secret = ''
        }
      }
    } else {
      toast.add({ title: 'Failed to save OIDC providers', description: (res.error.value as any)?.data?.detail || 'Error', color: 'red' })
    }
  } finally {
    ssoOidcSaving.value = false
  }
}

async function handleSaveOidcAndClose() {
  await handleSaveOidc()
  if (!ssoOidcSaving.value) closeModal()
}

function addOidcProvider() {
  oidcProviders.value.push({
    name: '',
    label: '',
    enabled: true,
    logo: 'oidc',
    issuer: '',
    client_id: '',
    client_secret: '',
    client_secret_set: false,
    scopesCsv: 'openid,profile,email',
    sync_groups: false,
    group_claim: 'groups',
  })
  openModal('oidc', oidcProviders.value.length - 1)
}

function removeOidcProvider(idx: number) {
  oidcProviders.value.splice(idx, 1)
  handleSaveOidc()
}

async function handleAuthModeChange(mode: string) {
  try {
    const res = await useMyFetch('/api/organization/sso/auth-mode', { method: 'PUT', body: { mode } })
    if (res.status.value === 'success') {
      toast.add({ title: 'Auth mode updated', color: 'green' })
    } else {
      toast.add({ title: 'Failed to update auth mode', color: 'red' })
    }
  } catch {
    // ignore
  }
}

// ── Task 3: Sign-up toggle ────────────────────────────────────────────────
const signupEnabled = ref(false)
const signupSaving = ref(false)

async function loadSignupEnabled() {
  try {
    const settings = await $fetch('/api/settings') as any
    signupEnabled.value = !!(settings?.signup_enabled)
  } catch {
    // ignore
  }
}

async function handleSignupToggle() {
  const newVal = !signupEnabled.value
  signupSaving.value = true
  try {
    const res = await useMyFetch('/api/organization/signup-enabled', {
      method: 'PUT',
      body: { enabled: newVal },
    })
    if (res.status.value === 'success') {
      signupEnabled.value = newVal
      toast.add({ title: newVal ? 'Public sign-up enabled' : 'Public sign-up disabled', color: 'green' })
    } else {
      toast.add({ title: 'Failed to update sign-up setting', color: 'red' })
    }
  } catch {
    toast.add({ title: 'Failed to update sign-up setting', color: 'red' })
  } finally {
    signupSaving.value = false
  }
}

// ── SCIM ──────────────────────────────────────────────────────────────────
const { tokens, loading: scimLoading, error: scimError, fetchTokens, createToken, revokeToken } = useScimTokens()

const showCreateModal = ref(false)
const newTokenName = ref('SCIM Token')
const creating = ref(false)
const createdToken = ref<string | null>(null)
const tokenToRevoke = ref<ScimToken | null>(null)
const copied = ref<string | null>(null)
const hasFetchedScim = ref(false)

const scimBaseUrl = computed(() => {
  if (process.client) {
    return `${window.location.origin}/scim/v2`
  }
  return '/scim/v2'
})

const dismissCreateModal = () => {
  showCreateModal.value = false
  createdToken.value = null
  newTokenName.value = 'SCIM Token'
}

const handleCreateToken = async () => {
  if (!newTokenName.value.trim() || creating.value) return
  creating.value = true
  const result = await createToken(newTokenName.value.trim())
  creating.value = false
  if (result) {
    createdToken.value = result.token
  }
}

const confirmRevoke = (token: ScimToken) => {
  tokenToRevoke.value = token
}

const handleRevoke = async () => {
  if (!tokenToRevoke.value) return
  await revokeToken(tokenToRevoke.value.id)
  tokenToRevoke.value = null
  createdToken.value = null
}

// ── LDAP ──────────────────────────────────────────────────────────────────
const {
  status: ldapStatus,
  preview: ldapPreview,
  testResult: ldapTestResult,
  loading: ldapLoading,
  error: ldapError,
  fetchStatus: fetchLdapStatus,
  triggerSync,
  fetchPreview,
  testConnection,
} = useLdapSync()

const lastSyncResult = ref<LDAPSyncResult | null>(null)
const hasFetchedLdap = ref(false)

// LDAP config form state
const ldapForm = reactive({
  enabled: false,
  logo: 'ldap',
  url: '',
  bind_dn: '',
  bind_password: '',
  bind_password_set: false,
  use_ssl: false,
  start_tls: false,
  base_dn: '',
  user_search_base: '',
  user_search_filter: '(objectClass=person)',
  user_email_attribute: 'mail',
  user_name_attribute: 'cn',
  group_search_base: '',
  group_search_filter: '(objectClass=group)',
  group_name_attribute: 'cn',
  group_member_attribute: 'member',
  group_member_format: 'dn',
  sync_interval_minutes: 60,
  auto_provision_users: false,
})

const ldapFormSaving = ref(false)
const ldapFormTesting = ref(false)
const ldapNewTestResult = ref<{ connected: boolean; server?: string; vendor?: string; user_count?: number | null; group_count?: number | null; error?: string } | null>(null)
const ldapAdvOpen = ref(false)
const ldapFormLoaded = ref(false)

async function loadLdapConfig() {
  if (ldapFormLoaded.value) return
  ldapFormLoaded.value = true
  try {
    const res = await useMyFetch('/api/organization/ldap')
    const data = res.data.value as any
    if (!data) return
    ldapForm.enabled = data.enabled ?? false
    ldapForm.logo = data.logo || 'ldap'
    ldapForm.url = data.url || ''
    ldapForm.bind_dn = data.bind_dn || ''
    ldapForm.bind_password_set = data.bind_password_set ?? false
    ldapForm.use_ssl = data.use_ssl ?? false
    ldapForm.start_tls = data.start_tls ?? false
    ldapForm.base_dn = data.base_dn || ''
    ldapForm.user_search_base = data.user_search_base || ''
    ldapForm.user_search_filter = data.user_search_filter || '(objectClass=person)'
    ldapForm.user_email_attribute = data.user_email_attribute || 'mail'
    ldapForm.user_name_attribute = data.user_name_attribute || 'cn'
    ldapForm.group_search_base = data.group_search_base || ''
    ldapForm.group_search_filter = data.group_search_filter || '(objectClass=group)'
    ldapForm.group_name_attribute = data.group_name_attribute || 'cn'
    ldapForm.group_member_attribute = data.group_member_attribute || 'member'
    ldapForm.group_member_format = data.group_member_format || 'dn'
    ldapForm.sync_interval_minutes = data.sync_interval_minutes ?? 60
    ldapForm.auto_provision_users = data.auto_provision_users ?? false
  } catch {
    // not yet configured — defaults are fine
  }
}

function buildLdapPayload() {
  const p: any = {
    enabled: ldapForm.enabled,
    logo: ldapForm.logo,
    url: ldapForm.url,
    bind_dn: ldapForm.bind_dn,
    use_ssl: ldapForm.use_ssl,
    start_tls: ldapForm.start_tls,
    base_dn: ldapForm.base_dn,
    user_search_base: ldapForm.user_search_base,
    user_search_filter: ldapForm.user_search_filter,
    user_email_attribute: ldapForm.user_email_attribute,
    user_name_attribute: ldapForm.user_name_attribute,
    group_search_base: ldapForm.group_search_base,
    group_search_filter: ldapForm.group_search_filter,
    group_name_attribute: ldapForm.group_name_attribute,
    group_member_attribute: ldapForm.group_member_attribute,
    group_member_format: ldapForm.group_member_format,
    sync_interval_minutes: ldapForm.sync_interval_minutes,
    auto_provision_users: ldapForm.auto_provision_users,
  }
  if (ldapForm.bind_password) p.bind_password = ldapForm.bind_password
  return p
}

async function handleLdapSave() {
  ldapFormSaving.value = true
  try {
    const res = await useMyFetch('/api/organization/ldap', { method: 'PUT', body: buildLdapPayload() })
    if (res.status.value === 'success') {
      toast.add({ title: 'LDAP configuration saved', color: 'green' })
      ldapForm.bind_password_set = ldapForm.bind_password_set || !!ldapForm.bind_password
      ldapForm.bind_password = ''
      // refresh status so configured/unconfigured UI updates
      await fetchLdapStatus()
    } else {
      toast.add({ title: 'Failed to save LDAP configuration', description: (res.error.value as any)?.data?.detail || 'Error', color: 'red' })
    }
  } finally {
    ldapFormSaving.value = false
  }
}

async function handleLdapSaveAndClose() {
  await handleLdapSave()
  if (!ldapFormSaving.value) closeModal()
}

async function handleLdapTestNew() {
  ldapFormTesting.value = true
  ldapNewTestResult.value = null
  try {
    const res = await useMyFetch('/api/organization/ldap/test', { method: 'POST' })
    const data = res.data.value as any
    if (data) {
      ldapNewTestResult.value = data
    } else {
      ldapNewTestResult.value = { connected: false, error: 'No response from server' }
    }
  } catch {
    ldapNewTestResult.value = { connected: false, error: 'Test failed — check LDAP settings' }
  } finally {
    ldapFormTesting.value = false
  }
}

const handleTestConnection = async () => {
  await testConnection()
}

const handleSync = async () => {
  lastSyncResult.value = null
  ldapPreview.value = null
  const result = await triggerSync()
  if (result) {
    lastSyncResult.value = result
    setTimeout(() => { lastSyncResult.value = null }, 15000)
  }
}

const handlePreview = async () => {
  lastSyncResult.value = null
  await fetchPreview()
}

// ── Shared ────────────────────────────────────────────────────────────────
const copyToClipboard = async (text: string, key: string = 'url') => {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    setTimeout(() => { copied.value = null }, 2000)
  } catch {
    // Fallback
  }
}

const formatRelativeTime = (timestamp: string | null) => {
  if (!timestamp) return ''
  const isoTimestamp = timestamp.endsWith('Z') ? timestamp : timestamp + 'Z'
  const date = new Date(isoTimestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// ── Init ──────────────────────────────────────────────────────────────────
watch(
  () => license.value,
  (newLicense) => {
    if (newLicense && hasFeature('scim') && !hasFetchedScim.value) {
      hasFetchedScim.value = true
      fetchTokens()
    }
    if (newLicense && hasFeature('ldap') && !hasFetchedLdap.value) {
      hasFetchedLdap.value = true
      fetchLdapStatus()
      loadLdapConfig()
    }
  },
  { immediate: true }
)

// ── Logo + smart-status + provider-library (IdP redesign) ──────────────────
const showLibrary = ref(false)

// 4-state pill from (enabled × configured)
function pillText(enabled: boolean, configured: boolean) {
  if (enabled && configured) return '● On · Ready'
  if (enabled && !configured) return '⚠ On · Needs setup'
  if (!enabled && configured) return '○ Off · Configured'
  return '○ Disabled'
}
function pillClass(enabled: boolean, configured: boolean) {
  if (enabled && configured) return 'bg-[#E7F2EC] text-[#2f7a52] border border-[#cfe6da]'
  if (enabled && !configured) return 'bg-[#FBEEDD] text-[#9A5A12] border border-[#eed6b3]'
  return 'bg-[#F4EEE5] text-[#6b6b6b] border border-[#E9E0D3]'
}

const FIXED_DEFAULT_KEYS = ['okta', 'keycloak']
function findOidcIdx(name: string) {
  return oidcProviders.value.findIndex(p => (p.name || '').toLowerCase() === name)
}
function oidcConfigured(p: OidcProvider) {
  return !!(p.client_secret_set || (p.client_id && p.issuer))
}

async function quickToggleGoogle() {
  ssoGoogle.enabled = !ssoGoogle.enabled
  await handleSaveGoogle()
}
async function quickToggleMicrosoft() {
  ssoMicrosoft.enabled = !ssoMicrosoft.enabled
  await handleSaveMicrosoft()
}
async function quickToggleOidc(idx: number) {
  const p = oidcProviders.value[idx]
  if (!p) return
  p.enabled = !p.enabled
  await handleSaveOidc()
}
async function quickToggleLdap() {
  ldapForm.enabled = !ldapForm.enabled
  await handleLdapSave()
}

// Create a provider from a library template (or a default Okta/Keycloak row).
// enableOnly=true → persist immediately as enabled-but-unconfigured (amber state).
async function createFromTemplate(key: string, opts: { enableOnly?: boolean } = {}) {
  const tpl = IDP_TEMPLATES.find(t => t.key === key)
  const isGeneric = key === 'oidc' || !tpl
  oidcProviders.value.push({
    name: isGeneric ? '' : key,
    label: tpl ? tpl.name : '',
    enabled: true,
    logo: tpl ? tpl.logo : 'oidc',
    issuer: '',
    client_id: '',
    client_secret: '',
    client_secret_set: false,
    scopesCsv: (tpl ? tpl.scopes : ['openid', 'profile', 'email']).join(','),
    sync_groups: false,
    group_claim: tpl ? tpl.groupClaim : 'groups',
  })
  const idx = oidcProviders.value.length - 1
  if (opts.enableOnly) {
    await handleSaveOidc()
  } else {
    openModal('oidc', idx)
  }
}

function onLibrarySelect(tpl: IdpTemplate) {
  showLibrary.value = false
  const existing = findOidcIdx(tpl.key)
  if (existing >= 0 && tpl.key !== 'oidc') {
    openModal('oidc', existing)
    return
  }
  createFromTemplate(tpl.key)
}

// Default catalog row (Okta/Keycloak): backed by an oidc provider if present.
function defaultRow(key: string, name: string) {
  const idx = findOidcIdx(key)
  if (idx >= 0) {
    const p = oidcProviders.value[idx]
    return {
      id: 'oidc-' + idx,
      name: p.label || name,
      logo: p.logo || key,
      enabled: p.enabled,
      configured: oidcConfigured(p),
      removable: true,
      configure: () => openModal('oidc', idx),
      toggle: () => quickToggleOidc(idx),
      remove: () => removeOidcProvider(idx),
    }
  }
  return {
    id: 'default-' + key,
    name,
    logo: key,
    enabled: false,
    configured: false,
    removable: false,
    configure: () => createFromTemplate(key),
    toggle: () => createFromTemplate(key, { enableOnly: true }),
    remove: undefined as undefined | (() => void),
  }
}

// All SSO rows in display order: Google · Microsoft · Okta · Keycloak · custom.
const ssoRows = computed(() => {
  const rows: any[] = [
    {
      id: 'google',
      name: 'Google',
      logo: ssoGoogle.logo || 'google',
      enabled: ssoGoogle.enabled,
      configured: !!(ssoGoogle.client_secret_set || ssoGoogle.client_id),
      removable: false,
      configure: () => openModal('google'),
      toggle: quickToggleGoogle,
    },
    {
      id: 'microsoft',
      name: 'Microsoft / Entra',
      logo: ssoMicrosoft.logo || 'microsoft',
      enabled: ssoMicrosoft.enabled,
      configured: !!(ssoMicrosoft.client_secret_set || ssoMicrosoft.client_id),
      removable: false,
      configure: () => openModal('microsoft'),
      toggle: quickToggleMicrosoft,
    },
    defaultRow('okta', 'Okta'),
    defaultRow('keycloak', 'Keycloak'),
  ]
  oidcProviders.value.forEach((p, idx) => {
    if (FIXED_DEFAULT_KEYS.includes((p.name || '').toLowerCase())) return
    rows.push({
      id: 'oidc-' + idx,
      name: p.label || p.name || 'Unnamed provider',
      logo: p.logo || p.name || 'oidc',
      enabled: p.enabled,
      configured: oidcConfigured(p),
      removable: true,
      configure: () => openModal('oidc', idx),
      toggle: () => quickToggleOidc(idx),
      remove: () => removeOidcProvider(idx),
    })
  })
  return rows
})

onMounted(() => {
  loadSso()
  loadSignupEnabled()
})
</script>
