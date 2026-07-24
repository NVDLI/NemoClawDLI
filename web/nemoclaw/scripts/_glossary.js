// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Glossary helpers: ranked local webSearch plus single-term instantAnswer.

// Ranked local search over the vendored NVIDIA materials index.
// Runs keyless from static pages; instantAnswer is the narrow single-term path.
let _glossaryIndexP = null;
function _loadGlossaryIndex() {
  if (!_glossaryIndexP) {
    _glossaryIndexP = fetch("assets/glossary_index.json")
      .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(d => Array.isArray(d.terms) ? d.terms : [])
      .catch(e => { _glossaryIndexP = null; throw e; });   // let a later call retry
  }
  return _glossaryIndexP;
}
// Materials catalog combines cached glossary entries and on-demand sources.
let _materialsCatalogP = null;
function _loadMaterialsCatalog() {
  if (!_materialsCatalogP) {
    _materialsCatalogP = fetch("assets/materials_index.json")
      .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(d => Array.isArray(d.entries) ? d.entries : [])
      .catch(e => { _materialsCatalogP = null; throw e; });   // let a later call retry
  }
  return _materialsCatalogP;
}
// Rank identity hits first; blurb hits refine but cannot create a match alone.
function _scoreGlossaryTerm(term, query) {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const name  = (term.term  || "").toLowerCase();
  const blurb = (term.blurb || "").toLowerCase();
  const tags  = (term.tags  || []).map(t => String(t).toLowerCase());
  let identity = 0, blurb_score = 0;
  if (name === q) identity += 100;
  else if (name.includes(q) || q.includes(name)) identity += 40;
  for (const tok of q.split(/[^a-z0-9]+/).filter(Boolean)) {
    if (name.includes(tok))               identity += 12;
    if (tags.some(t => t.includes(tok)))  identity += 6;
    if (blurb.includes(tok))              blurb_score += 3;
  }
  return identity > 0 ? identity + blurb_score : 0;
}
// Glossary explorer reuses the real ranking and loaders.
export { _scoreGlossaryTerm as glossaryScore, _loadGlossaryIndex as loadGlossaryIndex,
         _loadMaterialsCatalog as loadMaterialsCatalog };

export async function webSearch(query, { maxResults = 5 } = {}) {
  /* @doc <code>helpers.webSearch(q, {maxResults})</code> ::
       Key-less, ranked search over the course's materials catalog
       (<code>assets/materials_index.json</code>): the cached NVIDIA glossary terms
       <em>plus</em> the on-demand materials (papers, blogs) vendored from the web. Matches the
       query against each entry's name, tags, and blurb; runs from any page with no key and no
       lab. Each result carries a <code>tier</code> (<code>cached</code> = full text shipped;
       <code>on_demand</code> = follow <code>href</code> for the source). Returns <code>{
       results: [{title, body, href, tier, kind}], count, unreachable }</code>.
  */
  try {
    const entries = await _loadMaterialsCatalog();
    const results = entries
      .map(t => ({ t, s: _scoreGlossaryTerm(t, query) }))
      .filter(x => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, maxResults)
      .map(x => ({ title: x.t.term, body: x.t.blurb || "", href: x.t.url, tier: x.t.tier, kind: x.t.kind }));
    return { unreachable: false, source: "materials", query, results, count: results.length };
  } catch (e) {
    return { unreachable: true, source: "materials", error: e.message, query, results: [], count: 0 };
  }
}

// Single-term answer path; free-form questions should use webSearch.
export async function instantAnswer(query) {
  /* @doc <code>helpers.instantAnswer(q)</code> ::
       A single NVIDIA glossary definition for a query that names a term (e.g.
       <code>retrieval-augmented generation</code>, <code>deep agents</code>). Same return shape
       as <code>webSearch</code>, but it returns one curated card only for a close term match
       and nothing for a free-form question. The narrow, entity-keyed counterpart to
       <code>webSearch</code>.
  */
  try {
    const terms = await _loadGlossaryIndex();
    const q = query.trim().toLowerCase();
    // Accept only near-exact names; choose the closest length match.
    const hit = terms
      .map(t => ({ t, name: (t.term || "").toLowerCase() }))
      .filter(x => x.name && (x.name === q || x.name.includes(q) || q.includes(x.name)))
      .sort((a, b) => Math.abs(a.name.length - q.length) - Math.abs(b.name.length - q.length))[0];
    if (!hit) return { unreachable: false, source: "glossary-term", query, results: [], count: 0 };
    const results = [{ title: hit.t.term, body: hit.t.blurb || "", href: hit.t.url }];
    return { unreachable: false, source: "glossary-term", query, results, count: results.length };
  } catch (e) {
    return { unreachable: true, source: "glossary-term", error: e.message, query, results: [], count: 0 };
  }
}
