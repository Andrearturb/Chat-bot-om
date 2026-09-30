<#import "footer.ftl" as loginFooter>
<#--
  Layout do tema gentil-om — mesma composição da página /login do Chat-bot O&M:
  área institucional (personagem + identidade) à esquerda e card de autenticação
  à direita. Mantém os scripts e seções do template base do Keycloak 26.
-->
<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html class="${properties.kcHtmlClass!}" lang="${lang}">

<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="robots" content="noindex, nofollow">
    <meta name="color-scheme" content="light">
    <meta name="theme-color" content="#07345e">
    <#if properties.meta?has_content>
        <#list properties.meta?split(' ') as meta>
            <meta name="${meta?split('==')[0]}" content="${meta?split('==')[1]}"/>
        </#list>
    </#if>
    <title>${msg("loginTitle",(realm.displayName!''))}</title>
    <link rel="icon" type="image/png" href="${url.resourcesPath}/img/favicon.png" />
    <link rel="preload" href="${url.resourcesPath}/fonts/manrope-latin.woff2" as="font" type="font/woff2" crossorigin>
    <#if properties.stylesCommon?has_content>
        <#list properties.stylesCommon?split(' ') as style>
            <link href="${url.resourcesCommonPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.styles?has_content>
        <#list properties.styles?split(' ') as style>
            <link href="${url.resourcesPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.scripts?has_content>
        <#list properties.scripts?split(' ') as script>
            <script src="${url.resourcesPath}/${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <script type="importmap">
        {
            "imports": {
                "rfc4648": "${url.resourcesCommonPath}/vendor/rfc4648/rfc4648.js"
            }
        }
    </script>
    <#if scripts??>
        <#list scripts as script>
            <script src="${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <script type="module">
        import { startSessionPolling } from "${url.resourcesPath}/js/authChecker.js";

        startSessionPolling(
            "${url.ssoLoginInOtherTabsUrl?no_esc}"
        );
    </script>
    <script type="module">
        document.addEventListener("click", (event) => {
            const link = event.target.closest("a[data-once-link]");

            if (!link) {
                return;
            }

            if (link.getAttribute("aria-disabled") === "true") {
                event.preventDefault();
                return;
            }

            const { disabledClass } = link.dataset;

            if (disabledClass) {
                link.classList.add(...disabledClass.trim().split(/\s+/));
            }

            link.setAttribute("role", "link");
            link.setAttribute("aria-disabled", "true");
        });
    </script>
    <#if authenticationSession??>
        <script type="module">
            import { checkAuthSession } from "${url.resourcesPath}/js/authChecker.js";

            checkAuthSession(
                "${authenticationSession.authSessionIdHash}"
            );
        </script>
    </#if>
</head>

<body class="${properties.kcBodyClass!} ${bodyClass}" data-page-id="login-${pageId}">
<#assign pageSubtitle><#nested "subtitle"></#assign>
<div class="om-shell ${properties.kcLoginClass!}">
    <span class="om-glow om-glow--blue" aria-hidden="true"></span>
    <span class="om-glow om-glow--yellow" aria-hidden="true"></span>

    <main class="om-layout">
        <section class="om-hero" aria-label="${msg('omAppName')}">
            <span class="om-hero__ring om-hero__ring--one" aria-hidden="true"></span>
            <span class="om-hero__ring om-hero__ring--two" aria-hidden="true"></span>
            <span class="om-hero__grid" aria-hidden="true"></span>

            <div class="om-wordmark" aria-label="Gentil Negócios">
                <strong>Gentil</strong>
                <strong>Negócios</strong>
                <small><i aria-hidden="true"></i>${msg("omDepartment")}</small>
            </div>

            <div class="om-hero__copy">
                <p class="om-eyebrow">Gentil Negócios<span class="om-eyebrow__area"><span class="om-eyebrow__dot" aria-hidden="true"></span>${msg("omDepartment")}</span></p>
                <h1 class="om-hero__title">Chat-bot <em>O&amp;M</em><b aria-hidden="true"></b></h1>
                <p class="om-hero__subtitle">${msg("omAppSubtitle")}</p>
            </div>

            <div class="om-hero__stage">
                <div class="om-hero__portrait">
                    <span class="om-hero__halo" aria-hidden="true"></span>
                    <img src="${url.resourcesPath}/img/gentileza.png" width="720" height="960"
                         alt="${msg('omMascotAlt')}" />
                    <p class="om-hero__speech">${msg("omHeroTagline")}</p>
                </div>
            </div>
        </section>

        <section class="om-panel">
            <div class="${properties.kcFormCardClass!}">
                <div class="om-card__brand">
                    <span class="om-card__avatar"><img src="${url.resourcesPath}/img/gentileza-avatar.png" alt="" width="44" height="44" /></span>
                    <span class="om-card__brand-copy">
                        <strong>${msg("omAppName")}</strong>
                        <small>${msg("omAppSubtitle")}</small>
                    </span>
                </div>

                <header class="om-card__header">
                    <#if displayRequiredFields>
                        <p class="om-required-note"><span class="required">*</span> ${msg("requiredFields")}</p>
                    </#if>
                    <h2 id="kc-page-title"><#nested "header"></h2>
                    <#if pageSubtitle?markup_string?trim?has_content>
                        <p class="om-card__subtitle">${pageSubtitle}</p>
                    </#if>
                    <#if auth?has_content && auth.showUsername() && !auth.showResetCredentials()>
                        <#nested "show-username">
                        <div id="kc-username" class="om-attempted-user">
                            <span class="om-attempted-user__avatar" aria-hidden="true"></span>
                            <label id="kc-attempted-username">${auth.attemptedUsername}</label>
                            <a id="reset-login" href="${url.loginRestartFlowUrl}" aria-label="${msg("restartLoginTooltip")}">
                                <i class="${properties.kcResetFlowIcon!}" aria-hidden="true"></i>
                                <span>${msg("omSwitchAccount")}</span>
                            </a>
                        </div>
                    </#if>
                </header>

                <div id="kc-content">
                    <div id="kc-content-wrapper">
                        <#-- Ações iniciadas pela aplicação não exibem avisos sobre a própria ação. -->
                        <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
                            <div class="${properties.kcAlertClass!} om-alert--${message.type}" role="<#if message.type = 'error'>alert<#else>status</#if>">
                                <span class="om-alert__icon" aria-hidden="true"></span>
                                <span class="${properties.kcAlertTitleClass!}">${kcSanitize(message.summary)?no_esc}</span>
                            </div>
                        </#if>

                        <#nested "form">

                        <#if auth?has_content && auth.showTryAnotherWayLink()>
                            <form id="kc-select-try-another-way-form" action="${url.loginAction}" method="post">
                                <div class="${properties.kcFormGroupClass!} om-try-another-way">
                                    <input type="hidden" name="tryAnotherWay" value="on"/>
                                    <a href="#" id="try-another-way"
                                       onclick="document.forms['kc-select-try-another-way-form'].requestSubmit();return false;">${msg("doTryAnotherWay")}</a>
                                </div>
                            </form>
                        </#if>

                        <#nested "socialProviders">

                        <#if displayInfo>
                            <div id="kc-info" class="${properties.kcSignUpClass!}">
                                <div id="kc-info-wrapper" class="${properties.kcInfoAreaWrapperClass!}">
                                    <#nested "info">
                                </div>
                            </div>
                        </#if>
                    </div>
                </div>

                <footer class="om-card__footer">
                    <span class="om-icon om-icon--lock" aria-hidden="true"></span>
                    <span>${msg("omExclusiveAccess")}</span>
                </footer>
                <@loginFooter.content/>
            </div>
        </section>
    </main>
</div>
</body>
</html>
</#macro>
