interface OSPlaceholderProps {
  name: string;
  purpose: string;
}

export function OSPlaceholder({ name, purpose }: OSPlaceholderProps) {
  return (
    <section className="os-placeholder" aria-label={`${name} placeholder`}>
      <div className="panel brackets os-placeholder-card">
        <div className="panel-h">
          <span className="blip"></span>
          <span className="t">{name.toUpperCase()}</span>
          <span className="badge IDLE"><span className="bd"></span>PLANNED</span>
        </div>
        <div className="os-placeholder-body">
          <span className="os-placeholder-mark">◇</span>
          <p className="os-placeholder-kicker">FUTURE OPERATING SYSTEM</p>
          <h1>{name}</h1>
          <p>{purpose}</p>
          <div className="os-placeholder-state">
            <strong>PLACEHOLDER ONLY</strong>
            <span>No agents, data connections, automations, or external controls are active.</span>
          </div>
          <span className="badge IDLE"><span className="bd"></span>BUILD SCHEDULED LATER</span>
        </div>
      </div>
    </section>
  );
}
