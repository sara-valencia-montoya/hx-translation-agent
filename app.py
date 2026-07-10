import os
import json
import secrets
from urllib.parse import urlencode
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import httpx
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ALLOWED_DOMAIN        = "homeexchange.com"
_raw_emails           = os.getenv("ALLOWED_EMAILS", "")
ALLOWED_EMAILS        = {e.strip().lower() for e in _raw_emails.split(",") if e.strip()}
SESSION_COOKIE        = "hx_auth"
SESSION_SECRET        = os.getenv("SESSION_SECRET", secrets.token_hex(32))
GOOGLE_CLIENT_ID      = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET  = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI   = os.getenv("GOOGLE_REDIRECT_URI", "")
signer = URLSafeTimedSerializer(SESSION_SECRET)

def get_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return signer.loads(token, max_age=86400 * 7)  # 7 days
    except (BadSignature, SignatureExpired):
        return None

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    public = {"/login", "/login/check", "/auth/google", "/auth/callback"}
    if request.url.path in public:
        return await call_next(request)
    if not get_session(request):
        return RedirectResponse("/login")
    return await call_next(request)

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>homeexchange translate — Sign in</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: #f4f5f8; color: #16181d;
    height: 100vh; display: flex; align-items: center; justify-content: center;
  }
  .card {
    background: #ffffff; border: 1px solid #e3e6ea;
    border-radius: 16px; padding: 48px 52px; width: 420px;
    display: flex; flex-direction: column; gap: 28px;
  }
  .brand { font-size: 18px; font-weight: 700; }
  .brand strong { color: #fbb341; }
  .brand span { color: #6b7280; font-weight: 400; }
  h2 { font-size: 22px; font-weight: 700; line-height: 1.3; }
  p { color: #6b7280; font-size: 14px; line-height: 1.6; }
  .google-btn {
    display: flex; align-items: center; justify-content: center; gap: 12px;
    background: #fff; color: #1f1f1f; border: 1px solid #e3e6ea; border-radius: 100px;
    font-size: 15px; font-weight: 600; padding: 13px 24px; cursor: pointer;
    transition: background 0.15s; width: 100%; text-decoration: none;
  }
  .google-btn:hover { background: #f0f0f0; }
  .google-btn svg { flex-shrink: 0; }
  .error {
    background: rgba(220,38,38,0.08); border: 1px solid rgba(220,38,38,0.3);
    border-radius: 8px; padding: 12px 16px; color: #dc2626; font-size: 14px;
    display: none;
  }
  .error.visible { display: block; }
</style>
</head>
<body>
<div class="card">
  <div class="brand">home<strong>exchange</strong> <span>translate</span></div>
  <div>
    <h2>Sign in to continue</h2>
    <p style="margin-top:8px">This tool is reserved for HomeExchange team members.</p>
  </div>
  <div class="error {error_class}">{error_msg}</div>
  <a href="/auth/google" class="google-btn">
    <svg width="20" height="20" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/><path fill="none" d="M0 0h48v48H0z"/></svg>
    Sign in with Google
  </a>
</div>
</body>
</html>"""

@app.get("/login", response_class=HTMLResponse)
def login_page(error: str = ""):
    if error == "domain":
        html = LOGIN_PAGE.replace("{error_class}", "visible").replace(
            "{error_msg}", "Access restricted to authorised HomeExchange accounts.")
    else:
        html = LOGIN_PAGE.replace("{error_class}", "").replace("{error_msg}", "")
    return html

@app.get("/auth/google")
def auth_google():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email",
        "hd": ALLOWED_DOMAIN,  # hints Google to show only @homeexchange.com accounts
        "access_type": "online",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)

@app.get("/auth/callback")
async def auth_callback(code: str = None, error: str = None):
    if error or not code:
        return RedirectResponse("/login?error=domain", status_code=303)
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse("/login?error=domain", status_code=303)
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        email = user_resp.json().get("email", "").strip().lower()
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        return RedirectResponse("/login?error=domain", status_code=303)
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return RedirectResponse("/login?error=domain", status_code=303)
    token = signer.dumps({"email": email})
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=86400 * 7, samesite="lax")
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp

SYSTEM_PROMPT = """Tu es un traducteur ou traductrice professionnel(le) spécialisé(e) HomeExchange.

## Identité

- Langues : EN, FR, ES, IT, DE, PT, NL, DA, SV, NO, HR
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
- **[ES] "finalize [an/my/the/your] exchange"** : Toujours traduire par "registrar intercambio" — jamais "cerrar", "confirmar", "completar" ni aucune autre formulation. La forme varie (finalize an / my / the / your exchange) mais la traduction ES est toujours "registrar intercambio".
- **[FR] "secure your [first/an/the] exchange"** : Traduire par "organiser" — jamais "financer" ni aucun autre terme à connotation financière. Ex : "Enough to secure your first exchange" → "De quoi organiser votre premier échange" (et non "De quoi financer votre premier échange"). Cohérent avec la règle GuestPoints : aucun vocabulaire monétaire autour des échanges.

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

- Scope: English (EN), French (FR), Spanish (ES), Italian (IT), German (DE), Portuguese (PT), Dutch (NL), Danish (DA), Swedish (SV), Norwegian (NO), Croatian (HR).
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

**If the input contains labeled fields** (e.g. "Subject line: …", "Pre-header: …", "Body: …"), output the improved version as a markdown table:

| Field | Original | Improved |
|---|---|---|
| Subject line | [original] | [improved] |
| Pre-header | [original] | [improved] |
| … | … | … |

**If the input is plain text without labels**, output a table with numbered rows:

| # | Original | Improved |
|---|---|---|
| 1 | [original sentence] | [improved sentence] |

Rules for the table:
- No preamble, no intro sentence before the table. Start immediately with the table.
- Keep each cell on a single line (no line breaks inside cells).
- Apply all HomeExchange rules to the Improved column.
- Never remove meaning, CTAs, warnings, or legal mentions.

If you made structural changes, add a brief note AFTER the table under the heading `### What changed` (1-3 bullets max).

If the content is Product/UI copy: act as a UX content assistant. Be an expert in microcopy: clear, inclusive, actionable, aligned with HomeExchange TOV and UX writing guidelines.

If something is ambiguous (channel, audience, intent): state your best assumption and proceed. Do not ask for clarification unless absolutely necessary.
"""

GLOSSARY_TABLE = """

## Glossaire officiel HomeExchange — EN / FR / ES / DE / IT / PT / NL / HR / DA / NO / SV (source canonique : Translation glossary database)

Cette table est la source de vérité. Pour tout terme du texte source qui y figure, reprendre la traduction approuvée au caractère près (accents, casse, espaces, ponctuation) — ne jamais reformuler ni "améliorer" un terme déjà listé ici.

| Contexte | EN | FR | ES | DE | IT | PT | NL | HR | DA | NO | SV |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Concept | home exchange / home swapping | échange de maisons | intercambio de casas // intercambios de casa | Haustausch | scambio casa | troca de casa | huizenruil | Zamjena domova | boligbytte | boligbytte | hembyte / hembyten |
| Payment page | Pay {{price}} | Payer {{price}} | Pagar {{price}} | {{price}} bezahlen | Paga {{price}} | Pagar {{price}} | Betaal {{price}} | Platiti {{price}} | Betal {{price}} | Betal {{price}} | Betala {{price}} |
| Membership > to payment page [imperative] | Pay for my membership | Payez votre adhésion | Paga tu suscripción | Meine Mitgliedschaft bezahlen | Paga l'abbonamento | Pague a sua filiação | Betaal voor mijn lidmaatschap | Platite svoju članarinu | Betal for mit medlemskab | Betal for mitt medlemskap | Betala mitt medlemskap |
| Membership CTA > to payment page | Pay for my membership | Payer mon adhésion | Pagar mi suscripción | Mitgliedschaft bezahlen | Mi abbono | Pagar a minha filiação | Betaal voor mijn lidmaatschap | Platite moju članarinu | Betal for mit medlemskab | Betal for mitt medlemskap | Betala mitt medlemskap |
| Membership CTA > to payment page | Pay for your membership | Payer votre adhésion | Pagar la suscripción | Mitgliedschaft bezahlen | Abbonati ora | Pagar a filiação | Betaal voor je lidmaatschap | Platite svoju članarinu | Betal for dit medlemskab | Betal for ditt medlemskap | Betala ditt medlemskap |
| Membership CTA > to payment page | Start my membership | Prendre mon adhésion | Activar mi suscripción | Mitgliedschaft starten | Attiva l'abbonamento | Iniciar a minha filiação | Start mijn lidmaatschap | Pokrenite moje članstvo | Start mit medlemskab | Start mitt medlemskap | Starta mitt medlemskap |
| Membership CTA > to payment page | Start your membership | Prendre votre adhésion | Activar la suscripción | Mitgliedschaft starten | Attiva l'abbonamento | Iniciar a filiação | Start je lidmaatschap | Pokrenite svoje članstvo | Start dit medlemskab | Start ditt medlemskap | Starta ditt medlemskap |
| Membership > to payment page [imperative] | Start your membership | Prenez votre adhésion | Activa la suscripción | Mitgliedschaft starten | Attiva l'abbonamento | Inicie a sua filiação | Start je lidmaatschap | Pokrenite svoje članstvo | Start dit medlemskab | Start ditt medlemskap | Starta ditt medlemskap |
| Membership CTA > to payment page | Renew my membership | Renouveler mon adhésion | Renovar mi suscripción | Mitgliedschaft verlängern | Rinnovo l'abbonamento | Renovar a filiação | Vernieuw je lidmaatschap | Produljite svoje članstvo | Forny dit medlemskab | Forny medlemskapet ditt | Förnya mitt medlemskap |
| Membership > to payment page [imperative] | Renew your membership | Renouvelez votre adhésion | Renova tu suscripción | Verlängern Sie Ihre Mitgliedschaft | Rinnova l'abbonamento | Renove a sua filiação | Vernieuw je lidmaatschap | Produljite svoje članstvo | Forny dit medlemskab | Forny medlemskapet ditt | Förnya ditt medlemskap |
| Membership CTA > to My Plan page | Join the community | Rejoindre la communauté | Únete a la comunidad | Teil der Community werden | Unisciti alla comunità | Juntar-me à comunidade | Word lid van onze community | Pridružite se zajednici | Bliv en del af fællesskabet | Bli med i fellesskapet | Gå med i communityn |
| Membership CTA > to My Plan page | Become a member | Devenir membre | Hazte miembro | Mitglied werden | Diventa membro | Tornar-me membro | Word lid | Postanite član | Bliv medlem | Bli medlem | Bli medlem |
| When people leave reviews about their exchange | Reviews | Avis | Comentarios | Bewertungen | Recensioni | Avaliações | Beoordelingen | Osvrti | Anmeldelser | Anmeldelser | Recensioner |
| Review CTA | Rate your exchange | Noter votre échange / Noter cet échange | Valora tu intercambio / Valorar intercambio | Tausch bewerten | Valuta il tuo scambio | Avaliar troca | Beoordeel mijn huizenruil | Ocijenite svoju zamjenu | Bedøm dit boligbytte | Vurder boligbyttet ditt | Betygsätt ditt hembyte |
| Teams | Member Support / Member Support Team | service membres | Servicio de Asistencia | Mitgliedersupport / Mitgliedersupport-Team | Supporto Membri / team Supporto Membri | Suporte aos Membros | Ledenservice | Korisnička podrška | Medlemssupport | Medlemsstøtte | Medlemssupport |
| Teams | Marketing team | équipe Marketing | equipo de marketing | Marketingteam | Team Marketing | Equipa de Marketing | Marketingteam | Marketinški tim | Marketing team | Markedsføringsteam | Marketingteam |
| Teams | Product team | équipe Produit | equipo de producto | Produktteam | Team Prodotto | Equipa de Produto | Productteam | Produkt tim | Produkt team | Produktteam | Produktteam |
| Teams | Team of developers / dev team | équipe développement / nos développeurs | equipo de desarrollo / desarrolladores | Entwicklungsteam / Unsere Entwickler | I nostri sviluppatori | Equipa de Informática | Informaticateam | IT tim | Udviklingsteam | Utviklingsteam | Utvecklingsteam |
| Teams | Communication team | équipe communication | equipo de comunicación | Kommunikationsteam | team Comunicazione | Equipa de Comunicação | Communicatieteam | Komunikacijski tim | Kommunikationsteam | Kommunikasjonsteam | Kommunikationsteam |
| Teams | HR team / Human Resources | équipe RH / équipe ressources humaines | equipo de RRHH | Personalabteilung | team Risorse Umane | Equipa de RH / Recursos Humanos | HR team | Odjel ljudskih resursa | Personaleafdeling | HR-team / Personalavdeling | HR-team / Personalavdelning |
| Teams | The HomeExchange Team | L'équipe HomeExchange | El equipo de HomeExchange | Das HomeExchange-Team | Il team HomeExchange | A equipa HomeExchange | Het HomeExchange Team | The HomeExchange Team | HomeExchange-teamet | HomeExchange-teamet | HomeExchange-teamet |
| About payment | Payment method | moyen de paiement | Forma de pago | Zahlungsmethode | Metodo di pagamento | Método de pagamento | Betaalmethode | Metoda plaćanja | Betalingsmetode | Betalingsmetode | Betalningsmetod |
| First step of registering | Sign up, create your home listing / Sign up, create your listing | Inscrivez-vous, créez votre annonce | Regístrate, crea tu anuncio | Registrieren Sie sich und erstellen Sie Ihr Inserat. | Iscriviti, crea il tuo annuncio | Inscreva-se, crie a sua oferta | Registreer je en maak je profiel aan | Prijavite se, izradite oglas svojeg doma | Bliv medlem, opret din profil | Registrer deg, lag oppføringen din | Registrera dig, skapa din profil |
| Validity of the membership | Membership valid for 1-year | Adhésion valable un an | Suscripción válida durante 1 año | Mitgliedschaft ein Jahr gültig | L'abbonamento è valido per un anno | Filiação válida por 1 ano | Lidmaatschap geldig voor 1 jaar | Članstvo traje 1 godinu | Medlemskabet gælder 1 år | Medlemskapet er gyldig i ett år | Medlemskapet giltigt i 1 år |
| Finalization | Finalize my exchange | Finaliser mon échange | Registrar intercambio | Meinen Tausch finalisieren | Finalizzo il mio scambio | Finalizar a minha troca | Bevestig mijn huizenruil | Dovršite svoju zamjenu | Bekræft mit boligbytte | Bekreft boligbyttet mitt | Bekräfta mitt hembyte |
| Hostellerie concept | Nights | Nuitées | Noches / Noches de intercambio | Nächte / Übernachtungen | Pernottamenti | Noites | Nachten | Noći | Nætter | Netter | Nätter |
| GuestPoints exchange | GuestPoints exchange | échange contre GuestPoints | Intercambio con GuestPoints | GuestPoints-Tausch | Scambio con GuestPoints | Troca por GuestPoints | GuestPoints-ruil | Zamjena temeljena na GuestPoints | Udveksling af GuestPoints | Utveksling av GuestPoints | Hembyte med GuestPoints |
| HomeExchange guarantees | This exchange is covered by our HomeExchange guarantees. | Cet échange est couvert par les garanties HomeExchange / nos garanties. | Este intercambio está cubierto por el servicio HomeExchange. | Dieser Haustausch ist durch die Garantien von HomeExchange abgesichert. | Questo scambio è coperto dalle garanzie HomeExchange. | Esta troca esta coberta pelas garantias da HomeExchange. | Deze uitwisseling is gedekt door onze HomeExchange-garanties | Ova zamjena pokrivena je s našim HomeExchange garancijama. | Dette boligbytte er dækket af vores HomeExchange garanti. | Dette boligbyttet er dekket av våre HomeExchange-garantier. | Detta hembyte täcks av HomeExchanges garantier. |
| HomeExchange guarantees | Our guarantees | Nos garanties | Nuestras garantías | Unsere Garantien | Le nostre garanzie | As Nossas Garantias | Onze garanties | Naše garancije | Vores garantier | Våre garantier | Våra garantier |
| HomeExchange guarantees | Organize your vacations with peace of mind. HomeExchange guarantees protect your exchanges and your home. | Organisez vos vacances en toute sérénité. Les garanties HomeExchange protègent vos échanges et votre logement. | Planifica tus vacaciones con total tranquilidad. Las garantías de HomeExchange cubren todos tus intercambios en caso de cancelación. | Bereiten Sie Ihren Urlaub ganz entspannt vor. Die HomeExchange-Garantien schützen Ihren Haustausch im Falle einer Stornierung. | Organizza la tua vacanza in tutta tranquillità! Le garanzie di HomeExchange coprono tutti i tuoi scambi in caso di cancellazione. | Prepare as suas férias com tranquilidade. As garantias HomeExchange cobrem as suas trocas em caso de cancelamento. | Plan je vakantie zonder zorgen. De HomeExchange-garanties dekken je uitwisselingen in geval van annulering. | Organizirajte svoj odmor mirne duše. HomeExchange jamstva štite Vaše zamjene i Vaš dom. | Arranger dine ferier med ro i sindet. HomeExchange-garantier beskytter dine boligbytninger og dit hjem. | Planlegg feriene dine med full trygghet. HomeExchange garanterer beskyttelse av dine bytter og din bolig. | Planera dina semestrar med sinnesro. HomeExchange-garantier skyddar dina hembyten och ditt hem. |
| Deposit | Deposit | Caution | Fianza | Kaution | Cauzione | Caução | Waarborgsom | Polog | Depositum | Depositum | Deposition |
| Referral program | Refer / Invite your friends | Parrainez vos proches / ami·e·s | Invita a tus amigos | Werben Sie Freunde | Invita i tuoi amici | Convide os seus amigos | Beveel vrienden aan / nodig vrienden uit | Preporučite / Pozovite svoje prijatelje | Henvis / Inviter dine venner | Verv vennene dine | Bjud in dina vänner |
| Referral program | Referral program | Programme de parrainage | Programa de invitar amigos | Empfehlungsprogramm | Programma Invita i tuoi amici | Programa para convidar amigos | aanbevelingsprogramma | Sponzorstvo | Henvisningsprogram | Verveprogram | Hänvisningsprogram |
| Ambassadors (KEEP THE CAP) | (HomeExchange) Ambassadors | Ambassadeurs et Ambassadrices (HomeExchange) | embajadores (o embajadores y embajadoras, si es un saludo) | (HomeExchange) Botschafter | Ambassador | Embaixadores | Ambassadeurs | Ambasadori | (HomeExchange) Ambassadører | (HomeExchange) Ambassadører | (HomeExchange) Ambassadörer |
| Our customers (NEVER use customers/users/clients) | member / members | membre / membres | miembro / miembros | Mitglied / Mitglieder | membro/membri | membro/membros | lid/leden | član | medlem/medlemmer | medlem/medlemmer | medlem/medlemmar |
| Our customers (NEVER use customers/users/clients) | guest / guests | invité·e / invité·e·s | invitado/a / invitados | Gast / Gäste | ospite/ospiti | convidado/convidados | gast/gasten | gost | gæst/gæster | gjest/gjester | gäst/gäster |
| Our customers (NEVER use customers/users/clients) | host / hosts | hôte / hôte | anfitrión/a / anfitriones | Gastgeber | host/hosts | anfitrião/anfitriões | gastheer/-vrouw / gastgezin of host | domaćin | vært/værter | vert/verter | värd/värdar |
| Our customers (NEVER use customers/users/clients) | exchange partner | partenaire d'échange | compañero/a de intercambio | Tauschpartner | partner di scambio | parceiro de troca | Ruilpartner / uitwisselingspartner | zamjenski partner // partner u zamjeni | boligbytte partner | byttepartner | bytespartner |
| New member | New member | Nouveau·elle membre | Miembro nuevo | Neues Mitglied | Nuovo membro | Novo membro | Nieuw lid | Novi član | Nyt medlem | Nytt medlem | Ny medlem |
| Person who signed up but hasn't subscribed | Newcomer | Inscrit·e | Usuario registrado | Einsteiger | Iscritto/a | Novo utilizador | Nieuwkomer | Novi korisnik | Nybegynder | Nybegynner | Nykomling |
| Loyalty benefits | Loyalty benefits | Avantages fidélité | Beneficios de fidelidad | Treuevorteile | Vantaggi fedeltà | Vantagens de fidelidade | Beloningen voor je loyaliteit | Prednosti vjernosti | Loyalitetsfordele | Lojalitetsfordeler | Lojalitetsförmåner |
| LOYALTY BADGE | Loyalty badge | Badge fidélité | Insignia de fidelidad | Treueabzeichen | Badge fedeltà | Emblema de fidelização | Loyaliteitsbadge | Bedž vjernosti | Loyalitetsbadge | Lojalitetsmerke | Lojalitetsmärke |
| LOYALTY PRICE (long naming) | Reduced loyalty price | Prix réduit fidélité | Tarifa reducida de fidelidad | vergünstigter Treuebeitrag | Tariffa ridotta fedeltà | Preço reduzido de fidelidade | Verlaagd loyaliteitstarief | Snižena cijena zbog vjernosti | Reduceret loyalitetspris | Lojalitetsfordeler | Reducerat lojalitetspris |
| LOYALTY PRICE (short naming) | Loyalty price | Prix fidélité | Tarifa de fidelidad | Treuebeitrag | Tariffa fedeltà | Preço de fidelidade | Loyaliteitstarief | Cijena zbog vjernosti | Loyalitetspris | Redusert lojalitetspris | Lojalitetspris |
| GP bonus | 250 GuestPoints bonus | Bonus de 250 GuestPoints | 250 GuestPoints de regalo | 250 Bonus-GuestPoints | Bonus di 250 GuestPoints | 250 GuestPoints de bónus | 250 Bonus GuestPoints | 250 GuestPoints bonusa | 250 GuestPoints bonus | 250 GuestPoints-bonus | 250 GuestPoints-bonus |
| Home Manual | Home manual | Guide de maison | Manual de la casa | Infomappe zur Unterkunft | Manuale d'accoglienza | manual da casa | Huishandleidingen | Vodič kroz dom | Boligmanual | Bolighåndbok | Husmanual |
| Sponsor Badge | Referral badge | badge Parrain | insignia de Apadrinamiento | Empfehlungsabzeichen | badge Sponsor | Crachá de Patrocinador | Sponsor Badge | Značka sponzora | Henvisningsbadge | Vervemerke | Värvningsmärke |
| Sponsor | Referer | Parrain / Marraine | persona/amigo/a que te invitó a HomeExchange | Werbendes Mitglied | Persona che invita / che ti ha invitato | Responsável pelos convites / Pessoa que o(a) convidou | Sponsor | Osoba koja preporučuje | Henviser | Verver | Värvare |
| Sponsored person | Referee | Filleul·e | Amigos invitados | Geworbene Person | Persona invitata | Convidado(a) | Gesponsord lid | Osoba koju se preporučuje | Henviste/Henvisning | Vervet person | Värvad person / Värvning |
| Referral code | referral code | code de parrainage | código de invitación | Empfehlungscode | Codice invito | Código de referência | Sponsorcode | Kod za preporuku | Henvisningskode | Vervekode | Inbjudningskod |
| Hospitality exchange | Private room exchange | Echange en chambre privée | Intercambio de habitación | Gästezimmertausch | Scambio in ospitalità | Trocas de quarto privado | Uitwisseling van een kamer | Gostoprimstvo | Boligbytte i privat værelse | Bytte av privat rom | Privat rumsbyte |
| Our product | Our website | Notre site | Nuestra/La página web | Unsere Website | Il nostro sito | O nosso site | Onze website | Naša web stranica | Vores hjemmeside | Vår nettside | Vår hemsida |
| Our product | Our platform | Notre plateforme | Nuestra/La plataforma | Unsere Plattform | La nostra piattaforma | A nossa plataforma | Ons platform | Naša platforma | Vores platform | Vår plattform | Vår plattform |
| Our product | The website and the app | Le site et l'application / l'app | La página web y la aplicación | Die Website und die App | Il sito web e l'app | O site e a aplicação | De website en de app | Web stranica i aplikacija | Hjemmesiden og appen | Vår nettside og app | Hemsidan och appen |
| Promo code (use "promo code" only on payment page) | Special code | Code spécial | Código regalo | Gutscheincode / Aktionscode | Codice speciale | Código especial | kortingscode | poseban kod | Specialkode | Gavekode | Specialkod |
| Name of the sales team for members | Exchange expert | spécialiste des échanges | especialistas en intercambios | Haustausch-Experten | Esperti in scambi | Especialista em trocas | Huizenruil-expert | Stručnjak za zamjene | Bytte-ekspert | Bytteekspert | Hembytesexpert |
| Calendar filters | Any type | Tout type | Disponible para cualquier intercambio | Alle Tauscharten | Qualsiasi tipo di scambio | Qualquer tipo | Elk type | Bilo koji tip | Alle typer | Alle typer | Alla sorters hembyte |
| Calendar filters | Reciprocal Exchange | Echange réciproque | Intercambio recíproco | Wechselseitiger Tausch | Scambio reciproco | Troca Recíproca | Wederzijdse ruil | Recipročna zamjena | Gensidigt boligbytte | Gjensidig Bytte | Ömsesidigt hembyte |
| Calendar filters | GuestPoints Exchange | Contre GuestPoints | Intercambio con GuestPoints | GuestPoints-Tausch | In cambio di GuestPoints | Troca por GuestPoints | Ruil met GuestPoints | Zamjena sa GuestPoints bodovima | GuestPoints boligbytte | Veksling av GuestPoints | Hembyte för GuestPoints |
| CTA for page my Home | View the home listing | Voir l'annonce | Ver anuncio | Inserat ansehen | Vedere l'annuncio | Ver o anúncio | Bekijk de aanbieding | Pogledajte oglas | Se boligprofilen | Se annonsen | Visa profilen |
| Block "My home" | Completion | Complété à | Completo al | Vollständig zu | Completa al | Completa | Voltooid | Dovršetak | Udfyldt | Ferdigstillelse | Ifyllt |
| Block "My home" | Home ID | ID de la maison | Nº de anuncio | Identifikationsnummer der Unterkunft | ID della casa | ID da casa | Huis-ID | ID kuće/stana | Bolig-ID | Bolig-ID | Hemmets ID |
| Block "My home" | Home published | Maison en ligne | Casa publicada | Unterkunft online | Casa pubblicata | Casa publicada | Huis publiceren | Oglas objavljen | Bolig publiseret | Annonsen publisert | Hem publicerat |
| Verification | Verification | Vérification | Verificación | Verifizierung | Verifica | verificação | Verificatie | Provjera | Godkendelser | Verifiering | Verifiering |
| Proof of address | Proof of address | Jutificatif de domicile | Comprobante de dirección | Adressnachweis | Prova di indirizzo | Comprovativo de morada | Adresbewijs | Dokaz adrese | Adressebevis | Adressebevis | Adressbevis |
| Proof of identity | Proof of identity | Justificatif d'identité | Comprobante de identidad | Identitätsnachweis | Documento d'identità | Comprovativo de identidade | Identificatiebewijs | Dokaz identiteta | Identitetsbevis | Identitetsbevis | Identitetsbevis |
| Travelers feature | Travelers | Voyageurs | Grupo de viajeros | Reisegruppe | I viaggiatori | Grupo de viagem | Reisgezelschap | Putnici | Rejsegruppe | Reisefølge | Resenärer |
| Travelers feature | Create my traveling group | Créer mon groupe de voyageurs | Crear mi grupo de viajeros | Erstelle meine Reisegruppe | Creo il mio gruppo di viaggio | Criar o meu grupo de viagem | Creëer mijn reisgezelschap | Kreiraj moju grupu putnika | Opret min rejsegruppe | Opprett mitt reisefølge | Skapa mitt resesällskap |
| Type of residence | Primary residence | Résidence principale | Residencia principal | Hauptwohnsitz | Residenza principale | Residência principal | Thuisadres | Primarno boravište | Primær bolig | Primærbolig | Huvudbostad |
| Type of residence | Secondary residence | Résidence secondaire | Segunda residencia | Zweitwohnsitz | Residenza secondaria | Residência secundária | Vakantiehuis | Sekundarno boravište | Sekundær bolig | Sekundærbolig | Sekundär bostad |
| Surrounding tags | Close surroundings | Environnement direct | Entorno cercano | Umgebung | Dintorni | Arredores | Directe omgeving | Neposredna okolina | Nære omgivelser | Nære omgivelser | Nära omgivning |
| Surrounding tags | Countryside | Campagne | Campo | Auf dem Land | Campagna | Campo | Platteland / buitenaf | Ruralno okruženje | På landet | Landsbygd | Landsbygd |
| Surrounding tags | Mountains | Montagne | Montaña | In den Bergen | Montagna | Montanhas | Bergen | Planine | Bjerge | Fjell | Berg |
| Surrounding tags | Coastal | Bord de mer | Litoral | Am Meer | Mare | Litoral | Aan zee | More | Ved havet | Kyst | Hav |
| Surrounding tags | Lakes | Lac | Lago | An einem See | Lago | Lagos | Bij een meer | Jezero | Søer | Innsjøer | Sjöar |
| Surrounding tags | City | Ville | Ciudad | In der Stadt | Città | Cidade | Stad | Grad | By | By | Stad |
| Surrounding tags | Village | Village | Pueblo | In einem Dorf | Paese | Aldeia | Dorp | Selo | Landsby | Landsby | By |
| Surrounding tags | Isolated | Isolé | Aislado | Abgelegen | Isolata | Isolada | Afgelegen | Izolirano | Isoleret | Isolert | Isolerat |
| Surrounding tags | Island | Île | Isla | Auf einer Insel | Isola o penisola | Ilha | Eiland | Otok | Ø | Øy | Ö |
| Surrounding tags | River | Rivière | Río | An einem Fluss | Fiume | Rio | Rivier | Rijeka | Flod | Elv | Älv/flod |
| Private room | private room | chambre privée | habitación privada | Gästezimmer | Camera privata | quarto privado | privékamer | privatna soba | Privat værelse | Privat rom | Privat rum |
| Welcome GuestPoints | welcome GuestPoints | GuestPoints de bienvenue | GuestPoints de bienvenida | Willkommens-GuestPoints | GuestPoints di benvenuto | GuestPoints de boas-vindas | welkomst-GuestPoints | GuestPoints dobrodošlice | velkomst-GuestPoints | velkomst-GuestPoints | Välkomst-GuestPoints |
| Auto decline | Automatic decline | refus automatique | Rechazo automático | automatische Ablehnung | Rifiuto automatico | Rejeição automática | Automatische afwijzing | Automatsko odbijanje | Automatisk afvisning | Automatisk avslag | Automatisk avböjning |
| Auto decline | Automatically declined | Déclinée automatiquement | Rechazada automáticamente | Automatisch abgelehnt | Rifiutato in automatico | Automaticamente recusado | Automatisch afgewezen | Automatski odbijeno | Automatisk afvist | Avslått automatisk | Avböjt automatiskt |
| Auto decline | Declined exchanges | Demandes déclinées | Intercambios rechazados | Abgelehnte Tauschanfragen | Scambi rifiutati | Trocas recusadas | Afgewezen uitwisselingen | Odbijene zamjene | Afviste boligbytter | Avslåtte boligbytter | Avböjda hembyten |
| Auto decline | This exchange request was automatically declined. | Cette demande d'échange a été déclinée automatiquement. | Esta solicitud de intercambio se ha rechazado automáticamente. | Diese Haustauschanfrage wurde automatisch abgelehnt. | Questa richiesta di scambio è stata rifiutata automaticamente. | Este pedido de troca foi automaticamente recusado. | Dit uitwisselingsverzoek werd automatisch afgewezen. | Ovaj zahtjev za zamjenu je automatski odbijen. | Denne anmodning om boligbytte blev automatisk afvist. | Denne boligbytteforespørselen ble avslått automatisk. | Denna hembytesförfrågan har avböjts automatiskt. |
| Flexible search feature | Flexible dates filter | Filtre "dates flexibles" | Filtro "fechas flexibles" | Filter "Flexible Daten" | Filtro "date flessibili" | Filtro "datas flexíveis" | Filter "flexibele data" | Fleksibilni datumi | Fleksibelt datofilter / Fleksible datoer | Filter for fleksible datoer | Flexibla datum-filter / Flexibla datum |
| Type of exchange filters | Any type of exchange | Tout type d'échange | Cualquier tipo de intercambio | Jede Tauschanfrage | Qualsiasi tipo di scambio | Qualquer tipo de pedido de Troca | Elk type ruil | Sve vrste zamjene | Alle typer af boligbytte | Alla typer boligbytte | Alla typer av hembyte |
| Type of exchange filters | GuestPoints exchange | Echange contre GuestPoints | Intercambio con GuestPoints | GuestPoints-Tausch | Scambio in cambio di GuestPoints | Troca com GuestPoints | Ruil met GuestPoints | Zamjena sa GuestPoints bodovima | Boligbytte med GuestPoints | Boligbytte Mot GuestPoints | Hembyte för GuestPoints |
| Type of exchange filters | Reciprocal exchange | Echange réciproque | Intercambio recíproco | Wechselseitiger Tausch | Scambio reciproco | Troca Recíproca | Wederzijdse ruil | Recipročna zamjena | Gensidigt boligbytte | Gjensidig Boligbytte | Ömsesidigt hembyte |
| Reverse search feature | Reverse search | Recherche inversée | Búsqueda inversa | Umgekehrte Suche | Ricerca Inversa | Busca Invertida | Omgekeerd zoeken | Obrnuta pretraga | Omvendt søgning | Reversert Søk | Omvänd sökning |
| More filters | Quality | Qualité | Calidad | Qualität | Qualità | Qualidade | Kwaliteit | Kvaliteta | Kvalitet | Kvalitet | Kvalitet |
| More filters | Verified homes | Maisons vérifiées | Casas verificadas | Verifizierte Unterkunft | Case verificate | Casas verificadas | Geverifieerde huizen | Verificirani domovi | Godkendte boliger | Verifiserte boliger | Verifierade hem |
| More filters | Homes with pictures | Maisons avec photos | Casas con fotos | Unterkünfte mit Bildern | Case con foto | Casas com fotos | Huizen met foto's | Domovi sa slikama | Boliger med billeder | Boliger med bilder | Hem med bilder |
| More filters | Response rate >80% | Taux de réponse > 80% | Tasa de respuesta > 80% | Antwortrate über 80 % | Tasso di risposta > 80% | Taxa de resposta > 80% | Responspercentage > 80% | Stopa odgovora > 80% | Svarprocent > 80% | Svarprosent > 80% | Svarsfrekvens > 80 % |
| More filters | GuestPoints / night | GuestPoints / nuit | GuestPoints / noche | GuestPoints pro Nacht | GuestPoints / notte | GuestPoints / noite | GuestPoints / nacht | GuestPoints / noć | GuestPoints/døgn | GuestPoints / natt | GuestPoints/natt |
| More filters | Type of accommodation | Type de logement | Tipo de alojamiento | Art der Unterkunft | Tipo di casa | Tipo de alojamento | Type accommodatie | Tip doma | Boligtype | Boligtype | Typ av hem |
| More filters | House | Maison | Casa | Haus | Casa | Casa | Huis | Kuća | Hus | Hus | Hus |
| More filters | Apartment | Appartement | Piso | Wohnung | Appartamento | Apartamento | Appartement | Stan | Lejlighed | Leilighet | Lägenhet |
| More filters | Residence | Résidence | Vivienda | Art des Wohnsitzes | Residenza | Residência | Verblijfplaats | Dom | Bolig | Bolig | Hem |
| More filters | Primary | Principale | Principal | Hauptwohnsitz | Principale | Primária | Eerste | Moj dom | Primære bolig | Primær | Första |
| More filters | Secondary | Secondaire | Secundaria | Zweitwohnsitz | Secondaria | Secundária | Tweede | Druga | Anden | Sekundær | Andra |
| More filters | Size | Taille | Tamaño | Größe | Dimensione | Tamanho | Grootte | Veličina | Størrelse | Størrelse | Storlek |
| More filters | Bedrooms | Chambres | Dormitorios | Schlafzimmer | Stanze | Quartos | Kamers | Spavaće sobe | Værelser | Soverom | Sovrum |
| More filters | Bathrooms | Salles de bain | Cuartos de baños | Badezimmer | Bagno | WC's | Badkamer | Kupaonica | Badeværelse | Baderom | Badrum |
| More filters | No temporary beds | Pas de lits d'appoint | No hay camas supletorias | Ausziehcouch | Divano letto | Nenhuma cama não fixa | Geen extra bedden | Bez sklopivih kreveta | Ingen ekstrasenge | Ingen ekstrasenger | Inga extrasängar |
| More filters | Amenities | Équipements | Comodidades | Ausstattungsmerkmale | Servizi | Amenidades | Uitrusting | Oprema | Faciliteter | Fasiliteter | Faciliteter |
| More filters | Accessibility | Accessibilité | Accesibilidad | Barrierefreiheit | Accessibilità | Acessibilidade | Toegankelijkheid | Dostupnost | Tilgængelighed | Tilgjengelighet | Tillgänglighet |
| More filters | Disabled access | Accès personnes à mobilité réduite | Acceso para personas con movilidad reducida | Behindertengerecht | Accesso per disabili | Acesso a pessoas com deficência | Toegang voor gehandicapten | Pristup osobama s invaliditetom | Handicapvenligt | Tilrettelagt tilgang | Tillgänglighetsanpassat |
| More filters | Last minute | Dernière minute | Último minuto | Last minute | Last minute | Última hora | Last minute | Last minute | Last minute | I siste minutt | Sista minuten |
| Cleaning fees | Cleaning fees | Frais de ménage | Gastos de limpieza | Reinigungskosten | Spese di pulizia | Taxas de limpeza | Schoonmaakkosten | Naknada za čišćenje | Rengøringsgebyr | Rengjøringsgebyr | Städavgifter |
| Terms of Use | Violation |  | incumplimiento | Verstoß | Violazione | Infração | Overtreding | Kršenje | Overtrædelse | Overtredelse | Överträdelse |
| Favorite folders | Favorite folder | Dossier de favoris | Carpeta de favoritos | Favoriten-Ordner | Cartella dei preferiti | Pasta de favoritos | Map met favoriete huizen | Mapa s omiljenima | Mappe med favoritter | Favoritter-mappen | Favoritmapp |
| Response rate | Response rate | Réactivité / Niveau de réactivité | tasa de respuesta | Antwortrate | Tasso di risposta | Taxa de resposta | Reactiesnelheid | Stopa odgovora | Svartid | Svarprosent | Svarsprocent |
| Travel wishlist | Travel wishlist | Projets de voyage | Proyectos de viaje | Reiseprojekte | Progetti di viaggio | ideias de viagens | Reisplannen | Planovi za putovanje | Rejseliste | Reiseplaner | Reselista |
| Responsible travel pledge | Responsible travel pledge | Charte de voyage responsable | Carta de compromiso para viajar de manera consciente | Ein Versprechen für verantwortungsbewusstes Reisen | Dichiarazione del viaggiatore responsabile | Compromisso de viajante responsável | Belofte van een verantwoorde reiziger | Povelja o odgovornom putovanju | Løfte om ansvarlig rejse | Et løfte om ansvarlig reise | Löfte om ansvarsfullt resande |
| HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days | HomeExchange Days |
| Only used on HomeExchange Days | meetup | rencontre | encuentro | Treffen | incontro | encontro | bijeenkomst | sastanak | meetup | meetup | träff |
| The Pets Corner | The Pets Corner | Le Coin des Animaux | El Rincón de las Mascotas | - | - | - | - | - | - | - | - |
"""

SYSTEM_PROMPT += GLOSSARY_TABLE
PROOFREADER_PROMPT += GLOSSARY_TABLE

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Translation Assistant — HomeExchange</title>
<style>
  :root {
    --bg: #f4f5f8;
    --bg-card: #ffffff;
    --border: #e3e6ea;
    --text: #16181d;
    --muted: #6b7280;
    --accent: #fbb341;
    --accent-hover: #e8992c;
    --accent-text: #b45309;
    --accent2: #2f6b46;
    --danger: #dc2626;
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
  .badge { font-size: 12px; background: rgba(251,179,65,0.12); color: var(--accent-text); border: 1px solid rgba(251,179,65,0.25); border-radius: 100px; padding: 3px 10px; }

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
  textarea:focus { border-color: rgba(251,179,65,0.4); }
  textarea::placeholder { color: var(--muted); }

  .output-box {
    flex: 1;
    min-height: 220px;
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
  .output-box.streaming { border-color: rgba(251,179,65,0.3); }
  /* Result tabs */
  .result-tabs {
    display: flex; gap: 4px; flex-shrink: 0;
    border-bottom: 1px solid var(--border); padding-bottom: 0;
  }
  .result-tab {
    background: transparent; border: none; border-bottom: 2px solid transparent;
    color: var(--muted); font-size: 13px; font-weight: 700; padding: 6px 16px;
    cursor: pointer; transition: all 0.15s; border-radius: 6px 6px 0 0;
    margin-bottom: -1px; letter-spacing: 0.5px;
  }
  .result-tab:hover { color: var(--text); background: rgba(251,179,65,0.04); }
  .result-tab.active { color: var(--accent-text); border-bottom-color: var(--accent-text); background: transparent; }
  .result-panel { display: none; }
  .result-panel.active { display: block; }
  .output-box table { border-collapse: collapse; width: 100%; margin: 16px 0; }
  .output-box th, .output-box td { border: 1px solid var(--border); padding: 10px 14px; text-align: left; vertical-align: top; }
  .output-box th { background: rgba(251,179,65,0.06); color: var(--accent-text); font-size: 13px; }
  .output-box strong { color: #000000; }
  .output-box code { background: rgba(0,0,0,0.06); padding: 2px 6px; border-radius: 4px; font-size: 13px; }
  .output-box h2 { font-size: 17px; font-weight: 700; color: var(--accent-text); margin: 20px 0 8px; }
  .output-box h3 { font-size: 13px; font-weight: 700; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; margin: 20px 0 8px; padding: 8px 12px; background: rgba(0,0,0,0.04); border-left: 3px solid var(--border); border-radius: 0 6px 6px 0; }
  .output-box hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
  .output-box blockquote { border-left: 3px solid var(--accent-hover); margin: 12px 0; padding: 8px 16px; background: rgba(251,179,65,0.04); border-radius: 0 8px 8px 0; color: var(--muted); font-size: 14px; }
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
  select:focus { border-color: rgba(251,179,65,0.4); }

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
  button.btn-new { background: #1bc9cf; color: #063638; }
  button.btn-new:hover { background: #12acb2; }

  .lang-row {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }
  .lang-group { display: flex; align-items: center; gap: 6px; }
  .lang-label { font-size: 12px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }
  .lang-arrow { color: var(--accent-text); font-size: 18px; font-weight: 700; padding: 0 2px; }
  .lang-checks { display: flex; gap: 6px; }
  .lang-check {
    display: flex; align-items: center; gap: 5px;
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 100px; padding: 5px 12px; cursor: pointer;
    font-size: 13px; font-weight: 600; color: var(--muted);
    transition: all 0.15s; user-select: none;
  }
  .lang-check:has(input:checked) { border-color: var(--accent-hover); color: var(--accent-text); background: rgba(251,179,65,0.08); }
  .lang-check input { display: none; }
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
  .detect-btn:hover { border-color: var(--accent-hover); color: var(--accent-text); background: rgba(251,179,65,0.06); }
  .detect-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .controls-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
  .detect-confirm {
    font-size: 13px; padding: 5px 12px;
    background: rgba(47,107,70,0.08);
    border: 1px solid rgba(47,107,70,0.25);
    border-radius: 6px; color: var(--accent2);
  }
  .detect-confirm.hidden { display: none; }
  .detect-confirm.changed {
    background: rgba(180,83,9,0.08);
    border-color: rgba(180,83,9,0.3);
    color: #b45309;
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
  .proof-header:hover { background: rgba(251,179,65,0.04); }
  .proof-title { font-size: 13px; font-weight: 600; color: var(--accent-text); letter-spacing: 0.5px; text-transform: uppercase; }
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
  .proof-body textarea:focus { border-color: rgba(251,179,65,0.4); }
  .proof-controls { display: flex; gap: 10px; align-items: center; }

  /* Results table FAB button */
  .results-fab {
    position: fixed; bottom: 24px; right: 24px; z-index: 200;
    background: var(--accent); color: #1a1200;
    border: none; border-radius: 100px;
    font-size: 13px; font-weight: 700; padding: 9px 18px;
    cursor: pointer; box-shadow: 0 4px 16px rgba(251,179,65,0.35);
    transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
    white-space: nowrap;
  }
  .results-fab:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 6px 20px rgba(251,179,65,0.45); }

  /* Results modal */
  .results-modal-backdrop {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.6); z-index: 300; backdrop-filter: blur(3px);
  }
  .results-modal-backdrop.open { display: block; }
  .results-modal {
    display: none; position: fixed;
    top: 50%; left: 50%; transform: translate(-50%, -50%);
    z-index: 400; width: min(95vw, 1500px); max-height: 85vh;
    background: var(--bg-card); border: 1px solid rgba(251,179,65,0.25);
    border-radius: 16px; flex-direction: column; overflow: hidden;
    box-shadow: 0 24px 60px rgba(0,0,0,0.18);
  }
  .results-modal.open { display: flex; }
  .results-modal-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .results-modal-title { font-size: 15px; font-weight: 700; color: var(--accent-text); }
  .results-modal-header .btn-new { font-size: 12px; padding: 7px 14px; }
  .results-modal-close {
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: 6px; font-size: 14px; padding: 4px 10px; cursor: pointer;
  }
  .results-modal-close:hover { color: var(--text); border-color: var(--text); background: transparent; }
  .results-modal-body { overflow: auto; padding: 20px; }
  /* Combined multi-language table: let columns breathe and scroll horizontally
     instead of squeezing every language into the modal width (which forced
     mid-word breaks, e.g. "Field" wrapping to "F/i/e/l/d"). */
  .results-modal-body table { width: max-content; min-width: 100%; table-layout: auto; }
  .results-modal-body th, .results-modal-body td {
    min-width: 150px; max-width: 320px;
    white-space: normal; word-break: normal; overflow-wrap: break-word;
  }
  .results-modal-body th:first-child, .results-modal-body td:first-child {
    min-width: 44px; max-width: 44px; width: 44px;
    white-space: nowrap; text-align: center;
  }
  .results-modal-body th:nth-child(2), .results-modal-body td:nth-child(2) {
    min-width: 220px; max-width: 360px;
  }
  .results-modal-body thead th, .results-modal-body tr:first-child th {
    position: sticky; top: -20px; z-index: 2;
    background: var(--bg-card); box-shadow: 0 1px 0 var(--border);
  }

  /* Make right panel scrollable to fit proofreader */
  .panel { overflow-y: auto; }

  /* TSV banner */
  .tsv-banner {
    display: none; align-items: center; gap: 10px; flex-wrap: wrap;
    background: rgba(251,179,65,0.07); border: 1px solid rgba(251,179,65,0.25);
    border-radius: 10px; padding: 10px 14px; font-size: 13px; flex-shrink: 0;
  }
  .tsv-banner.visible { display: flex; }
  .tsv-icon { font-size: 16px; flex-shrink: 0; }
  .tsv-selectors { display: flex; gap: 12px; margin-left: auto; }
  .tsv-selectors label { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .tsv-selectors select { background: var(--bg-card); border: 1px solid var(--border); color: var(--text); font-size: 12px; padding: 4px 8px; border-radius: 6px; cursor: pointer; }
  .tsv-clear { background: transparent; border: none; color: var(--muted); font-size: 13px; cursor: pointer; padding: 2px 4px; border-radius: 4px; flex-shrink: 0; }
  .tsv-clear:hover { color: var(--text); background: transparent; }
  .tsv-header-toggle { display: flex; align-items: center; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; }
  .tsv-header-toggle input { accent-color: var(--accent); cursor: pointer; }

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
  .export-btn:hover { border-color: var(--accent-hover); color: var(--accent-text); background: rgba(251,179,65,0.06); }
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
  .key-option:hover { border-color: var(--accent-hover); }
  .key-option.selected { border-color: var(--accent-hover); background: rgba(251,179,65,0.05); }
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
  .key-input-wrap input:focus { border-color: rgba(251,179,65,0.5); }
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

  /* ── Mobile ─────────────────────────────────────────────────── */
  @media (max-width: 768px) {
    html, body { height: auto; min-height: 100vh; }
    body { height: auto; }

    header { padding: 14px 16px; flex-wrap: wrap; gap: 10px; }
    #headerTitle { display: none; }

    main { flex-direction: column; overflow: visible; height: auto; }

    .panel { padding: 16px; gap: 12px; overflow: visible; min-height: auto; }
    .panel + .panel { border-left: none; border-top: 1px solid var(--border); }

    #inputText { min-height: 160px; max-height: 260px; }
    .output-box { min-height: 180px; max-height: none; overflow: visible; }

    .lang-row { flex-wrap: wrap; gap: 10px; }
    .lang-checks { flex-wrap: wrap; }
    .tsv-banner { flex-wrap: wrap; }
    .tsv-selectors { flex-wrap: wrap; gap: 8px; margin-left: 0; width: 100%; }
    .export-bar { flex-wrap: wrap; }
    .proof-body textarea { min-height: 100px; max-height: 180px; }
    .key-card { width: 90vw; padding: 28px 20px; }
    .ui-lang-toggle { margin-left: 0; }
    header a[href="/logout"] { display: none; }
  }

  @media (max-width: 400px) {
    .lang-check { padding: 5px 10px; font-size: 12px; }
    button { font-size: 13px; padding: 10px 16px; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">
    <span>home<strong>exchange</strong> <span style="color:var(--muted);font-weight:400">translate</span></span>
  </div>
  <div class="badge">EN · FR · ES · IT · DE · PT · NL · DA · SV · NO · HR</div>
  <span id="headerTitle" style="margin-left:auto;font-size:13px;color:var(--muted)"></span>
  <div class="ui-lang-toggle">
    <button id="btnLangEN" class="ui-lang-btn active" onclick="setUiLang('en')">EN</button>
    <button id="btnLangFR" class="ui-lang-btn" onclick="setUiLang('fr')">FR</button>
  </div>
  <a href="/logout" style="font-size:12px;color:var(--muted);text-decoration:none;margin-left:12px;white-space:nowrap" onmouseover="this.style.color='var(--text)'" onmouseout="this.style.color='var(--muted)'">Sign out</a>
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
            <option value="IT">IT</option>
            <option value="DE">DE</option>
            <option value="PT">PT</option>
            <option value="NL">NL</option>
            <option value="DA">DA</option>
            <option value="SV">SV</option>
            <option value="NO">NO</option>
            <option value="HR">HR</option>
          </select>
          <button class="detect-btn" id="btnDetect" onclick="detectLang()" data-i18n="btnDetect">⟳</button>
        </div>
        <span class="lang-arrow">→</span>
        <div class="lang-group">
          <label class="lang-label" data-i18n="labelTarget"></label>
          <div class="lang-checks" id="targetLangs">
            <label class="lang-check"><input type="checkbox" value="FR" checked> FR</label>
            <label class="lang-check"><input type="checkbox" value="EN"> EN</label>
            <label class="lang-check"><input type="checkbox" value="ES"> ES</label>
            <label class="lang-check"><input type="checkbox" value="IT"> IT</label>
            <label class="lang-check"><input type="checkbox" value="DE"> DE</label>
            <label class="lang-check"><input type="checkbox" value="PT"> PT</label>
            <label class="lang-check"><input type="checkbox" value="NL"> NL</label>
            <label class="lang-check"><input type="checkbox" value="DA"> DA</label>
            <label class="lang-check"><input type="checkbox" value="SV"> SV</label>
            <label class="lang-check"><input type="checkbox" value="NO"> NO</label>
            <label class="lang-check"><input type="checkbox" value="HR"> HR</label>
          </div>
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
        <div class="spinner" id="spinner"></div>
        <button onclick="runTranslate()" id="btnTranslate" data-i18n="btnTranslate"></button>
        <button class="btn-new" onclick="newTranslation()" data-i18n="btnNew"></button>
      </div>
      <div class="controls-actions">
        <div id="detectConfirm" class="detect-confirm hidden"></div>
        <button class="export-btn" onclick="document.getElementById('fileImport').click()" data-i18n="btnImport"></button>
        <input type="file" id="fileImport" accept=".md,.csv,.txt" style="display:none" onchange="importFile(event)"/>
        <button class="clear" onclick="clearAll()" data-i18n="btnClear"></button>
      </div>
    </div>

    <div class="tsv-banner" id="tsvBanner">
      <span class="tsv-icon">📊</span>
      <span id="tsvInfo"></span>
      <div class="tsv-selectors">
        <label>Source
          <select id="tsvSource"><option value="0">Col A</option><option value="1">Col B</option></select>
        </label>
        <label>Context
          <select id="tsvContext"><option value="-1">None</option><option value="1">Col B</option><option value="0">Col A</option></select>
        </label>
        <label class="tsv-header-toggle">
          <input type="checkbox" id="tsvHasHeader" checked onchange="renderTsvPreview()">
          Header row
        </label>
      </div>
      <button class="tsv-clear" onclick="clearTsv()" title="Dismiss">✕</button>
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
        <div class="result-tabs" id="proofTabs" style="display:none"></div>
        <textarea id="proofInput" data-i18n-placeholder="proofPlaceholder"></textarea>
        <div class="proof-controls">
          <button onclick="runProofread()" id="btnProofread" data-i18n="btnProofread"></button>
          <button class="clear" onclick="clearProofread()" data-i18n="btnClear"></button>
        </div>
        <div class="hx-loading" id="hxProofLoading">
          <svg class="hx-mark" id="proofMark" width="56" height="50" viewBox="0 0 120 100" xmlns="http://www.w3.org/2000/svg">
            <path d="M 54,50 C 50,40 40,28 22,14 C 17,19 22,24 30,31 C 38,38 46,44 49,50 C 46,56 38,62 30,69 C 22,76 17,81 22,86 C 40,72 50,60 54,50 Z" fill="#fbb341"/>
            <path d="M 66,50 C 70,40 80,28 98,14 C 103,19 98,24 90,31 C 82,38 74,44 71,50 C 74,56 82,62 90,69 C 98,76 103,81 98,86 C 80,72 70,60 66,50 Z" fill="#fbb341"/>
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


    <!-- Results table fixed button -->
    <button class="results-fab" id="resultsFab" style="display:none" onclick="openResultsModal()">
      Results table ↗
    </button>

    <!-- Results table modal -->
    <div class="results-modal-backdrop" id="resultsModalBackdrop" onclick="closeResultsModal()"></div>
    <div class="results-modal" id="resultsModal">
      <div class="results-modal-header">
        <span class="results-modal-title">Results table</span>
        <div style="display:flex;gap:10px;align-items:center">
          <button class="export-btn" id="btnCombinedCopy" onclick="copyCombinedTSV()">📋 Copy as TSV</button>
          <button class="btn-new" onclick="newTranslation()" data-i18n="btnNew"></button>
          <button class="results-modal-close" onclick="closeResultsModal()">✕</button>
        </div>
      </div>
      <div class="results-modal-body">
        <div class="output-box" id="combinedOutput" style="max-height:none;overflow:visible"></div>
      </div>
    </div>

    <div class="hx-loading" id="hxLoading">
      <svg class="hx-mark" id="translationMark" width="72" height="64" viewBox="0 0 120 100" xmlns="http://www.w3.org/2000/svg">
        <!-- Left element: body pointing right, two prongs/tails on the left -->
        <path d="
          M 54,50
          C 50,40 40,28 22,14
          C 17,19 22,24 30,31
          C 38,38 46,44 49,50
          C 46,56 38,62 30,69
          C 22,76 17,81 22,86
          C 40,72 50,60 54,50 Z
        " fill="#fbb341"/>
        <!-- Right element: mirror -->
        <path d="
          M 66,50
          C 70,40 80,28 98,14
          C 103,19 98,24 90,31
          C 82,38 74,44 71,50
          C 74,56 82,62 90,69
          C 98,76 103,81 98,86
          C 80,72 70,60 66,50 Z
        " fill="#fbb341"/>
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
    const mark = document.getElementById('translationMark');
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
    const mark = document.getElementById('translationMark');
    if (mark) mark.style.transform = '';
  }

  const I18N = {
    en: {
      headerTitle: 'HomeExchange Translation Assistant',
      panelSource: 'Content to translate',
      panelOutput: 'Translation',
      placeholder: 'The translation will appear here with the source / target table and QA checklist.',
      btnDetect: '⟳ Detect',
      btnTranslate: 'Translate & Proofread',
      btnNew: '🔄 New translation',
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
      labelTarget: 'Target',
      loadingText: 'Translating…',
      exportCopy: 'Copy',
      exportCopied: 'Copied!',
      btnImport: '📂 Import',
      importError: 'Unsupported file. Use .md or .csv',
      proofTitle: 'Proofreader — auto',
      proofPlaceholder: 'Paste or edit the text to proofread here…',
      btnProofread: '✦ Re-run',
      proofLoadingText: 'Reviewing…',
    },
    fr: {
      headerTitle: 'Assistant de traduction HomeExchange',
      panelSource: 'Contenu à traduire',
      panelOutput: 'Traduction',
      placeholder: 'La traduction apparaîtra ici avec le tableau source / cible et la checklist QA.',
      btnDetect: '⟳ Détecter',
      btnTranslate: 'Traduire & Relire',
      btnNew: '🔄 Nouvelle traduction',
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
      labelTarget: 'Cible',
      loadingText: 'Traduction en cours…',
      exportCopy: 'Copier',
      exportCopied: 'Copié !',
      btnImport: '📂 Importer',
      importError: 'Fichier non supporté. Utilise .md ou .csv',
      proofTitle: 'Proofreader — auto',
      proofPlaceholder: 'Colle ou édite ici le texte à relire…',
      btnProofread: '✦ Relancer',
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
  let lastResults = []; // [{lang, result}] — per-language raw outputs

  function getActiveResult() {
    if (!lastResults.length) return lastRawOutput;
    if (lastResults.length === 1) return lastResults[0].result;
    // Multi-language: return the active tab's result
    const activeTab = document.querySelector('#output .result-tab.active');
    if (!activeTab) return lastResults[0].result;
    const match = lastResults.find(r => r.lang === activeTab.textContent);
    return match ? match.result : lastResults[0].result;
  }

  // ── Proofreader ────────────────────────────────────────────────
  let lastProofOutput = '';
  let _proofRAF = null, _proofWordTimer = null, _proofDirTimer = null;
  let proofLangs = []; // [{lang, text}] when multi-language
  let proofResults = {}; // {lang: [{field, original, improved}]}
  let translationSourceRows = []; // [{field, source}] — original source text per field

  function parseProofTable(raw) {
    const improved = extractImprovedVersion(raw);
    const lines = improved.split('\\n');
    const rows = [];
    let headerSkipped = false;
    let tableStarted = false;
    for (const line of lines) {
      const tr = line.trim();
      if (!tr.startsWith('|')) {
        if (tableStarted) break; // stop at end of first table — ignore any later table (e.g. QA checklist)
        continue;
      }
      tableStarted = true;
      if (tr.match(/^\\|[-| :]+\\|$/)) continue;
      const cells = tr.split('|').slice(1,-1).map(c => c.trim().replace(/\\*\\*(.+?)\\*\\*/g,'$1'));
      if (!headerSkipped) { headerSkipped = true; continue; }
      if (cells.length >= 3) rows.push({ field: cells[0], original: cells[1], improved: cells[2] });
      else if (cells.length === 2) rows.push({ field: cells[0], original: '', improved: cells[1] });
    }
    return rows;
  }

  function updateCombinedSection() {
    const langs = Object.keys(proofResults);
    if (langs.length < 2) { document.getElementById('resultsFab').style.display = 'none'; return; }

    const firstRows = proofResults[langs[0]];
    if (!firstRows || !firstRows.length) return;

    // Build combined markdown table
    let mdTable = '| Field | Source |' + langs.map(l => ` ${l} |`).join('') + '\\n';
    mdTable += '|---|---|' + langs.map(() => '---|').join('') + '\\n';

    firstRows.forEach((row, i) => {
      const srcText = translationSourceRows[i]?.source ?? row.original;
      let line = '| ' + row.field + ' | ' + srcText + ' |';
      langs.forEach(l => {
        const r = proofResults[l]?.[i];
        line += ' ' + (r ? r.improved : '') + ' |';
      });
      mdTable += line + '\\n';
    });

    renderMarkdown(document.getElementById('combinedOutput'), mdTable);
    document.getElementById('resultsFab').style.display = '';
    openResultsModal(); // auto-open when ready
  }

  function openResultsModal() {
    document.getElementById('resultsModal').className = 'results-modal open';
    document.getElementById('resultsModalBackdrop').className = 'results-modal-backdrop open';
  }

  function closeResultsModal() {
    document.getElementById('resultsModal').className = 'results-modal';
    document.getElementById('resultsModalBackdrop').className = 'results-modal-backdrop';
  }

  function tsvEscapeCell(cell) {
    // Google Sheets/Excel split a pasted TSV row on every raw \\t or \\n. Any cell
    // containing one (multi-paragraph fields, bulleted lists) must be quoted per
    // RFC 4180, or it silently explodes into extra rows on paste.
    const s = String(cell ?? '');
    return /[\\t\\n"]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function copyCombinedTSV() {
    const langs = Object.keys(proofResults);
    if (!langs.length) return;
    const firstRows = proofResults[langs[0]];
    const header = ['Field', 'Source', ...langs].join('\\t');
    const rows = firstRows.map((row, i) => {
      const srcText = translationSourceRows[i]?.source ?? row.original;
      const cols = [row.field, srcText, ...langs.map(l => proofResults[l]?.[i]?.improved || '')];
      return cols.map(tsvEscapeCell).join('\\t');
    });
    const tsv = [header, ...rows].join('\\n');
    navigator.clipboard.writeText(tsv).then(() => {
      const btn = document.getElementById('btnCombinedCopy');
      const orig = btn.textContent;
      btn.textContent = '✓ Copied!';
      btn.className = 'export-btn success';
      setTimeout(() => { btn.textContent = orig; btn.className = 'export-btn'; }, 2000);
    });
  }

  function extractTranslatedTextLabeled(raw) {
    // Like extractTranslatedText but keeps "Label: text" format for proofreader context
    const lines = raw.split('\\n');
    const parts = [];
    let headerSkipped = false;
    let tableStarted = false;
    for (const line of lines) {
      const tr = line.trim();
      if (!tr.startsWith('|')) {
        if (tableStarted) break; // stop at end of first table — ignore any later table (e.g. QA checklist)
        continue;
      }
      tableStarted = true;
      if (tr.match(/^\\|[-| :]+\\|$/)) continue;
      const cells = tr.split('|').slice(1,-1).map(c => c.trim().replace(/\\*\\*(.+?)\\*\\*/g,'$1').replace(/`([^`]+)`/g,'$1'));
      if (!headerSkipped) { headerSkipped = true; continue; }
      if (cells.length < 2) continue;
      const label = cells[0];
      const target = cells[cells.length - 1];
      const metaLabels = ['note','meta','type','source lang','target lang','source language','target language'];
      if (metaLabels.includes(label.toLowerCase())) continue;
      if (!target || target === '' || target.startsWith('[') || /^[✅❌⚠️🔴🟡🟢]/.test(target)) continue;
      parts.push(label ? label + ': ' + target : target);
    }
    return parts.length > 0 ? parts.join('\\n') : extractTranslatedText(raw);
  }

  function extractSourceColumn(raw) {
    // Extract the source column (col 1) from the translator's output table: | Field | Source | Target |
    const lines = raw.split('\\n');
    const rows = [];
    let headerSkipped = false;
    let tableStarted = false;
    for (const line of lines) {
      const tr = line.trim();
      if (!tr.startsWith('|')) {
        if (tableStarted) break; // stop at end of first table — ignore any later table (e.g. QA checklist)
        continue;
      }
      tableStarted = true;
      if (tr.match(/^\\|[-| :]+\\|$/)) continue;
      const cells = tr.split('|').slice(1,-1).map(c => c.trim().replace(/\\*\\*(.+?)\\*\\*/g,'$1').replace(/`([^`]+)`/g,'$1'));
      if (!headerSkipped) { headerSkipped = true; continue; }
      if (cells.length < 2) continue;
      const label = cells[0];
      const source = cells[1];
      const metaLabels = ['note','meta','type','source lang','target lang','source language','target language'];
      if (metaLabels.includes(label.toLowerCase())) continue;
      if (!source || source === '' || source.startsWith('[') || /^[✅❌⚠️🔴🟡🟢]/.test(source)) continue;
      rows.push({ field: label, source });
    }
    return rows;
  }

  function buildProofTabs(results) {
    const tabBar  = document.getElementById('proofTabs');
    const textarea = document.getElementById('proofInput');
    proofLangs = results.map(({ lang, result }) => ({
      lang, text: extractTranslatedTextLabeled(result)  // keep labels for table output
    }));
    // Capture original source text from the first translation result for the combined table
    translationSourceRows = results.length > 0 ? extractSourceColumn(results[0].result) : [];

    if (proofLangs.length <= 1) {
      // Single language — use plain textarea, no tabs
      tabBar.style.display = 'none';
      textarea.style.display = '';
      textarea.value = proofLangs[0]?.text || '';
      return;
    }

    // Multiple languages — build tabs
    tabBar.style.display = 'flex';
    tabBar.innerHTML = '';
    textarea.value = proofLangs[0].text;

    proofLangs.forEach(({ lang, text }, i) => {
      const tab = document.createElement('button');
      tab.className = 'result-tab' + (i === 0 ? ' active' : '');
      tab.textContent = lang;
      tab.onclick = () => {
        tabBar.querySelectorAll('.result-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        textarea.value = text;
        // Clear previous result when switching tab
        document.getElementById('proofOutput').style.display = 'none';
        document.getElementById('proofExportBar').className = 'export-bar';
        lastProofOutput = '';
      };
      tabBar.appendChild(tab);
    });
  }

  function getActiveProofLang() {
    const active = document.querySelector('#proofTabs .result-tab.active');
    return active ? active.textContent : null;
  }

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
    document.getElementById('proofTabs').style.display = 'none';
    document.getElementById('proofTabs').innerHTML = '';
    document.getElementById('proofInput').style.display = '';
    proofLangs = [];
    lastProofOutput = '';
    proofResults = {};
    document.getElementById('resultsFab').style.display = 'none';
    closeResultsModal();
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

  async function streamProofread(text) {
    const resp = await fetch('/proofread', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, api_key: activeKey })
    });
    if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || resp.statusText); }
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
    return full;
  }

  async function runProofread() {
    if (!activeKey) { changeKey(); return; }

    const loader = document.getElementById('hxProofLoading');
    const output = document.getElementById('proofOutput');
    const btn    = document.getElementById('btnProofread');
    const loadTxt = document.getElementById('proofLoadingText');

    // Determine which languages to proofread
    const langsToProof = proofLangs.length > 0 ? proofLangs : null;
    const isSingle = !langsToProof || langsToProof.length <= 1;

    // If single language / plain text, just use current textarea
    const singleText = isSingle ? document.getElementById('proofInput').value.trim() : null;
    if (isSingle && !singleText) { alert(t('alertNoText')); return; }

    btn.disabled = true;
    output.style.display = 'none';
    loader.className = 'hx-loading visible';
    document.getElementById('proofExportBar').className = 'export-bar';
    proofResults = {};
    startProofAnim();

    const tabBar = document.getElementById('proofTabs');

    try {
      if (isSingle) {
        // Single language — run once
        if (loadTxt) loadTxt.textContent = t('proofLoadingText');
        const full = await streamProofread(singleText);
        lastProofOutput = full;
        const lang = getActiveProofLang() || 'Text';
        proofResults[lang] = parseProofTable(full);
        stopProofAnim();
        loader.className = 'hx-loading';
        output.style.display = '';
        renderMarkdown(output, full);
        output.scrollTop = 0;
        document.getElementById('proofExportBar').className = 'export-bar visible';
      } else {
        // Multiple languages — run sequentially, update tabs as we go
        let lastFull = '';
        for (let i = 0; i < langsToProof.length; i++) {
          const { lang, text } = langsToProof[i];
          if (loadTxt) loadTxt.textContent = `${lang}… (${i+1}/${langsToProof.length})`;

          // Switch to this tab visually
          tabBar.querySelectorAll('.result-tab').forEach((t, ti) => {
            t.className = 'result-tab' + (ti === i ? ' active' : '');
          });
          document.getElementById('proofInput').value = text;

          const full = await streamProofread(text);
          lastFull = full;
          proofResults[lang] = parseProofTable(full);
        }

        // Show result for last language; all tabs are now proofread
        lastProofOutput = lastFull;
        stopProofAnim();
        loader.className = 'hx-loading';
        output.style.display = '';
        renderMarkdown(output, lastFull);
        output.scrollTop = 0;
        document.getElementById('proofExportBar').className = 'export-bar visible';
        updateCombinedSection();
      }
    } catch (e) {
      stopProofAnim();
      loader.className = 'hx-loading';
      output.style.display = '';
      output.textContent = 'Network error: ' + e.message;
    } finally {
      btn.disabled = false;
    }
  }

  function extractImprovedVersion(raw) {
    const lines = raw.split('\\n');
    let found = false;
    const parts = [];
    for (const line of lines) {
      if (!found) {
        if (/improved version/i.test(line)) { found = true; }
        continue;
      }
      if (line.trim() === '---' || /what.?changed/i.test(line)) break;
      parts.push(line);
    }
    return found ? parts.join('\\n').trim() : raw;
  }

  function tableToTSV(raw) {
    // Convert markdown table to TSV for Excel paste
    const lines = raw.split('\\n');
    const rows = [];
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('|')) continue;
      if (t.match(/^\\|[-| :]+\\|$/)) continue; // separator
      const cells = t.split('|').slice(1,-1).map(c =>
        c.trim().replace(/\\*\\*(.+?)\\*\\*/g,'$1').replace(/`([^`]+)`/g,'$1')
      );
      rows.push(cells.map(tsvEscapeCell).join('\\t'));
    }
    return rows.length ? rows.join('\\n') : raw;
  }

  function exportProofCopy() {
    if (!lastProofOutput) return;
    const improved = extractImprovedVersion(lastProofOutput);
    // If improved section contains a table, copy as TSV for Excel; otherwise plain text
    const text = improved.includes('|') ? tableToTSV(improved) : improved;
    navigator.clipboard.writeText(text).then(() => {
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
        return clean.includes(',') || clean.includes('"') || clean.includes('\\n') ? '"' + clean.replace(/"/g,'""') + '"' : clean;
      }).join(','));
    const content = rows.length ? rows.join('\\n') : lastProofOutput;
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'proofread.csv'; a.click();
    URL.revokeObjectURL(url);
  }
  // ────────────────────────────────────────────────────────────────

  // ── TSV / Excel paste handling ──────────────────────────────────
  let tsvData = null; // parsed rows from Excel paste

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('inputText').addEventListener('paste', handlePaste);
  });

  function handlePaste(e) {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!text.includes('\\t')) return; // not TSV, let default paste happen

    e.preventDefault();
    const rows = text.trim().split('\\n').map(r => r.split('\\t').map(c => c.trim()));
    const numCols = Math.max(...rows.map(r => r.length));
    if (numCols < 2) return; // single column — let it through

    tsvData = rows;

    // Update source/context selectors based on number of columns
    const srcSel = document.getElementById('tsvSource');
    const ctxSel = document.getElementById('tsvContext');
    srcSel.innerHTML = '';
    ctxSel.innerHTML = '<option value="-1">None</option>';
    for (let i = 0; i < numCols; i++) {
      const letter = String.fromCharCode(65 + i);
      srcSel.innerHTML += `<option value="${i}">Col ${letter}</option>`;
      ctxSel.innerHTML += `<option value="${i}" ${i === 1 ? 'selected' : ''}>Col ${letter}</option>`;
    }

    const banner = document.getElementById('tsvBanner');
    document.getElementById('tsvInfo').textContent =
      `Spreadsheet detected — ${numCols} columns, ${rows.length} rows`;
    banner.className = 'tsv-banner visible';

    // Put a preview in the textarea so it's not empty
    renderTsvPreview();

    // Re-render preview when selectors change
    srcSel.onchange = ctxSel.onchange = renderTsvPreview;
  }

  function getDataRows() {
    if (!tsvData) return [];
    const skip = document.getElementById('tsvHasHeader')?.checked ? 1 : 0;
    return tsvData.slice(skip);
  }

  function renderTsvPreview() {
    if (!tsvData) return;
    const srcIdx = parseInt(document.getElementById('tsvSource').value);
    const rows = getDataRows();
    const lines = rows.map((r, i) => `${i + 1}. ${r[srcIdx] || ''}`);
    document.getElementById('inputText').value = lines.join('\\n');
  }

  function clearTsv() {
    tsvData = null;
    document.getElementById('tsvBanner').className = 'tsv-banner';
    document.getElementById('inputText').value = '';
  }

  function buildTsvMessage(srcLang, tgtLang, type) {
    if (!tsvData) return null;
    const srcIdx = parseInt(document.getElementById('tsvSource').value);
    const ctxIdx = parseInt(document.getElementById('tsvContext').value);
    const hasCtx = ctxIdx >= 0 && ctxIdx !== srcIdx;
    const rows = getDataRows();
    if (!rows.length) return null;

    const srcInfo = srcLang !== 'auto' ? ` from ${srcLang}` : '';
    const typeInfo = type !== 'auto' ? ` (type: ${type})` : '';

    let msg = `Translate each row${srcInfo} to ${tgtLang}${typeInfo}.`;
    if (hasCtx) msg += ` The reference column is provided for context/consistency — do NOT translate it, only translate the source column.`;
    msg += `\\n\\nDeliver a single table with columns: Row | Source | Translation.\\n\\n`;

    rows.forEach((row, i) => {
      const src = row[srcIdx] || '';
      const ctx = hasCtx ? row[ctxIdx] || '' : '';
      msg += `Row ${i + 1} — Source: ${src}`;
      if (hasCtx && ctx) msg += ` | Reference: ${ctx}`;
      msg += '\\n';
    });

    return msg;
  }
  // ────────────────────────────────────────────────────────────────

  function extractTranslatedText(raw) {
    const lines = raw.split('\\n');
    const parts = [];
    let headerSkipped = false;

    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('|')) continue;
      if (t.match(/^\\|[-| :]+\\|$/)) continue; // separator row — skip, do NOT reset headerSkipped
      const cells = t.split('|').slice(1, -1).map(c =>
        c.trim().replace(/\\*\\*(.+?)\\*\\*/g, '$1').replace(/`([^`]+)`/g, '$1')
      );
      if (!headerSkipped) { headerSkipped = true; continue; } // skip the single column header row
      if (cells.length < 2) continue;
      const label  = cells[0].toLowerCase();
      const target = cells[cells.length - 1];
      // Skip meta/note rows — not actual translated content
      const metaLabels = ['note', 'meta', 'type', 'source lang', 'target lang', 'source language', 'target language'];
      if (metaLabels.includes(label)) continue;
      if (!target || target === '' || target.startsWith('[')) continue;
      // Skip rows where target is a status note (starts with emoji checkmarks etc.)
      if (/^[✅❌⚠️🔴🟡🟢]/.test(target)) continue;
      parts.push(target);
    }

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
    document.getElementById('tsvBanner').className = 'tsv-banner';
    tsvData = null;
    lastRawOutput = '';
    lastResults = [];
  }

  function newTranslation() {
    clearAll();
    clearProofread();
    document.getElementById('contentType').value = 'auto';
    document.querySelectorAll('#targetLangs input[type=checkbox]').forEach(cb => {
      cb.checked = cb.value === 'FR';
    });
    document.getElementById('proofBody').classList.remove('open');
    document.getElementById('proofToggle').className = 'proof-toggle';
    closeResultsModal();
    document.getElementById('resultsFab').style.display = 'none';
    proofResults = {};
    translationSourceRows = [];
    document.getElementById('inputText').focus();
  }

  function exportCopy() {
    if (!lastRawOutput) return;
    // Copy only the translated text of the active tab (clean, no pipes)
    const clean = extractTranslatedText(getActiveResult());
    navigator.clipboard.writeText(clean).then(() => {
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
    // Export clean translated text per language
    const content = lastResults.length > 1
      ? lastResults.map(({ lang, result }) => '## ' + lang + '\\n\\n' + extractTranslatedText(result)).join('\\n\\n---\\n\\n')
      : extractTranslatedText(getActiveResult());
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'translation.md'; a.click();
    URL.revokeObjectURL(url);
  }

  function exportCSV() {
    if (!lastRawOutput) return;
    // CSV keeps the full source+target table — useful for spreadsheet workflows
    const raw = lastRawOutput;
    const lines = raw.split('\\n');
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
    const content = csvRows.length ? csvRows.join('\\n') : raw;
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'translation.csv'; a.click();
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

  function getTargetLangs() {
    return [...document.querySelectorAll('#targetLangs input:checked')].map(i => i.value);
  }

  async function streamTranslation(message, lang) {
    const resp = await fetch('/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: message, api_key: activeKey })
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || resp.statusText);
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
    return full;
  }

  async function runTranslate() {
    if (!activeKey) { changeKey(); return; }

    const text = document.getElementById('inputText').value.trim();
    if (!text) { alert(t('alertNoText')); return; }

    const targets = getTargetLangs();
    if (!targets.length) { alert('Select at least one target language.'); return; }

    const sourceLang = document.getElementById('sourceLang').value;
    const type       = document.getElementById('contentType').value;
    const btn        = document.getElementById('btnTranslate');
    const output     = document.getElementById('output');
    const loader     = document.getElementById('hxLoading');

    btn.disabled = true;
    output.style.display = 'none';
    loader.className = 'hx-loading visible';
    startLoadingAnim();

    try {
      // Run translations sequentially — more reliable with streaming + Render free tier
      const results = [];
      for (const lang of targets) {
        const msg = buildTsvMessage(sourceLang, lang, type)
          || (() => {
            const s = sourceLang !== 'auto' ? ` from ${sourceLang}` : '';
            const tp = type !== 'auto' ? ` (type: ${type})` : '';
            return `Translate this content${s} to ${lang}${tp}:\\n\\n${text}`;
          })();

        // Update loading text to show progress
        const loadingTxt = document.querySelector('#hxLoading .hx-loading-text');
        if (loadingTxt) loadingTxt.textContent = `${lang}… (${results.length + 1}/${targets.length})`;

        try {
          const result = await streamTranslation(msg, lang);
          results.push({ lang, result });
        } catch(e) {
          results.push({ lang, result: `Translation error: ${e.message}` });
        }
      }

      stopLoadingAnim();
      loader.className = 'hx-loading';
      output.style.display = '';
      output.innerHTML = '';

      const allRaw = [];

      if (results.length === 1) {
        // Single language — no tabs needed
        renderMarkdown(output, results[0].result);
        allRaw.push(results[0].result);
      } else {
        // Multiple languages — render as tabs
        const tabBar = document.createElement('div');
        tabBar.className = 'result-tabs';

        const panels = [];
        results.forEach(({ lang, result }, i) => {
          // Tab button
          const tab = document.createElement('button');
          tab.className = 'result-tab' + (i === 0 ? ' active' : '');
          tab.textContent = lang;
          tab.onclick = () => {
            tabBar.querySelectorAll('.result-tab').forEach(t => t.classList.remove('active'));
            panels.forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            panels[i].classList.add('active');
          };
          tabBar.appendChild(tab);

          // Panel
          const panel = document.createElement('div');
          panel.className = 'result-panel' + (i === 0 ? ' active' : '');
          renderMarkdown(panel, result);
          panels.push(panel);

          allRaw.push(`## ${lang}\\n\\n${result}`);
        });

        output.appendChild(tabBar);
        panels.forEach(p => output.appendChild(p));
      }

      lastRawOutput = allRaw.join('\\n\\n---\\n\\n');
      lastResults = results;
      output.scrollTop = 0;
      document.getElementById('exportBar').className = 'export-bar visible';

      // Populate proofreader tabs — one per language
      buildProofTabs(results);

      // Auto-proofread: open section and run immediately
      const proofBody = document.getElementById('proofBody');
      const proofToggle = document.getElementById('proofToggle');
      if (!proofBody.classList.contains('open')) {
        proofBody.classList.add('open');
        proofToggle.className = 'proof-toggle open';
      }
      setTimeout(() => proofBody.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
      runProofread();

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
