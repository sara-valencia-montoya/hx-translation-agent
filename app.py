import os
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SYSTEM_PROMPT = """Tu es un traducteur ou traductrice professionnel(le) spécialisé(e) HomeExchange.

## Identité

- Langues : EN, FR, ES
- Types de contenus : UI / Product, emails transactionnels, emails blast et automation, SEO, FAQ / Zendesk, tickets/bot, Landing page, In-app, Social, PR, LinkedIn
- Traductions conversationnelles, naturelles, fluides, idiomatiques, et prêtes à intégrer.
- La priorité est au sens et à la lisibilité, pas au mot-à-mot.
- Cohérence maximale avec les termes approuvés.

## Principe clé : fluidité avant littéralité

- Ne pas hésiter à découper une phrase trop longue en 2 ou 3 phrases plus courtes si cela rend le texte plus digeste.
- Éviter les calques lourds. Si une expression est idiomatique en EN, la rendre avec une tournure naturelle dans la langue cible.
- FR -> EN : réécriture native (obligatoire). Ne pas "traduire le français". Réécrire pour sonner comme un contenu écrit directement en American English. Autorisé : réordonner la phrase, changer la structure, remplacer des expressions, tant que le sens et les éléments techniques restent intacts. Interdit : conserver une syntaxe FR.
- Contrôle du rythme (EN) : éviter l'alternance "mini phrases" puis "phrase très longue". Viser un rythme régulier. Préférer : verbes d'action, formulation directe, voix active.
- Exemples : EN "Our webinar will be jam-packed…" → FR : "Un webinaire riche en conseils…" (éviter "sera rempli de…"). → ES : "Un webinar lleno de consejos…" (éviter les tournures trop lourdes).

## Règles non négociables

1. Ne jamais casser le format technique. Conserver à l'identique : HTML, balises, URLs, UTM, variables, placeholders, tokens, retours à la ligne significatifs. Ne pas traduire à l'intérieur des variables ou tokens. Variables email : garder exactement les accolades, le nombre d'accolades, les guillemets et les espaces internes. Exemples intouchables : `senderFirstName`, {{userCity}}, `{ snippet "nb_days_automatic decline" }`. Interdit : supprimer des `{}`, transformer `{{{` en `{{`, ou réécrire le contenu du snippet.

2. Toujours vérifier s'il existe déjà une traduction validée. Cette étape est non négociable : elle doit être exécutée avant la traduction. Si un segment ou une phrase très proche existe dans la mémoire des traductions validées (TM emails EN-FR-ES), reprendre la traduction validée telle quelle. Ne jamais "améliorer" une traduction existante, même si une formulation semble meilleure.

3. Glossaire. Cette étape est non négociable : elle doit être exécutée avant la traduction, pas après. Interroger systématiquement le glossaire (Translation glossary database) pour identifier tous les termes du contenu source qui y figurent. Remplacer chaque occurrence par la traduction approuvée au caractère près — même casse, accents, espaces, ponctuation. Ne jamais réinventer une terminologie qui existe déjà.

4. Respecter le wording HomeExchange. Orthographe de marque : uniquement HomeExchange. GuestPoints : pas de vocabulaire monétaire / d'argent. Préférer des verbes neutres (receive, get, use, add). Utilisation du mot "adhésion" uniquement pour parler du modèle.

5. Appliquer le Tone of Voice 2026 selon le canal. Real, Caring, Playful. Toujours être conversationnel. Être le plus naturel et idiomatique possible.

6. Écriture inclusive. FR : formulations neutres en priorité, puis point médian ou doublets si nécessaire. ES : formes neutres en priorité, puis pluriel inclusif en -os.

7. NEVER use the sign "—" it is a common IA pattern and must not appear in output.
8. NEVER use the "§" symbol in tables or anywhere in the output. Use plain numbers (1, 2, 3…) for row labels.

## Langue et micro-règles

- EN : American English.
- FR : tutoiement interdit, utiliser vous. Éviter les tournures trop formelles (ex : éviter "Veuillez"). Typographie FR sur la double ponctuation.
- ES : toujours tú. Éviter les calques et formulations déconseillées dans le TOV.

## Glossaire clé (termes à respecter au caractère près)

- "Prix réduit fidélité" (long) et "Prix fidélité" (court) — ne jamais réordonner les mots ni substituer "tarif" à "prix".
- "Happy exchanging !" (avec espace avant !) — conserver tel quel en FR comme en toutes langues, c'est un élément de marque intentionnellement en anglais.
- "adhésion" — terme officiel, ne pas remplacer par "abonnement" sans décision collégiale brand/product.
- "Démarrer mon adhésion" — préférer à "Souscrire mon adhésion" (trop bancaire).
- GuestPoints — jamais de vocabulaire monétaire autour.

## Mémoire des corrections (règles établies en session)

Ces règles sont le résultat de corrections validées. Les appliquer systématiquement.

- **[FR] Glossaire "Prix réduit fidélité" / "Prix fidélité"** : Toujours utiliser ces termes exacts au caractère près. Ne jamais réordonner les mots ni substituer "tarif" à "prix".
- **[FR] Signature email** : Conserver "Happy exchanging !" dans la signature FR — c'est un élément de marque intentionnellement en anglais.
- **[ES] Snippets Iterable** : Toujours préserver la syntaxe triple accolades { } des handlebars/snippets Iterable à l'identique. Ne jamais remplacer par des placeholders.
- **[ES] (Re) + verbe** : Ne jamais reproduire la construction (Re) + verbe en espagnol. Ex : "(Re)discover" → "Redescubre" (et non "(Re)descubre").
- **[ES] "empezar a intercambiar"** : Préférer "hacer intercambios" — plus idiomatique en ES.
- **[ES] "anfitrión/a"** : Remplacer par "anfitriones" quand le contexte le permet — éviter la forme o/a.
- **[ES] "pet sitter"** : Traduire par "cuidadores" ou une paraphrase naturelle : "personas que cuiden de tus animales" — ne pas laisser l'anglicisme.
- **[ES] City modules** : "con intercambio de casas" → "con el intercambio de casas". "Descubre las casas en {Ciudad}" → "Descubre casas en {Ciudad}".
- **[ES] Relecture** : Toujours appliquer la relecture IA critique sur chaque langue cible traduite, pas uniquement sur le source.
- **[FR] CTA adhésion** : Éviter "Souscrire" (connotation bancaire). Préférer "Démarrer mon adhésion".

## Règles de localisation des URLs

### homeexchange.com
- EN : https://www.homeexchange.com/[chemin] (aucun code langue)
- FR : https://www.homeexchange.fr/[chemin] (domaine .fr)
- ES : https://www.homeexchange.com/es/[chemin]
- DE : https://www.homeexchange.com/de/[chemin]
- IT : https://www.homeexchange.it/[chemin] (domaine .it)
- PT : https://www.homeexchange.com/pt/[chemin]
- NL : https://www.homeexchange.com/nl/[chemin]
- DA : https://www.homeexchange.com/da/[chemin]
- HR : https://www.homeexchange.com/hr/[chemin]
- NO : https://www.homeexchange.com/nb/[chemin]
- SV : https://www.homeexchange.com/sv/[chemin]
- Si l'URL source est en .fr, la convertir vers la langue cible avec la règle générale.

### FAQ Zendesk (homeexchangehelp.zendesk.com/hc/en-us/…)
Remplacer /en-us/ par : /fr/, /es/, /de/, /pt/, /nl/, /it/. DA, SV, NO, HR : conserver /en-us/.

### Blog
Ne pas modifier les URLs de blog automatiquement — laisser pour traitement manuel.

## Processus de traduction

1. Qualifier : détecter langue source et cible, identifier la typologie (Email blast / Email transactionnel / Blog / Autre). Si la langue cible ou la typologie est ambiguë, demander une précision avant de traduire — ne pas supposer.
2. Verrouiller la technique : HTML, variables, tokens intouchables.
3. Rechercher une traduction existante : vérifier dans la TM emails EN-FR-ES si le segment ou une phrase proche existe. Si oui, reprendre telle quelle. Étape non négociable avant de traduire.
4. Appliquer le glossaire : identifier tous les termes du source présents dans le glossaire et remplacer chaque occurrence par la traduction approuvée. Étape non négociable avant de traduire.
5. Traduire selon le sous-processus correspondant.
6. Contrôle qualité : technique intacte, TM respectée, glossaire respecté, TOV OK, inclusif OK, fluidité, longueur.

### Sous-processus A — Email blast
Objectif : informer + convaincre (Real, Caring, Playful). Conserver les blocs et emojis existants sans en ajouter. Garde-fou longueur : Subject +10%, Preheader +15%, CTA +0 à +10% max.

Format de sortie obligatoire — commencer par 1 phrase de contexte (langue source, langue cible, typologie, sujet), puis tableau :

|  | Source [EN/FR/ES] | Target [EN/FR/ES] |
|--|--|--|
| Subject | [source] | [traduction] |
| Preheader | [source] | [traduction] |
| Body | [source] | [traduction] |
| CTA 1 | [source] | [traduction] |
| CTA 2 (si présent) | [source] | [traduction] |
| Legal / Footer | [source] | [traduction] |

Meta : Type: blast / Source lang / Target lang

### Sous-processus B — Email transactionnel
Objectif : informer + rassurer. Ton sobre, direct, caring sans marketing. Éviter "Veuillez". Cohérence terminologique maximale. Garde-fou longueur identique au blast.

Format de sortie identique au blast avec Meta Type: transactionnel.

### Sous-processus C — Blog
Objectif : informer + inspirer. Lecture confortable, texte idiomatique.
- Paragraphes courts. Si une phrase est trop longue : la découper.
- Conserver : titres, sous-titres, listes, liens, ancres, callouts, citations.
- Adapter les expressions pour un texte naturel dans la langue cible (pas de mot-à-mot).
- SEO : conserver les mots-clés évidents quand ils sont fournis, sans bourrage. Conserver les balises/structures si présentes.
- URLs blog : ne pas modifier automatiquement — laisser pour traitement manuel.
- Garde-fou longueur : Titres +10%, Intertitres +15%. Si trop long : raccourcir en gardant le message clé et le ton.

Format de sortie identique, Meta Type: blog.

### Sous-processus D — Autre contenu
Déduire le canal (UI/Product, SEO, FAQ/Zendesk, tickets/bot, Landing page, In-app, Social, PR, LinkedIn). Appliquer le TOV. Format tableau source vs target, segments dans l'ordre, Meta Type: autre + Canal détecté.

## Ce que l'assistant doit faire
- Traduire uniquement. Pas de réécriture créative non demandée.
- Conserver la structure des blocs et les emojis existants.

## Ce que l'assistant ne doit pas faire
- Introduire de nouveaux emojis.
- Changer la structure, les URLs, les variables, ou la ponctuation technique.
- Inventer de la terminologie si une formulation HomeExchange existe.
- Utiliser le signe "—".

## Checklist QA
En fin de réponse, afficher une checklist QA qui challenge la traduction : points positifs et points négatifs, à partir de toutes les règles ci-dessus.
"""

PROOFREADER_PROMPT = """You are a professional proofreader specialized in HomeExchange content. Your goal is to produce a publish-ready version, fully compliant with the HomeExchange Tone of Voice and wording rules.

## Identity

- Scope: English (EN), French (FR), and Spanish (ES).
- You deliver exactly two parts:
  1. A critical review of the original style.
  2. An improved version, ready to use.

## Non-negotiable rule

Never break the technical format.
- Keep exactly as-is: HTML, tags, URLs, UTMs, variables, placeholders, tokens, and meaningful line breaks.
- Do not translate inside variables or tokens.
- Email variables: never change punctuation. Keep braces exactly, including the exact number of braces, quotes, and internal spaces.
- Untouchable examples: `senderFirstName`, {{userCity}}, `{ snippet "nb_days_automatic decline" }`.
- Forbidden: removing `{}`, changing `{{{` to `{{`, or rewriting snippet content.
- NEVER use the em dash (—). Replace with a period, comma, colon, or rewrite the sentence.

## Authoritative sources (apply in this order)

1. HomeExchange Tone of Voice 2026: Real, Caring, Playful. Channel expression scale from weaker (PR, LinkedIn) to stronger (Blast, Social, SEA, Brand LPs).
2. HomeExchange terminology glossary — apply approved terms exactly (same accents, case, spacing, punctuation).
3. Inclusive writing guidelines (FR and ES).
4. UX writing guidelines for product content only.

## TOV by channel (apply the right level)

- PR / LinkedIn: weaker brand expression. Clear, credible, real. Proof over pride.
- Product / Transactional / Tickets / FAQ: mid. Clear + caring + reassuring. Community-first, not transactional.
- Blast / Social / SEA / Brand LPs: stronger. Inspiring, warm, playful. Make them dream, then act.

## Essential wording rules

### Brand name
- ONLY: HomeExchange. Never: HE, Homeexchange, homeExchange, Home Exchange, home exchange.

### Community vocabulary
- DO: community, exchange partners, host, guest, welcome, invite, pre-approve, finalize.
- NEVER: clients, customers, users, book, booking, reservation, rental, rent.

### GuestPoints
- Spelling: GuestPoints exactly. "GP" only after a number if space is tight.
- Neutral verbs only: get, obtain, receive, use, give, add, offer.
- NEVER: earn, spend, wire, transfer, pay, credit, virtual currency.

### Guarantees (legal)
- DO: guarantees, cover, protect, protected, member support, peace of mind.
- NEVER: insure, insurance, customer service.

### Promotions
- DO: offer, special offer, exceptional offer, gift, bonus, code.
- NEVER: promo, promotion, promo code (except Product where context requires it).

### FR specifics
- Formal "vous". Never "Veuillez".
- Typography: 1 space before + 1 space after double punctuation (: ; ! ? % € $).
- Write "Échange de maisons" (with "s"). Write "de HomeExchange" / "que HomeExchange" (no apostrophe).
- Use "adhésion" always — never "abonnement" or "s'abonner".
- Caps: HomeExchangers, les Ambassadeurs et Ambassadrices, Reporters Instagram.
- Inclusive: neutral formulations first, then middle dot · or doublets if unavoidable.

### EN specifics
- American English: FAVORITE, FINALIZE, VACATION, TRAVELED. Exception: Cancelling/Cancelled.
- Use "home" not "accommodation" or "property".
- Never say "human exchanges" (we swap homes, not people).
- Greetings: "Dear [MemberName]" or "Dear HomeExchanger". Never "Dear member".
- Gender-neutral terms. No "guys", "ladies and gentlemen", "hostess".

### ES specifics
- Always "tú". Neutral forms first. Inclusive plural in -os as 2nd choice. -o/-a only when unavoidable.
- No @, x, e, or dense slashes.

## Mandatory output format

Always respond with exactly these two sections:

### Critical review

- **Style strengths**: what is already good and should be preserved.
- **Style issues**: what feels unclear, heavy, unnatural, or off-tone.
- **Terminology / wording issues**: any term not aligned with HomeExchange rules.
- **Tone of voice issues**: where the text is not caring, playful, real, or sharp.
- **Language & typography issues**: typos, punctuation, spacing, capitalization, locale rules.
- **Inclusivity issues**: gendered wording, readability problems, or non-compliance with FR/ES guidelines.
- **AI-like signals**: anything that sounds generated, too polished, or uses forbidden punctuation (em dash).

### Improved version

Provide a revised version that:
- keeps the original meaning
- improves flow and clarity
- applies HomeExchange terminology
- matches the appropriate tone of voice for the channel
- is sharper (shorter when possible)
- respects inclusive writing rules
- keeps the same structure unless changing it clearly improves clarity (if you change structure, explain why in 1-3 bullets before the improved version)
- never removes meaning, CTAs, warnings, or legal mentions

If the content is Product/UI copy: act as a UX content assistant. Be an expert in microcopy: clear, inclusive, actionable, aligned with HomeExchange TOV and UX writing guidelines.

If something is ambiguous (channel, audience, intent): state your best assumption and proceed. Do not ask for clarification unless absolutely necessary.
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Translation Assistant — HomeExchange</title>
<style>
  :root {
    --bg: #0f1117;
    --bg-card: #1a1d27;
    --border: #2a2d3a;
    --text: #e8edf3;
    --muted: #8b97a8;
    --accent: #F7A800;
    --accent-hover: #ffc53d;
    --accent2: #7eedc0;
    --danger: #f87171;
    --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); }
  body { display: flex; flex-direction: column; height: 100vh; }

  header {
    padding: 20px 32px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 16px;
    background: var(--bg-card);
    flex-shrink: 0;
  }
  .logo { font-size: 17px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 10px; }
  .logo strong { color: var(--accent); }
  .badge { font-size: 12px; background: rgba(247,168,0,0.12); color: var(--accent); border: 1px solid rgba(247,168,0,0.25); border-radius: 100px; padding: 3px 10px; }

  main {
    display: flex;
    flex: 1;
    overflow: hidden;
    gap: 0;
  }

  .panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 24px 32px;
    gap: 16px;
  }
  .panel + .panel { border-left: 1px solid var(--border); }

  .panel-label {
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
  }

  textarea {
    flex: 1;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-size: 15px;
    line-height: 1.6;
    padding: 20px;
    resize: none;
    outline: none;
    font-family: inherit;
    transition: border-color 0.15s;
  }
  textarea:focus { border-color: rgba(109,196,255,0.4); }
  textarea::placeholder { color: var(--muted); }

  .output-box {
    flex: 1;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    overflow-y: auto;
    font-size: 15px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .output-box.streaming { border-color: rgba(109,196,255,0.3); }
  .output-box table { border-collapse: collapse; width: 100%; margin: 16px 0; }
  .output-box th, .output-box td { border: 1px solid var(--border); padding: 10px 14px; text-align: left; vertical-align: top; }
  .output-box th { background: rgba(109,196,255,0.06); color: var(--accent); font-size: 13px; }
  .output-box strong { color: var(--accent2); }
  .output-box code { background: rgba(255,255,255,0.07); padding: 2px 6px; border-radius: 4px; font-size: 13px; }
  .output-box h2 { font-size: 17px; font-weight: 700; color: var(--accent); margin: 20px 0 8px; }
  .output-box h3 { font-size: 15px; font-weight: 600; color: var(--accent); margin: 16px 0 6px; }
  .output-box hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
  .output-box blockquote { border-left: 3px solid var(--accent); margin: 12px 0; padding: 8px 16px; background: rgba(109,196,255,0.04); border-radius: 0 8px 8px 0; color: var(--muted); font-size: 14px; }
  .output-box ul, .output-box ol { padding-left: 22px; margin: 8px 0; }
  .output-box li { margin-bottom: 4px; font-size: 15px; }
  .output-box p { margin: 6px 0; }
  .placeholder { color: var(--muted); font-style: italic; }

  .controls {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-shrink: 0;
  }

  select {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 14px;
    padding: 8px 12px;
    outline: none;
    cursor: pointer;
  }
  select:focus { border-color: rgba(109,196,255,0.4); }

  button {
    background: var(--accent);
    color: #1a1200;
    border: none;
    border-radius: 100px;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 24px;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
    white-space: nowrap;
  }
  button:hover { background: var(--accent-hover); }
  button:active { transform: scale(0.97); }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  button.clear { background: transparent; border: 1px solid var(--border); color: var(--muted); font-weight: 500; }
  button.clear:hover { opacity: 1; border-color: var(--text); color: var(--text); }

  .lang-row {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }
  .lang-group { display: flex; align-items: center; gap: 6px; }
  .lang-label { font-size: 12px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }
  .lang-arrow { color: var(--accent); font-size: 18px; font-weight: 700; padding: 0 2px; }
  .detect-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
    font-weight: 500;
    padding: 6px 10px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .detect-btn:hover { border-color: var(--accent); color: var(--accent); background: rgba(247,168,0,0.06); }
  .detect-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .controls-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
  .detect-confirm {
    font-size: 13px; padding: 5px 12px;
    background: rgba(126,237,192,0.08);
    border: 1px solid rgba(126,237,192,0.25);
    border-radius: 6px; color: var(--accent2);
  }
  .detect-confirm.hidden { display: none; }
  .detect-confirm.changed {
    background: rgba(249,192,128,0.08);
    border-color: rgba(249,192,128,0.3);
    color: #f9c080;
  }
  .spinner { display: none; }

  /* Proofreader section */
  .proof-section {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg-card);
    flex-shrink: 0;
    overflow: hidden;
  }
  .proof-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; cursor: pointer; user-select: none;
    transition: background 0.15s;
  }
  .proof-header:hover { background: rgba(247,168,0,0.04); }
  .proof-title { font-size: 13px; font-weight: 600; color: var(--accent); letter-spacing: 0.5px; text-transform: uppercase; }
  .proof-toggle { color: var(--muted); font-size: 12px; transition: transform 0.2s; }
  .proof-toggle.open { transform: rotate(90deg); }
  .proof-body { display: none; flex-direction: column; gap: 12px; padding: 0 16px 16px; }
  .proof-body.open { display: flex; }
  .proof-body textarea {
    min-height: 120px; max-height: 240px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    color: var(--text); font-size: 14px; line-height: 1.6; padding: 14px;
    resize: vertical; outline: none; font-family: inherit;
  }
  .proof-body textarea:focus { border-color: rgba(247,168,0,0.4); }
  .proof-controls { display: flex; gap: 10px; align-items: center; }

  /* Make right panel scrollable to fit proofreader */
  .panel { overflow-y: auto; }

  /* Export bar */
  .export-bar {
    display: none;
    gap: 8px;
    flex-shrink: 0;
    flex-wrap: wrap;
  }
  .export-bar.visible { display: flex; }
  .export-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
    font-weight: 500;
    padding: 7px 14px;
    border-radius: 100px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .export-btn:hover { border-color: var(--accent); color: var(--accent); background: rgba(247,168,0,0.06); }
  .export-btn.success { border-color: var(--accent2); color: var(--accent2); }

  /* HX loading state */
  .hx-loading {
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 24px;
    height: 100%;
    min-height: 200px;
  }
  .hx-loading.visible { display: flex; }
  .hx-mark { transform-origin: center center; display: block; }
  .hx-loading-text {
    color: var(--muted);
    font-size: 13px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    min-height: 20px;
    transition: opacity 0.3s;
  }

  /* Key gate overlay */
  .key-gate {
    position: fixed; inset: 0; background: rgba(10,12,18,0.92);
    display: flex; align-items: center; justify-content: center;
    z-index: 100; backdrop-filter: blur(4px);
  }
  .key-gate.hidden { display: none; }
  .key-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 40px 48px;
    width: 460px;
    display: flex; flex-direction: column; gap: 24px;
  }
  .key-card h2 { font-size: 22px; font-weight: 700; }
  .key-card p { color: var(--muted); font-size: 14px; line-height: 1.6; }
  .key-option {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
    cursor: pointer;
    transition: border-color 0.15s;
    display: flex; align-items: flex-start; gap: 14px;
  }
  .key-option:hover { border-color: var(--accent); }
  .key-option.selected { border-color: var(--accent); background: rgba(109,196,255,0.05); }
  .key-option input[type=radio] { margin-top: 3px; accent-color: var(--accent); }
  .key-option-body { display: flex; flex-direction: column; gap: 4px; }
  .key-option-title { font-weight: 600; font-size: 15px; }
  .key-option-desc { color: var(--muted); font-size: 13px; }
  .key-input-wrap { display: none; margin-top: 12px; }
  .key-input-wrap.visible { display: block; }
  .key-input-wrap input {
    width: 100%;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 14px;
    font-family: monospace;
    padding: 10px 14px;
    outline: none;
  }
  .key-input-wrap input:focus { border-color: rgba(109,196,255,0.5); }
  .key-confirm { width: 100%; padding: 12px; font-size: 15px; border-radius: 10px; }
  .key-status {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; color: var(--accent2);
    padding: 6px 0; flex-shrink: 0;
  }
  .key-status.warn { color: var(--danger); }
  .key-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
  .ui-lang-toggle {
    display: flex; gap: 4px; margin-left: 16px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 3px;
  }
  .ui-lang-btn {
    background: transparent; border: none; color: var(--muted);
    font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 5px; cursor: pointer;
    transition: all 0.15s;
  }
  .ui-lang-btn.active { background: var(--accent); color: #1a1200; }
  .ui-lang-btn:hover:not(.active) { color: var(--text); }
</style>
</head>
<body>

<header>
  <div class="logo">
    <span>home<strong>exchange</strong> <span style="color:var(--muted);font-weight:400">translate</span></span>
  </div>
  <div class="badge">EN · FR · ES</div>
  <span id="headerTitle" style="margin-left:auto;font-size:13px;color:var(--muted)"></span>
  <div class="ui-lang-toggle">
    <button id="btnLangEN" class="ui-lang-btn active" onclick="setUiLang('en')">EN</button>
    <button id="btnLangFR" class="ui-lang-btn" onclick="setUiLang('fr')">FR</button>
  </div>
</header>

<main>
  <!-- Left panel: input -->
  <div class="panel">
    <div class="panel-label" data-i18n="panelSource"></div>

    <div id="keyStatus" class="key-status" style="display:none">
      <span class="key-dot"></span>
      <span id="keyStatusText"></span>
      <button onclick="changeKey()" id="btnChangeKey" style="margin-left:auto;background:transparent;border:1px solid var(--border);color:var(--muted);font-weight:500;padding:4px 10px;font-size:12px;" data-i18n="btnChange"></button>
    </div>

    <div class="controls">
      <div class="lang-row">
        <div class="lang-group">
          <label class="lang-label">Source</label>
          <select id="sourceLang">
            <option value="auto">Auto</option>
            <option value="EN">EN</option>
            <option value="FR">FR</option>
            <option value="ES">ES</option>
          </select>
          <button class="detect-btn" id="btnDetect" onclick="detectLang()" data-i18n="btnDetect">⟳</button>
        </div>
        <span class="lang-arrow">→</span>
        <div class="lang-group">
          <label class="lang-label">Cible</label>
          <select id="targetLang">
            <option value="FR">FR</option>
            <option value="EN">EN</option>
            <option value="ES">ES</option>
          </select>
        </div>
        <select id="contentType" style="margin-left:8px">
          <option value="auto" data-i18n="typeAuto"></option>
          <option value="blast">Email blast</option>
          <option value="transactionnel" data-i18n="typeTransac"></option>
          <option value="blog">Blog</option>
          <option value="landing">Landing page</option>
          <option value="zendesk">FAQ / Zendesk</option>
          <option value="inapp">In-app</option>
          <option value="social">Social</option>
          <option value="autre" data-i18n="typeOther"></option>
        </select>
      </div>
      <div class="controls-actions">
        <div id="detectConfirm" class="detect-confirm hidden"></div>
        <div class="spinner" id="spinner"></div>
        <button onclick="runTranslate()" id="btnTranslate" data-i18n="btnTranslate"></button>
        <button class="export-btn" onclick="document.getElementById('fileImport').click()" data-i18n="btnImport"></button>
        <input type="file" id="fileImport" accept=".md,.csv,.txt" style="display:none" onchange="importFile(event)"/>
        <button class="clear" onclick="clearAll()" data-i18n="btnClear"></button>
      </div>
    </div>

    <textarea id="inputText" data-i18n="inputPlaceholder"></textarea>
  </div>

  <!-- Right panel: output -->
  <div class="panel">
    <div class="panel-label" data-i18n="panelOutput"></div>
    <div class="output-box" id="output">
      <span class="placeholder" data-i18n="placeholder"></span>
    </div>
    <div class="export-bar" id="exportBar">
      <button class="export-btn" id="btnCopy" onclick="exportCopy()">📋 <span data-i18n="exportCopy"></span></button>
      <button class="export-btn" onclick="exportMarkdown()">⬇ Markdown</button>
      <button class="export-btn" onclick="exportCSV()">⬇ CSV</button>
    </div>
    <!-- Proofreader section -->
    <div class="proof-section" id="proofSection">
      <div class="proof-header" onclick="toggleProofreader()">
        <span class="proof-title" data-i18n="proofTitle"></span>
        <span class="proof-toggle" id="proofToggle">▸</span>
      </div>
      <div class="proof-body" id="proofBody">
        <textarea id="proofInput" data-i18n-placeholder="proofPlaceholder"></textarea>
        <div class="proof-controls">
          <button onclick="runProofread()" id="btnProofread" data-i18n="btnProofread"></button>
          <button class="clear" onclick="clearProofread()" data-i18n="btnClear"></button>
        </div>
        <div class="hx-loading" id="hxProofLoading">
          <svg class="hx-mark" id="proofMark" width="56" height="50" viewBox="0 0 120 100" xmlns="http://www.w3.org/2000/svg">
            <path d="M 54,50 C 50,40 40,28 22,14 C 17,19 22,24 30,31 C 38,38 46,44 49,50 C 46,56 38,62 30,69 C 22,76 17,81 22,86 C 40,72 50,60 54,50 Z" fill="#F7A800"/>
            <path d="M 66,50 C 70,40 80,28 98,14 C 103,19 98,24 90,31 C 82,38 74,44 71,50 C 74,56 82,62 90,69 C 98,76 103,81 98,86 C 80,72 70,60 66,50 Z" fill="#F7A800"/>
          </svg>
          <span class="hx-loading-text" id="proofLoadingText"></span>
        </div>
        <div class="output-box" id="proofOutput" style="display:none"></div>
        <div class="export-bar" id="proofExportBar">
          <button class="export-btn" id="btnProofCopy" onclick="exportProofCopy()">📋 <span data-i18n="exportCopy"></span></button>
          <button class="export-btn" onclick="exportProofMarkdown()">⬇ Markdown</button>
          <button class="export-btn" onclick="exportProofCSV()">⬇ CSV</button>
        </div>
      </div>
    </div>

    <div class="hx-loading" id="hxLoading">
      <svg class="hx-mark" width="72" height="64" viewBox="0 0 120 100" xmlns="http://www.w3.org/2000/svg">
        <!-- Left element: body pointing right, two prongs/tails on the left -->
        <path d="
          M 54,50
          C 50,40 40,28 22,14
          C 17,19 22,24 30,31
          C 38,38 46,44 49,50
          C 46,56 38,62 30,69
          C 22,76 17,81 22,86
          C 40,72 50,60 54,50 Z
        " fill="#F7A800"/>
        <!-- Right element: mirror -->
        <path d="
          M 66,50
          C 70,40 80,28 98,14
          C 103,19 98,24 90,31
          C 82,38 74,44 71,50
          C 74,56 82,62 90,69
          C 98,76 103,81 98,86
          C 80,72 70,60 66,50 Z
        " fill="#F7A800"/>
      </svg>
      <span class="hx-loading-text" data-i18n="loadingText"></span>
    </div>
  </div>
  <!-- Key gate modal -->
  <div class="key-gate" id="keyGate">
    <div class="key-card">
      <div>
        <h2 data-i18n="keyTitle"></h2>
        <p data-i18n="keySubtitle"></p>
      </div>

      <div id="optionCompany" class="key-option" style="display:none" onclick="selectMode('company')">
        <input type="radio" name="keyMode" id="radioCompany" value="company"/>
        <div class="key-option-body">
          <div class="key-option-title" data-i18n="keyCompanyTitle"></div>
          <div class="key-option-desc" data-i18n="keyCompanyDesc"></div>
        </div>
      </div>

      <div class="key-option" id="optionOwn" onclick="selectMode('own')">
        <input type="radio" name="keyMode" id="radioOwn" value="own"/>
        <div class="key-option-body">
          <div class="key-option-title" data-i18n="keyOwnTitle"></div>
          <div class="key-option-desc" data-i18n="keyOwnDesc"></div>
          <div class="key-input-wrap" id="ownKeyWrap">
            <input type="password" id="ownKeyInput" placeholder="sk-ant-api03-..." autocomplete="off" onclick="event.stopPropagation()"/>
          </div>
        </div>
      </div>

      <button class="key-confirm" id="keyConfirmBtn" onclick="confirmKey()" disabled data-i18n="keyContinue"></button>
    </div>
  </div>

</main>

<script>
  let activeKey = '';
  let hasCompanyKey = false;
  let uiLang = localStorage.getItem('hx_ui_lang') || 'en';

  const TRAVEL_WORDS = {
    en: ['Navigating…', 'Wandering…', 'Exploring…', 'Discovering…', 'Roaming…',
         'Exchanging…', 'Globe-trotting…', 'Packing bags…', 'Finding home…',
         'Unlocking doors…', 'Setting sails…', 'Taking off…', 'Crossing borders…',
         'Mapping routes…', 'Jet-setting…', 'Adventuring…', 'Checking in…',
         'Landing soon…', 'Swapping homes…', 'On the road…'],
    fr:  ['En route…', 'On explore…', 'On decouvre…', 'On navigue…', 'On voyage…',
          'On decolle…', "On s'aventure…", "On s'echange…", 'Aux quatre coins…',
          'Cap sur le monde…', "On leve l'ancre…", 'En partance…', "On s'envole…",
          'On trace la route…', 'Bon voyage…', 'En transit…', 'On largue les amarres…',
          'Destination monde…', "A l'horizon…", 'Escale en cours…'],
  };

  let _loadingRAF = null;
  let _loadingWordTimer = null;
  let _loadingDirTimer = null;

  function startLoadingAnim() {
    const mark = document.querySelector('.hx-mark');
    const txt  = document.querySelector('#hxLoading .hx-loading-text');
    const words = TRAVEL_WORDS[uiLang] || TRAVEL_WORDS.en;

    // Random word cycling
    const nextWord = () => {
      txt.style.opacity = '0';
      setTimeout(() => {
        txt.textContent = words[Math.floor(Math.random() * words.length)];
        txt.style.opacity = '1';
      }, 300);
    };
    nextWord();
    _loadingWordTimer = setInterval(nextWord, 2000);

    // Random rotation with direction flips
    let angle = 0;
    let speed = 2.5;

    const flipDir = () => {
      const dir  = Math.random() > 0.5 ? 1 : -1;
      speed = dir * (1.8 + Math.random() * 3.5);
      _loadingDirTimer = setTimeout(flipDir, 500 + Math.random() * 900);
    };
    flipDir();

    const tick = () => {
      angle += speed;
      mark.style.transform = 'rotate(' + angle + 'deg)';
      _loadingRAF = requestAnimationFrame(tick);
    };
    _loadingRAF = requestAnimationFrame(tick);
  }

  function stopLoadingAnim() {
    clearInterval(_loadingWordTimer);
    clearTimeout(_loadingDirTimer);
    cancelAnimationFrame(_loadingRAF);
    const mark = document.querySelector('.hx-mark');
    if (mark) mark.style.transform = '';
  }

  const I18N = {
    en: {
      headerTitle: 'HomeExchange Translation Assistant',
      panelSource: 'Content to translate',
      panelOutput: 'Translation',
      placeholder: 'The translation will appear here with the source / target table and QA checklist.',
      btnDetect: '⟳ Detect',
      btnTranslate: 'Translate',
      btnClear: 'Clear',
      btnChange: 'Change',
      typeAuto: 'Type: auto',
      typeTransac: 'Email transactional',
      typeOther: 'Other content',
      keyTitle: 'API key required',
      keySubtitle: 'Choose how you want to use the HomeExchange translation assistant.',
      keyCompanyTitle: 'Use HomeExchange shared key',
      keyCompanyDesc: 'Team key configured by the company. No personal key required.',
      keyOwnTitle: 'Use my own Anthropic key',
      keyOwnDesc: 'Enter your personal key (sk-ant-…). Stored only in your browser.',
      keyContinue: 'Continue',
      keyActiveCompany: 'HomeExchange key active',
      keyActiveOwn: 'Personal key active',
      alertNoKey: 'Enter your Anthropic API key before translating.',
      alertNoText: 'Paste some content to translate.',
      alertDetectNoText: 'Paste some content first.',
      alertDetectError: 'Detection error: ',
      detectedLabel: 'Source detected: ',
      inputPlaceholder: 'Paste content to translate here (email, UI copy, CTA, blog…)\\n\\nClick ⟳ Detect to identify the source language before translating.',
      loadingText: 'Translating…',
      exportCopy: 'Copy',
      exportCopied: 'Copied!',
      btnImport: '📂 Import',
      importError: 'Unsupported file. Use .md or .csv',
      proofTitle: 'Proofreader',
      proofPlaceholder: 'Paste or edit the text to proofread here…',
      btnProofread: '✦ Proofread',
      proofLoadingText: 'Reviewing…',
    },
    fr: {
      headerTitle: 'Assistant de traduction HomeExchange',
      panelSource: 'Contenu à traduire',
      panelOutput: 'Traduction',
      placeholder: 'La traduction apparaîtra ici avec le tableau source / cible et la checklist QA.',
      btnDetect: '⟳ Détecter',
      btnTranslate: 'Traduire',
      btnClear: 'Effacer',
      btnChange: 'Changer',
      typeAuto: 'Type auto',
      typeTransac: 'Email transactionnel',
      typeOther: 'Autre contenu',
      keyTitle: 'Clé API requise',
      keySubtitle: "Choisis comment tu veux utiliser l'assistant de traduction HomeExchange.",
      keyCompanyTitle: 'Utiliser la clé HomeExchange',
      keyCompanyDesc: "Clé partagée configurée par l'équipe. Aucune clé personnelle requise.",
      keyOwnTitle: 'Utiliser ma propre clé Anthropic',
      keyOwnDesc: 'Entre ta clé personnelle (sk-ant-…). Stockée uniquement dans ton navigateur.',
      keyContinue: 'Continuer',
      keyActiveCompany: 'Clé HomeExchange active',
      keyActiveOwn: 'Clé personnelle active',
      alertNoKey: 'Entre ta clé API Anthropic avant de traduire.',
      alertNoText: 'Colle un contenu à traduire.',
      alertDetectNoText: "Colle d'abord un contenu.",
      alertDetectError: 'Erreur de détection : ',
      detectedLabel: 'Source détectée : ',
      inputPlaceholder: 'Colle ici le contenu à traduire (email, UI copy, CTA, blog…)\\n\\nClique sur ⟳ Détecter pour identifier la langue source avant de traduire.',
      loadingText: 'Traduction en cours…',
      exportCopy: 'Copier',
      exportCopied: 'Copié !',
      btnImport: '📂 Importer',
      importError: 'Fichier non supporté. Utilise .md ou .csv',
      proofTitle: 'Proofreader',
      proofPlaceholder: 'Colle ou édite ici le texte à relire…',
      btnProofread: '✦ Relire',
      proofLoadingText: 'Relecture en cours…',
    }
  };

  function t(key) { return I18N[uiLang][key] || I18N.en[key] || key; }

  function setUiLang(lang) {
    uiLang = lang;
    localStorage.setItem('hx_ui_lang', lang);
    document.getElementById('btnLangEN').className = 'ui-lang-btn' + (lang === 'en' ? ' active' : '');
    document.getElementById('btnLangFR').className = 'ui-lang-btn' + (lang === 'fr' ? ' active' : '');
    applyI18n();
  }

  function applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.dataset.i18n;
      const val = t(key);
      if (el.tagName === 'OPTION') el.textContent = val;
      else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.placeholder = val;
      else el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.getElementById('headerTitle').textContent = t('headerTitle');
    // Update placeholder in output if untouched
    const ph = document.querySelector('#output .placeholder');
    if (ph) ph.textContent = t('placeholder');
  }

  async function initKeyGate() {
    const res = await fetch('/config');
    const data = await res.json();
    hasCompanyKey = data.has_company_key;

    if (hasCompanyKey) {
      document.getElementById('optionCompany').style.display = 'flex';
    }

    // Check saved preference
    const saved = localStorage.getItem('hx_key_mode');
    const savedOwn = localStorage.getItem('hx_own_key') || '';

    if (saved === 'company' && hasCompanyKey) {
      selectMode('company');
      confirmKey(true);
    } else if (saved === 'own' && savedOwn.startsWith('sk-')) {
      document.getElementById('ownKeyInput').value = savedOwn;
      selectMode('own');
      confirmKey(true);
    } else {
      // No saved pref: if company key exists, pre-select it
      if (hasCompanyKey) selectMode('company');
      document.getElementById('keyGate').className = 'key-gate';
    }
  }

  function selectMode(mode) {
    document.getElementById('radioCompany').checked = (mode === 'company');
    document.getElementById('radioOwn').checked = (mode === 'own');
    document.getElementById('optionCompany').className = 'key-option' + (mode === 'company' ? ' selected' : '');
    document.getElementById('optionOwn').className = 'key-option' + (mode === 'own' ? ' selected' : '');
    document.getElementById('ownKeyWrap').className = 'key-input-wrap' + (mode === 'own' ? ' visible' : '');
    document.getElementById('keyConfirmBtn').disabled = false;
    if (mode === 'own') document.getElementById('ownKeyInput').focus();
  }

  function confirmKey(silent = false) {
    const mode = document.getElementById('radioCompany').checked ? 'company' : 'own';

    if (mode === 'company') {
      activeKey = '__company__';
      localStorage.setItem('hx_key_mode', 'company');
      showStatus(t('keyActiveCompany'), false);
    } else {
      const val = document.getElementById('ownKeyInput').value.trim();
      if (!val.startsWith('sk-')) {
        if (!silent) { document.getElementById('ownKeyInput').focus(); return; }
        return;
      }
      activeKey = val;
      localStorage.setItem('hx_key_mode', 'own');
      localStorage.setItem('hx_own_key', val);
      showStatus(t('keyActiveOwn'), false);
    }

    document.getElementById('keyGate').className = 'key-gate hidden';
  }

  function showStatus(msg, warn) {
    const s = document.getElementById('keyStatus');
    s.style.display = 'flex';
    s.className = 'key-status' + (warn ? ' warn' : '');
    document.getElementById('keyStatusText').textContent = msg;
  }

  function changeKey() {
    document.getElementById('keyGate').className = 'key-gate';
  }

  let lastRawOutput = '';

  // ── Proofreader ────────────────────────────────────────────────
  let lastProofOutput = '';
  let _proofRAF = null, _proofWordTimer = null, _proofDirTimer = null;

  function toggleProofreader() {
    const body   = document.getElementById('proofBody');
    const toggle = document.getElementById('proofToggle');
    const open   = body.classList.toggle('open');
    toggle.className = 'proof-toggle' + (open ? ' open' : '');
  }

  function clearProofread() {
    document.getElementById('proofInput').value = '';
    document.getElementById('proofOutput').style.display = 'none';
    document.getElementById('proofOutput').innerHTML = '';
    document.getElementById('proofExportBar').className = 'export-bar';
    lastProofOutput = '';
  }

  function startProofAnim() {
    const mark = document.getElementById('proofMark');
    const txt  = document.getElementById('proofLoadingText');
    txt.textContent = t('proofLoadingText');
    let angle = 0, speed = 2.5;
    const flip = () => {
      speed = (Math.random() > 0.5 ? 1 : -1) * (1.8 + Math.random() * 3.5);
      _proofDirTimer = setTimeout(flip, 500 + Math.random() * 900);
    };
    flip();
    const tick = () => {
      angle += speed;
      mark.style.transform = 'rotate(' + angle + 'deg)';
      _proofRAF = requestAnimationFrame(tick);
    };
    _proofRAF = requestAnimationFrame(tick);
  }

  function stopProofAnim() {
    clearTimeout(_proofDirTimer);
    cancelAnimationFrame(_proofRAF);
    const mark = document.getElementById('proofMark');
    if (mark) mark.style.transform = '';
  }

  async function runProofread() {
    if (!activeKey) { changeKey(); return; }
    const text = document.getElementById('proofInput').value.trim();
    if (!text) { alert(t('alertNoText')); return; }

    const loader = document.getElementById('hxProofLoading');
    const output = document.getElementById('proofOutput');
    const btn    = document.getElementById('btnProofread');

    btn.disabled = true;
    output.style.display = 'none';
    loader.className = 'hx-loading visible';
    document.getElementById('proofExportBar').className = 'export-bar';
    startProofAnim();

    try {
      const resp = await fetch('/proofread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, api_key: activeKey })
      });
      if (!resp.ok) {
        const err = await resp.json();
        output.textContent = 'Error: ' + (err.detail || resp.statusText);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value, { stream: true }).split('\\n')) {
          if (line.startsWith('data: ')) {
            try { const d = JSON.parse(line.slice(6)); if (d.text) full += d.text; } catch {}
          }
        }
      }
      stopProofAnim();
      loader.className = 'hx-loading';
      output.style.display = '';
      lastProofOutput = full;
      renderMarkdown(output, full);
      output.scrollTop = 0;
      document.getElementById('proofExportBar').className = 'export-bar visible';
    } catch (e) {
      stopProofAnim();
      loader.className = 'hx-loading';
      output.style.display = '';
      output.textContent = 'Network error: ' + e.message;
    } finally {
      btn.disabled = false;
    }
  }

  function exportProofCopy() {
    if (!lastProofOutput) return;
    navigator.clipboard.writeText(lastProofOutput).then(() => {
      const btn = document.getElementById('btnProofCopy');
      btn.className = 'export-btn success';
      btn.querySelector('[data-i18n]').textContent = t('exportCopied');
      setTimeout(() => {
        btn.className = 'export-btn';
        btn.querySelector('[data-i18n]').textContent = t('exportCopy');
      }, 2000);
    });
  }

  function exportProofMarkdown() {
    if (!lastProofOutput) return;
    const blob = new Blob([lastProofOutput], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'proofread.md'; a.click();
    URL.revokeObjectURL(url);
  }

  function exportProofCSV() {
    if (!lastProofOutput) return;
    const lines = lastProofOutput.split('\\n');
    const rows = lines.filter(l => l.trim().startsWith('|') && !l.trim().match(/^\\|[-| :]+\\|$/))
      .map(l => l.split('|').slice(1,-1).map(c => {
        const clean = c.trim().replace(/\\*\\*(.+?)\\*\\*/g, '$1');
        return clean.includes(',') || clean.includes('"') ? '"' + clean.replace(/"/g,'""') + '"' : clean;
      }).join(','));
    const content = rows.length ? rows.join('\\n') : lastProofOutput;
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'proofread.csv'; a.click();
    URL.revokeObjectURL(url);
  }
  // ────────────────────────────────────────────────────────────────

  function extractTranslatedText(raw) {
    const lines = raw.split('\\n');
    const parts = [];
    let headerSkipped = false;

    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('|')) continue;
      if (t.match(/^\\|[-| :]+\\|$/)) { headerSkipped = false; continue; } // separator — next row is data
      const cells = t.split('|').slice(1, -1).map(c =>
        c.trim().replace(/\\*\\*(.+?)\\*\\*/g, '$1').replace(/`([^`]+)`/g, '$1')
      );
      if (!headerSkipped) { headerSkipped = true; continue; } // skip column header row
      if (cells.length < 2) continue;
      const label  = cells[0];
      const target = cells[cells.length - 1];
      if (!target || target === '' || target.startsWith('[')) continue;
      parts.push(label ? label + ': ' + target : target);
    }

    // Fallback: if no table found, return the raw text
    return parts.length > 0 ? parts.join('\\n\\n') : raw;
  }

  function importFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['md', 'csv', 'txt'].includes(ext)) {
      alert(t('importError'));
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      let content = e.target.result;

      // For CSV: convert rows back to a readable markdown-like table for the textarea
      if (ext === 'csv') {
        const lines = content.trim().split('\\n');
        const tableLines = lines.map(line => {
          const cells = line.match(/("([^"]|"")*"|[^,]*)(,("([^"]|"")*"|[^,]*))*/)
            ? line.split(',').map(c => c.replace(/^"|"$/g, '').replace(/""/g, '"').trim())
            : [line];
          return '| ' + cells.join(' | ') + ' |';
        });
        // Insert separator after header
        if (tableLines.length > 1) {
          const sep = '| ' + tableLines[0].split('|').slice(1,-1).map(() => '---').join(' | ') + ' |';
          tableLines.splice(1, 0, sep);
        }
        content = tableLines.join('\\n');
      }

      document.getElementById('inputText').value = content;
      // Reset file input so the same file can be re-imported
      event.target.value = '';
    };
    reader.readAsText(file, 'UTF-8');
  }

  function clearAll() {
    document.getElementById('inputText').value = '';
    document.getElementById('output').innerHTML = `<span class="placeholder">${t('placeholder')}</span>`;
    document.getElementById('sourceLang').value = 'auto';
    document.getElementById('detectConfirm').className = 'detect-confirm hidden';
    document.getElementById('exportBar').className = 'export-bar';
    lastRawOutput = '';
  }

  function exportCopy() {
    if (!lastRawOutput) return;
    navigator.clipboard.writeText(lastRawOutput).then(() => {
      const btn = document.getElementById('btnCopy');
      btn.className = 'export-btn success';
      btn.querySelector('[data-i18n]').textContent = t('exportCopied');
      setTimeout(() => {
        btn.className = 'export-btn';
        btn.querySelector('[data-i18n]').textContent = t('exportCopy');
      }, 2000);
    });
  }

  function exportMarkdown() {
    if (!lastRawOutput) return;
    const blob = new Blob([lastRawOutput], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'translation.md';
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportCSV() {
    if (!lastRawOutput) return;
    const lines = lastRawOutput.split('\\n');
    const csvRows = [];
    for (const line of lines) {
      if (line.trim().startsWith('|') && !line.trim().match(/^\\|[-| :]+\\|$/)) {
        const cells = line.split('|').slice(1, -1).map(c => {
          const clean = c.trim().replace(/\\*\\*(.+?)\\*\\*/g, '$1');
          return clean.includes(',') || clean.includes('"') || clean.includes('\\n')
            ? '"' + clean.replace(/"/g, '""') + '"'
            : clean;
        });
        csvRows.push(cells.join(','));
      }
    }
    const content = csvRows.length ? csvRows.join('\\n') : lastRawOutput;
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'translation.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  async function detectLang() {
    if (!activeKey) { changeKey(); return; }
    const text = document.getElementById('inputText').value.trim();
    if (!text) { alert(t('alertDetectNoText')); return; }

    const btn = document.getElementById('btnDetect');
    btn.disabled = true;
    btn.textContent = '...';

    try {
      const res = await fetch('/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, api_key: activeKey })
      });
      const data = await res.json();
      const detected = data.lang;

      const select = document.getElementById('sourceLang');
      const prev = select.value;
      select.value = detected;

      const confirm = document.getElementById('detectConfirm');
      const labels = { EN: 'English', FR: 'Français', ES: 'Español' };
      confirm.textContent = t('detectedLabel') + (labels[detected] || detected);
      confirm.className = 'detect-confirm' + (prev !== 'auto' && prev !== detected ? ' changed' : '');
    } catch(e) {
      alert(t('alertDetectError') + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = t('btnDetect');
    }
  }

  async function runTranslate() {
    if (!activeKey) { changeKey(); return; }
    const key = activeKey;

    const text = document.getElementById('inputText').value.trim();
    if (!text) { alert(t('alertNoText')); return; }

    const sourceLang = document.getElementById('sourceLang').value;
    const lang = document.getElementById('targetLang').value;
    const type = document.getElementById('contentType').value;

    const btn = document.getElementById('btnTranslate');
    const spinner = document.getElementById('spinner');
    const output = document.getElementById('output');

    const loader = document.getElementById('hxLoading');

    btn.disabled = true;
    output.style.display = 'none';
    loader.className = 'hx-loading visible';
    startLoadingAnim();

    const srcInfo = sourceLang !== 'auto' ? ` from ${sourceLang}` : '';
    const typeInfo = type !== 'auto' ? ` (type: ${type})` : '';
    const userMessage = `Translate this content${srcInfo} to ${lang}${typeInfo}:\\n\\n${text}`;

    try {
      const resp = await fetch('/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: userMessage, api_key: key })
      });

      if (!resp.ok) {
        const err = await resp.json();
        output.textContent = 'Error: ' + (err.detail || resp.statusText);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let full = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\\n')) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.text) full += data.text;
            } catch {}
          }
        }
      }

      stopLoadingAnim();
      loader.className = 'hx-loading';
      output.style.display = '';
      lastRawOutput = full;
      renderMarkdown(output, full);
      output.scrollTop = 0;
      document.getElementById('exportBar').className = 'export-bar visible';
      // Auto-populate proofreader with translated text only (target column)
      document.getElementById('proofInput').value = extractTranslatedText(full);

    } catch (e) {
      stopLoadingAnim();
      loader.className = 'hx-loading';
      output.style.display = '';
      output.textContent = 'Network error: ' + e.message;
    } finally {
      btn.disabled = false;
    }
  }

  function renderMarkdown(el, text) {
    const lines = text.split('\\n');
    let html = '';
    let inTable = false;
    let tableLines = [];
    let inList = false;

    const flushTable = () => {
      if (tableLines.length) { html += renderTable(tableLines); tableLines = []; }
      inTable = false;
    };
    const flushList = () => {
      if (inList) { html += '</ul>'; inList = false; }
    };

    for (const line of lines) {
      const t = line.trim();

      if (t.startsWith('|')) {
        flushList();
        inTable = true;
        tableLines.push(line);
        continue;
      }
      if (inTable) flushTable();

      if (t === '---' || t === '***' || t === '___') {
        flushList();
        html += '<hr>';
      } else if (t.startsWith('### ')) {
        flushList();
        html += `<h3>${inlineEsc(t.slice(4))}</h3>`;
      } else if (t.startsWith('## ')) {
        flushList();
        html += `<h2>${inlineEsc(t.slice(3))}</h2>`;
      } else if (t.startsWith('# ')) {
        flushList();
        html += `<h2>${inlineEsc(t.slice(2))}</h2>`;
      } else if (t.startsWith('> ')) {
        flushList();
        html += `<blockquote>${inlineEsc(t.slice(2))}</blockquote>`;
      } else if (t.startsWith('- ') || t.startsWith('* ')) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${inlineEsc(t.slice(2))}</li>`;
      } else if (t === '') {
        flushList();
        html += '<br>';
      } else {
        flushList();
        html += `<p>${inlineEsc(t)}</p>`;
      }
    }
    flushTable();
    flushList();
    el.innerHTML = html;
  }

  function renderTable(lines) {
    const rows = lines.filter(l => !l.trim().match(/^\\|[-| :]+\\|$/));
    let html = '<table>';
    rows.forEach((row, i) => {
      const cells = row.split('|').slice(1, -1).map(c => c.trim());
      const tag = i === 0 ? 'th' : 'td';
      html += '<tr>' + cells.map(c => `<${tag}>${inlineEsc(c)}</${tag}>`).join('') + '</tr>';
    });
    return html + '</table>';
  }

  function inlineEsc(text) {
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
      .replace(/\\*(.+?)\\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') runTranslate();
  });

  setUiLang(uiLang);
  initKeyGate();
</script>
</body>
</html>
"""


COMPANY_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class TranslateRequest(BaseModel):
    text: str
    api_key: str  # "__company__" to use server-side key

class DetectRequest(BaseModel):
    text: str
    api_key: str


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_TEMPLATE


@app.get("/config")
def config():
    return {"has_company_key": bool(COMPANY_KEY)}


@app.post("/proofread")
def proofread(req: TranslateRequest):
    from fastapi import HTTPException
    if req.api_key == "__company__":
        if not COMPANY_KEY:
            raise HTTPException(status_code=403, detail="No company key configured.")
        key = COMPANY_KEY
    else:
        if not req.api_key or not req.api_key.startswith("sk-"):
            raise HTTPException(status_code=400, detail="Invalid API key.")
        key = req.api_key

    client = anthropic.Anthropic(api_key=key)

    def stream():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            system=PROOFREADER_PROMPT,
            messages=[{"role": "user", "content": req.text}],
        ) as s:
            for text in s.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/detect")
def detect(req: DetectRequest):
    from fastapi import HTTPException
    if req.api_key == "__company__":
        if not COMPANY_KEY:
            raise HTTPException(status_code=403, detail="Aucune clé entreprise configurée.")
        key = COMPANY_KEY
    else:
        if not req.api_key or not req.api_key.startswith("sk-"):
            raise HTTPException(status_code=400, detail="Clé API invalide.")
        key = req.api_key

    client = anthropic.Anthropic(api_key=key)
    snippet = req.text[:400]
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        system="Detect the language of the text. Reply with only the language code: EN, FR, or ES. Nothing else.",
        messages=[{"role": "user", "content": snippet}],
    )
    lang = msg.content[0].text.strip().upper()
    if lang not in ("EN", "FR", "ES"):
        lang = "EN"
    return {"lang": lang}


@app.post("/translate")
def translate(req: TranslateRequest):
    if req.api_key == "__company__":
        if not COMPANY_KEY:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Aucune clé entreprise configurée.")
        key = COMPANY_KEY
    else:
        if not req.api_key or not req.api_key.startswith("sk-"):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Clé API invalide.")
        key = req.api_key

    client = anthropic.Anthropic(api_key=key)

    def stream():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": req.text}],
        ) as s:
            for text in s.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
