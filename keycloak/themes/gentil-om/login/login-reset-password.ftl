<#import "template.ftl" as layout>
<#-- "Esqueci minha senha" — só é acessível quando o realm permite (SMTP configurado). -->
<@layout.registrationLayout displayInfo=false displayMessage=!messagesPerField.existsError('username'); section>
    <#if section = "header">
        ${msg("emailForgotTitle")}
    <#elseif section = "subtitle">
        <#if realm.duplicateEmailsAllowed>${msg("emailInstructionUsername")}<#else>${msg("emailInstruction")}</#if>
    <#elseif section = "form">
        <form id="kc-reset-password-form" class="${properties.kcFormClass!}" action="${url.loginAction}" method="post" novalidate>
            <div class="${properties.kcFormGroupClass!}">
                <label for="username" class="${properties.kcLabelClass!}"><#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if></label>
                <div class="om-input-shell">
                    <span class="om-icon om-icon--user om-input-shell__icon" aria-hidden="true"></span>
                    <input type="text" id="username" name="username" class="${properties.kcInputClass!}" autofocus
                           value="${(auth.attemptedUsername!'')}" autocomplete="username" autocapitalize="none" spellcheck="false"
                           placeholder="${msg('omUsernamePlaceholder')}"
                           aria-invalid="<#if messagesPerField.existsError('username')>true</#if>" dir="ltr"/>
                </div>
                <#if messagesPerField.existsError('username')>
                    <span id="input-error-username" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                        ${kcSanitize(messagesPerField.get('username'))?no_esc}
                    </span>
                </#if>
            </div>

            <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" type="submit">
                    <span>${msg("omSendInstructions")}</span>
                    <span class="om-button__arrow" aria-hidden="true">→</span>
                </button>
                <a class="om-button om-button--secondary om-button--block" href="${url.loginUrl}">${msg("backToLogin")}</a>
            </div>
        </form>
    </#if>
</@layout.registrationLayout>
