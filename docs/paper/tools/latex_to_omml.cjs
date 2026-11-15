// Convert the LaTeX subset used in docs/paper equations into docx-js Math components (native Word OMML).
// Supported: \frac \tfrac \sqrt \left( \right) \left[ \right] \left| \right| _ ^ \sum \int \operatorname(*) \hat
// \mathcal \mathrm \exp \ln \arctan Greek letters, \partial, \times, \ge, spacing commands.
const {
  MathRun, MathFraction, MathRadical, MathRoundBrackets, MathSquareBrackets, MathSubScript, MathSuperScript, MathSubSuperScript,
  MathSum, MathIntegral, MathLimitLower,
} = require("docx");

const GREEK = { tau: "τ", delta: "δ", theta: "θ", rho: "ρ", partial: "∂", times: "×", ge: "≥", le: "≤", cdot: "·", mathcal_R: "ℛ" };
const FUNCS = new Set(["exp", "ln", "arctan", "median"]);

function tokenize(s) {
  const out = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "\\") {
      let j = i + 1;
      if (/[a-zA-Z]/.test(s[j])) { while (j < s.length && /[a-zA-Z]/.test(s[j])) j++; }
      else j++;
      let name = s.slice(i + 1, j);
      if (s[j] === "*") { name += "*"; j++; }
      out.push({ t: "cmd", v: name });
      i = j;
    } else if (c === " ") { i++; }
    else { out.push({ t: "ch", v: c }); i++; }
  }
  return out;
}

function parse(tokens) {
  let pos = 0;
  const peek = () => tokens[pos];
  const next = () => tokens[pos++];

  function group() { // after '{'
    const items = sequence((t) => t.t === "ch" && t.v === "}");
    next(); // consume '}'
    return items;
  }
  function arg() {
    const t = next();
    if (t && t.t === "ch" && t.v === "{") return group();
    return t ? atomFrom(t) : [];
  }
  function textOf(items) { return items.map((x) => (x.__text ?? "")).join(""); }
  function run(text) { const r = new MathRun(text); r.__text = text; return r; }

  function atomFrom(t) {
    if (t.t === "ch") return [run(t.v)];
    const v = t.v;
    if (v === "frac" || v === "tfrac") { const n = arg(); const d = arg(); return [new MathFraction({ numerator: n, denominator: d })]; }
    if (v === "sqrt") return [new MathRadical({ children: arg() })];
    if (v === "hat") { const a = arg(); return [run(textOf(a) + "̂")]; }
    if (v === "mathcal") { const a = arg(); return [run(textOf(a) === "R" ? "ℛ" : textOf(a))]; }
    if (v === "mathrm") { const a = arg(); return [run(textOf(a))]; }
    if (v === "operatorname") { const a = arg(); return [run(textOf(a))]; }
    if (v === "operatorname*") {
      const name = textOf(arg());
      if (peek() && peek().t === "ch" && peek().v === "_") { next(); return [new MathLimitLower({ children: [run(name)], limit: arg() })]; }
      return [run(name)];
    }
    if (v === "left") {
      const open = next();
      const opener = open.t === "cmd" ? open.v : open.v;
      const inner = sequence((x) => x.t === "cmd" && x.v === "right");
      next(); next(); // \right and its delimiter
      if (opener === "(") return [new MathRoundBrackets({ children: inner })];
      if (opener === "[") return [new MathSquareBrackets({ children: inner })];
      return [run("|"), ...inner, run("|")];
    }
    if (v === "sum" || v === "int") {
      let sub = [], sup = [];
      while (peek() && peek().t === "ch" && (peek().v === "_" || peek().v === "^")) {
        const k = next().v;
        if (k === "_") sub = arg(); else sup = arg();
      }
      const body = sequence((x) => (x.t === "ch" && (x.v === "}" || x.v === ",")) || (x.t === "cmd" && (x.v === "qquad" || x.v === "right")));
      const Cls = v === "sum" ? MathSum : MathIntegral;
      return [new Cls({ children: body, subScript: sub.length ? sub : undefined, superScript: sup.length ? sup : undefined })];
    }
    if (FUNCS.has(v)) return [run(v)];
    if (GREEK[v]) return [run(GREEK[v])];
    if (v === "," || v === "quad") return [run(" ")];
    if (v === "qquad") return [run("    ")];
    if (v === "!" || v === ";") return [];
    if (v === "|") return [run("|")];
    return [run(v)];
  }

  function sequence(stop) {
    const items = [];
    while (pos < tokens.length && !stop(peek())) {
      const t = next();
      if (t.t === "ch" && (t.v === "_" || t.v === "^")) {
        const base = items.pop() ?? run("");
        const first = arg();
        let sub = t.v === "_" ? first : null, sup = t.v === "^" ? first : null;
        if (peek() && peek().t === "ch" && (peek().v === "_" || peek().v === "^") && peek().v !== t.v) {
          const k = next().v; const second = arg();
          if (k === "_") sub = second; else sup = second;
        }
        if (sub && sup) items.push(new MathSubSuperScript({ children: [base], subScript: sub, superScript: sup }));
        else if (sub) items.push(new MathSubScript({ children: [base], subScript: sub }));
        else items.push(new MathSuperScript({ children: [base], superScript: sup }));
      } else if (t.t === "ch" && t.v === "{") {
        items.push(...group());
      } else {
        items.push(...atomFrom(t));
      }
    }
    return items;
  }
  return sequence(() => false);
}

/** Single-letter runs are split so a script attaches to the right base (e.g. d_{k} -> base d). */
function latexToMath(latex) {
  return parse(tokenize(latex.replace(/\\tag\{[^}]*\}/, "")));
}

module.exports = { latexToMath };
