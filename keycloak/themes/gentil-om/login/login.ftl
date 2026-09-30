<#import "template.ftl" as layout>
<#--
  Página de login do Chat-bot O&M. Os campos de usuário e senha pertencem
  exclusivamente ao Keycloak — o frontend React nunca recebe a senha.
  Não há link público de cadastro: contas são criadas pela Gestão de Usuários.
-->
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=false; section>
    <#if section = "header">
        ${msg("loginAccountTitle")}
    <#elseif section = "subtitle">
        ${msg("omWelcomeSubtitle")}
    <#elseif section = "form">
        <div id="kc-form">
          <div id="kc-form-wrapper">
            <#if realm.password>
                <form id="kc-form-login" class="om-form" onsubmit="login.disabled = true; login.classList.add('om-button--loading'); return true;" action="${url.loginAction}" method="post" novalidate>
                    <#if messagesPerField.existsError('username','password')>
                        <div class="om-alert om-alert--error" role="alert" id="input-error">
                            <span class="om-alert__icon" aria-hidden="true"></span>
                            <span class="om-alert__text">${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}</span>
                        </div>
                    </#if>

                    <#if !usernameHidden??>
                        <div class="${properties.kcFormGroupClass!}">
                            <label for="username" class="${properties.kcLabelClass!}"><#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if></label>
                            <div class="om-input-shell">
                                <span class="om-icon om-icon--user om-input-shell__icon" aria-hidden="true"></span>
                                <input tabindex="1" id="username" class="${properties.kcInputClass!}" name="username" value="${(login.username!'')}"
                                       type="text" autofocus autocomplete="username" autocapitalize="none" spellcheck="false"
                                       placeholder="${msg('omUsernamePlaceholder')}"
                                       aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"
                                       <#if messagesPerField.existsError('username','password')>aria-describedby="input-error"</#if>
                                       dir="ltr"
                                />
                            </div>
                        </div>
                    </#if>

                    <div class="${properties.kcFormGroupClass!}">
                        <div class="om-label-row">
                            <label for="password" class="${properties.kcLabelClass!}">${msg("password")}</label>
                            <#if realm.resetPasswordAllowed>
                                <a tabindex="6" class="om-link" href="${url.loginResetCredentialsUrl}">${msg("doForgotPassword")}</a>
                            </#if>
                        </div>
                        <div class="${properties.kcInputGroup!} om-input-shell" dir="ltr">
                            <span class="om-icon om-icon--lock om-input-shell__icon" aria-hidden="true"></span>
                            <input tabindex="2" id="password" class="${properties.kcInputClass!}" name="password" type="password" autocomplete="current-password"
                                   placeholder="${msg('omPasswordPlaceholder')}"
                                   aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"
                                   <#if messagesPerField.existsError('username','password')>aria-describedby="input-error"</#if>
                            />
                            <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg("showPassword")}"
                                    aria-controls="password" data-password-toggle tabindex="3"
                                    data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                                    data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                                <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                            </button>
                        </div>
                    </div>

                    <#if realm.rememberMe && !usernameHidden??>
                        <div class="om-form-options">
                            <label class="om-check">
                                <input tabindex="4" class="om-check__input" id="rememberMe" name="rememberMe" type="checkbox" <#if login.rememberMe??>checked</#if>>
                                <span class="om-check__label">${msg("rememberMe")}</span>
                            </label>
                        </div>
                    </#if>

                    <div id="kc-form-buttons" class="om-form-buttons">
                        <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
                        <button tabindex="5" class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" name="login" id="kc-login" type="submit">
                            <span>${msg("doLogIn")}</span>
                            <span class="om-button__arrow" aria-hidden="true">→</span>
                        </button>
                    </div>
                </form>
            </#if>
          </div>
        </div>
        <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
    <#elseif section = "socialProviders" >
        <#if realm.password && social?? && social.providers?has_content>
            <div id="kc-social-providers" class="${properties.kcFormSocialAccountSectionClass!}">
                <p class="om-divider"><span>${msg("identity-provider-login-label")}</span></p>
                <ul class="${properties.kcFormSocialAccountListClass!}">
                    <#list social.providers as p>
                        <li>
                            <a data-once-link data-disabled-class="${properties.kcFormSocialAccountListButtonDisabledClass!}" id="social-${p.alias}"
                               class="${properties.kcFormSocialAccountListButtonClass!}" type="button" href="${p.loginUrl}">
                                <span class="${properties.kcFormSocialAccountNameClass!}">${p.displayName!}</span>
                            </a>
                        </li>
                    </#list>
                </ul>
            </div>
        </#if>
    </#if>
</@layout.registrationLayout>
