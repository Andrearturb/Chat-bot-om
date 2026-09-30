<#import "template.ftl" as layout>
<#import "password-commons.ftl" as passwordCommons>
<#-- Primeiro acesso com senha temporária ou redefinição solicitada pelo administrador. -->
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('password','password-confirm'); section>
    <#if section = "header">
        ${msg("updatePasswordTitle")}
    <#elseif section = "subtitle">
        ${msg("omUpdatePasswordSubtitle")}
    <#elseif section = "form">
        <form id="kc-passwd-update-form" class="${properties.kcFormClass!}" onsubmit="submitPassword.disabled = true; return true;" action="${url.loginAction}" method="post" novalidate>
            <div class="${properties.kcFormGroupClass!}">
                <label for="password-new" class="${properties.kcLabelClass!}">${msg("passwordNew")}</label>
                <div class="${properties.kcInputGroup!} om-input-shell" dir="ltr">
                    <span class="om-icon om-icon--lock om-input-shell__icon" aria-hidden="true"></span>
                    <input type="password" id="password-new" name="password-new" class="${properties.kcInputClass!}"
                           autofocus autocomplete="new-password"
                           aria-invalid="<#if messagesPerField.existsError('password','password-confirm')>true</#if>"
                           <#if messagesPerField.existsError('password')>aria-describedby="input-error-password"</#if>
                    />
                    <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg('showPassword')}"
                            aria-controls="password-new" data-password-toggle
                            data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                            data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                        <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                    </button>
                </div>
                <#if messagesPerField.existsError('password')>
                    <span id="input-error-password" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                        ${kcSanitize(messagesPerField.get('password'))?no_esc}
                    </span>
                </#if>
            </div>

            <div class="${properties.kcFormGroupClass!}">
                <label for="password-confirm" class="${properties.kcLabelClass!}">${msg("passwordConfirm")}</label>
                <div class="${properties.kcInputGroup!} om-input-shell" dir="ltr">
                    <span class="om-icon om-icon--lock om-input-shell__icon" aria-hidden="true"></span>
                    <input type="password" id="password-confirm" name="password-confirm" class="${properties.kcInputClass!}"
                           autocomplete="new-password"
                           aria-invalid="<#if messagesPerField.existsError('password-confirm')>true</#if>"
                           <#if messagesPerField.existsError('password-confirm')>aria-describedby="input-error-password-confirm"</#if>
                    />
                    <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg('showPassword')}"
                            aria-controls="password-confirm" data-password-toggle
                            data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                            data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                        <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                    </button>
                </div>
                <#if messagesPerField.existsError('password-confirm')>
                    <span id="input-error-password-confirm" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                        ${kcSanitize(messagesPerField.get('password-confirm'))?no_esc}
                    </span>
                </#if>
            </div>

            <@passwordCommons.logoutOtherSessions/>

            <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                <#if isAppInitiatedAction??>
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" name="submitPassword" type="submit">${msg("doSubmit")}</button>
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonDefaultClass!} ${properties.kcButtonBlockClass!}" type="submit" name="cancel-aia" value="true">${msg("doCancel")}</button>
                <#else>
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" name="submitPassword" type="submit">
                        <span>${msg("doSubmit")}</span>
                        <span class="om-button__arrow" aria-hidden="true">→</span>
                    </button>
                </#if>
            </div>
        </form>
        <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
    </#if>
</@layout.registrationLayout>
