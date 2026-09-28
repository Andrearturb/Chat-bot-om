import mascot from "../../../assets/gentileza-indicadores.png";

function IconStore() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}
function IconEquip() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}
function IconDoc() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function HeroStatCard({ icon, label, value }) {
  return (
    <div className="assets-hero-stat">
      <span className="assets-hero-stat__icon">{icon}</span>
      <div className="assets-hero-stat__body">
        <span className="assets-hero-stat__label">{label}</span>
        <strong className="assets-hero-stat__value">
          {value ?? <span className="assets-hero-stat__loading" aria-label="Carregando" />}
        </strong>
      </div>
    </div>
  );
}

/* ── Hero component ─────────────────────────────────────────────────── */
export function AssetsHero({ summary, loading }) {
  const storesVal = loading && !summary ? null : summary?.stores_count ?? 0;
  const equipVal  = loading && !summary ? null : summary?.equipment_count ?? 0;
  const docsVal   = loading && !summary ? null : summary?.documents_count ?? 0;

  return (
    <header className="assets-hero" aria-labelledby="assets-title">
      {/* Left: mascot panel */}
      <div className="assets-hero__left">
        <div className="assets-hero__mascot-panel">
          <div className="assets-hero__ring assets-hero__ring--one" aria-hidden="true" />
          <div className="assets-hero__ring assets-hero__ring--two" aria-hidden="true" />
          <img src={mascot} alt="" className="assets-hero__mascot-img" />
          <div className="assets-hero__speech">
            Aqui você encontra os equipamentos
            <br />e documentos de cada loja
            <br />em um só lugar.
          </div>
        </div>

        {/* Copy */}
        <div className="assets-hero__copy">
          <p className="assets-hero__eyebrow">Gestão de ativos</p>
          <h1 id="assets-title">
            <span>Central de</span>
            <span>Ativos</span>
          </h1>
          <h2>Informações técnicas que apoiam a manutenção.</h2>
          <p>
            Consulte equipamentos e documentos das lojas de forma simples,
            organizada e centralizada.
          </p>
        </div>
      </div>

      {/* Right: stat cards */}
      <div className="assets-hero__right">
        <div className="assets-hero__bars" aria-hidden="true">
          <span /><span /><span />
        </div>
        <div className="assets-hero__stats">
          <HeroStatCard
            icon={<IconStore />}
            label="Lojas cadastradas"
            value={storesVal !== null ? `${storesVal} ${storesVal === 1 ? "loja" : "lojas"}` : null}
          />
          <HeroStatCard
            icon={<IconEquip />}
            label="Equipamentos"
            value={equipVal !== null ? `${equipVal} ${equipVal === 1 ? "ativo" : "ativos"}` : null}
          />
          <HeroStatCard
            icon={<IconDoc />}
            label="Documentos"
            value={docsVal !== null ? `${docsVal} ${docsVal === 1 ? "documento" : "documentos"}` : null}
          />
        </div>
      </div>
    </header>
  );
}

