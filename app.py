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

2. Toujours vérifier s'il existe déjà une traduction validée. Si un segment ou une phrase très proche existe dans la mémoire des traductions validées, reprendre la traduction telle quelle sans "améliorer".

3. Glossaire. Si un terme figure dans le glossaire, reprendre la traduction littéralement telle qu'elle est écrite — même casse, accents, espaces, ponctuation.

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

1. Qualifier : détecter langue source et cible, identifier la typologie (Email blast / Email transactionnel / Blog / Autre).
2. Verrouiller la technique : HTML, variables, tokens intouchables.
3. Appliquer le glossaire systématiquement avant de traduire.
4. Traduire selon le sous-processus correspondant.
5. Contrôle qualité : technique intacte, glossaire respecté, TOV OK, inclusif OK, fluidité, longueur.

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
Objectif : informer + inspirer. Paragraphes courts. Adapter les expressions pour un texte naturel. Conserver titres, sous-titres, listes, liens, ancres. URLs blog : laisser pour traitement manuel.

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
    --accent: #6dc4ff;
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
  .logo { font-size: 18px; font-weight: 700; color: var(--text); }
  .logo span { color: var(--accent); }
  .badge { font-size: 12px; background: rgba(109,196,255,0.12); color: var(--accent); border: 1px solid rgba(109,196,255,0.25); border-radius: 100px; padding: 3px 10px; }

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
    color: #0f1117;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 24px;
    cursor: pointer;
    transition: opacity 0.15s;
    white-space: nowrap;
  }
  button:hover { opacity: 0.88; }
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
  .detect-btn:hover { border-color: var(--accent); color: var(--accent); }
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
  .spinner {
    display: none;
    width: 16px; height: 16px;
    border: 2px solid rgba(109,196,255,0.2);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }
  .spinner.visible { display: block; }
  @keyframes spin { to { transform: rotate(360deg); } }

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
  .ui-lang-btn.active { background: var(--accent); color: #0f1117; }
  .ui-lang-btn:hover:not(.active) { color: var(--text); }
</style>
</head>
<body>

<header>
  <div class="logo">HX <span>Translate</span></div>
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

  function clearAll() {
    document.getElementById('inputText').value = '';
    document.getElementById('output').innerHTML = `<span class="placeholder">${t('placeholder')}</span>`;
    document.getElementById('sourceLang').value = 'auto';
    document.getElementById('detectConfirm').className = 'detect-confirm hidden';
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

    btn.disabled = true;
    spinner.className = 'spinner visible';
    output.className = 'output-box streaming';
    output.textContent = '';

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
        output.textContent = 'Erreur : ' + (err.detail || resp.statusText);
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
              if (data.text) {
                full += data.text;
                output.textContent = full;
                output.scrollTop = output.scrollHeight;
              }
            } catch {}
          }
        }
      }

      // Basic markdown rendering for tables
      renderMarkdown(output, full);

    } catch (e) {
      output.textContent = 'Erreur réseau : ' + e.message;
    } finally {
      btn.disabled = false;
      spinner.className = 'spinner';
      output.className = 'output-box';
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
