<#import "template.ftl" as layout>
<#-- Exibida apenas quando o logout chega sem id_token_hint (ex.: sessão antiga). -->
<@layout.registrationLayout; section>
    <#if section = "header">
        ${msg("logoutConfirmTitle")}
    <#elseif section = "subtitle">
        ${msg("logoutConfirmHeader")}
    <#elseif section = "form">
        <div id="kc-logout-confirm" class="om-stack">
            <form class="om-form" action="${url.logoutConfirmAction}" onsubmit="confirmLogout.disabled = true; return true;" method="POST">
                <input type="hidden" name="session_code" value="${logoutConfirm.code}">
                <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                            name="confirmLogout" id="kc-logout" type="submit">${msg("doLogout")}</button>
                    <#if !logoutConfirm.skipLink && (client.baseUrl)?has_content>
                        <a class="om-button om-button--secondary om-button--block" href="${client.baseUrl}">${msg("backToApplication")}</a>
                    </#if>
                </div>
            </form>
        </div>
    </#if>
</@layout.registrationLayout>
