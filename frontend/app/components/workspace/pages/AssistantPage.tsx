export default function AssistantPage() {
  return <div className="page-section">
    <div className="page-intro"><div><p className="eyebrow">AI-ASSISTED SCIENTIFIC WORKFLOW</p><h1>Research assistant</h1><p>A place for evidence-aware interpretation as the TerraLuna analysis services evolve.</p></div></div>
    <section className="assistant-surface">
      <div className="assistant-banner"><span className="assistant-mark">✧</span><div><span className="future-badge">BACKEND INTEGRATION · NOT CONNECTED</span><h2>Bring your planetary research questions here.</h2><p>The current API does not expose an AI assistant endpoint, so this interface will not generate or imply scientific conclusions.</p></div></div>
      <div className="assistant-capabilities">
        <article><span>01</span><h3>Grounded in provenance</h3><p>Future responses can cite the terrain summaries, source manifests, and limitations available in this workspace.</p></article>
        <article><span>02</span><h3>Clear about uncertainty</h3><p>Future interpretations should distinguish processed observations, previews, and unavailable evidence.</p></article>
        <article><span>03</span><h3>Researcher controlled</h3><p>AI support can help explore findings without replacing scientific judgment or the underlying data.</p></article>
      </div>
      <div className="assistant-composer"><label htmlFor="assistant-prompt">Research prompt</label><textarea id="assistant-prompt" disabled placeholder="Assistant service will be available when a backend endpoint is implemented." /><div><span>Prompts are not sent or stored.</span><button className="button button-disabled" type="button" disabled>Assistant unavailable</button></div></div>
    </section>
  </div>;
}
