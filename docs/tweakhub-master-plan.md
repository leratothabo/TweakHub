# TweakHub — Master Plan
Commercial PDF/File Processing Platform for the African Market

_Saved 2026-08-31 as the reference architecture/business doc for the TweakHub project. Also mirrored in the TweakHub claude.ai project as `claude/tweakhub-master-plan.md`._

## Overview

TweakHub is a commercial web application for the African market, offering 200+ file processing tools (PDF, images, video, audio, documents) with flexible payment options including pay-as-you-go credits. Target deployment: Truehost (Kenya), with a Git-to-production workflow via GitHub Actions.

## Core Architecture (Hybrid Model)

### 1. Backend Foundation (Commercial-Friendly)

- **AVX (MIT License)** — primary conversion engine, 100+ format conversions via a single CLI, wrapped as a microservice with a REST API.
- **ConvertAgent (Open-Source)** — document conversion specialist for pdf↔docx, html→pdf, markdown→pdf; REST API + MCP server for complex workflows.
- **TerraPDF (MIT License)** — PDF generation from templates (invoices, reports, certificates); C# library with rich formatting, barcodes, encryption.
- **php-pdf (MIT License)** — PDF manipulation: merge, split, extract pages, watermarks, digital signatures. Pure PHP, no external deps.
- **PDF processing Java libraries:**
  - Apache PDFBox (Apache 2.0) — core PDF handling, text extraction, forms, preflight, digital signatures.
  - JPedal (Commercial) — pixel-accurate rendering, embedded viewer, enterprise support.
  - iText (AGPL/Commercial) — complex PDF generation. **AGPL requires source disclosure unless a commercial license is purchased** — flagged as a licensing risk to resolve before shipping any iText-backed tool.

### 2. Frontend Layer

- **PDFEditor (MIT License)** — browser-based PDF editing (React/Next.js + TypeScript): annotations, highlighting, shapes, forms.
- **SimplePDF Embed (MIT License)** — lightweight PDF viewing/form filling via iframe or React.

### 3. Proprietary Core

Backend routing logic dispatches each tool name to the engine that handles it:

```python
# app/services/tool_router.py
class ToolRouter:
    def __init__(self):
        self.engines = {
            'convert': AVXEngine(),
            'document': ConvertAgentEngine(),
            'generate': TerraPDFEngine(),
            'manipulate': PHPPDFEngine(),
            'edit': PDFEditorEngine(),
        }

    def route_tool(self, tool_name, input_data, options):
        if tool_name in ['pdf_to_word', 'html_to_pdf']:
            return self.engines['document'].process(input_data, options)
        elif tool_name in ['merge', 'split', 'watermark']:
            return self.engines['manipulate'].process(input_data, options)
        # ... etc
```

## Payment Strategy: Airtime, Mobile Money, Cards, Pay-As-You-Go

**DPO Group** is the pan-African payment gateway of choice: Visa/Mastercard, MTN Mobile Money, Airtel Money, bank transfers, across 21+ African countries.

### Option 1 — Subscriptions

| Tier | Price (USD) | Price (ZAR) | Features |
|------|-------------|-------------|----------|
| Free | $0 | R0 | 5 tools/day, 10 MB max file, watermarked output |
| Pro | $5.99/mo | ~R110/mo | Unlimited tools, 100 MB files, batch processing, priority queue |
| Business | $19.99/mo | ~R370/mo | Team accounts, 500 MB files, custom branding, API access |
| Enterprise | Custom | Custom | Self-hosted option, unlimited, dedicated support |

### Option 2 — Pay-As-You-Go Credits

Rationale: lowers barrier to entry, aligns cost with value, mirrors prepaid airtime/data/electricity spending habits, credits never expire, protects from currency volatility.

```python
# app/services/credit_service.py
class CreditService:
    def __init__(self):
        self.credit_packages = {
            'starter': {'credits': 100, 'price_usd': 2.99, 'price_zar': 55},
            'popular': {'credits': 500, 'price_usd': 9.99, 'price_zar': 185},
            'pro': {'credits': 2000, 'price_usd': 29.99, 'price_zar': 555},
            'business': {'credits': 10000, 'price_usd': 99.99, 'price_zar': 1850},
        }

    def get_credit_cost(self, tool_name, file_size):
        """Calculate credit cost based on tool complexity and file size"""
        base_cost = {
            'pdf_merge': 5,
            'pdf_split': 3,
            'pdf_to_word': 15,
            'pdf_compress': 8,
            'image_convert': 5,
            'video_compress': 30,
            'ocr_extract': 20,
        }
        cost = base_cost.get(tool_name, 10)
        if file_size > 50:
            cost = cost * 1.5
        if file_size > 100:
            cost = cost * 2
        return round(cost)

    def process_credit_purchase(self, user_id, package_key, payment_method):
        """Handle credit purchase via DPO"""
        package = self.credit_packages[package_key]
        payment_token = self.initiate_dpo_payment(
            amount=package['price_usd'],
            currency='USD',
            description=f'{package["credits"]} Credits',
            callback_url=f'{BASE_URL}/payment-callback'
        )
        return {
            'payment_url': f'https://secure.dpogroup.com/pay/{payment_token}',
            'credits': package['credits'],
            'amount': package['price_usd']
        }
```

### Option 3 — Mobile Money (via DPO)

MTN Mobile Money, Airtel Money, Orange Money, M-Pesa, Wave.

### Option 4 — Debit/Credit Cards

Visa, Mastercard, Amex with 3D Secure.

## Deployment on Truehost with GitHub Push

Truehost (Kenya) advantages: pay in KES via M-Pesa, pre-configured environments, NVMe SSD, full root SSH access, local Nairobi support (~4 min first response), automated daily snapshots, network-level DDoS protection.

| Plan | Price | vCPU | RAM | Storage | Bandwidth | Best For |
|------|-------|------|-----|---------|-----------|----------|
| KVM1 | Ksh 1,999/mo | 1 | 2 GB | 50 GB NVMe | 4 TB | Development & testing |
| KVM2 | Ksh 2,699/mo | 2 | 4 GB | 100 GB NVMe | 8 TB | Production deployment |

### Repository layout

```
tweakhub/
├── .github/workflows/{deploy.yml, test.yml}
├── apps/
│   ├── web/            # Next.js frontend (React/TypeScript)
│   ├── api/             # Backend API
│   └── workers/         # Background job processors
├── packages/
│   ├── avx-client/
│   ├── terra-pdf/
│   └── convert-agent/
├── infrastructure/
│   ├── docker/{Dockerfile.api, Dockerfile.web, docker-compose.yml}
│   └── nginx/nginx.conf
├── scripts/{deploy.sh, setup-truehost.sh}
├── tests/
├── docs/
├── .env.example
├── .gitignore
├── package.json
├── README.md
└── LICENSE
```

### GitHub Actions → Truehost deployment

`.github/workflows/deploy.yml` builds, tests, then SCPs the build to the Truehost VPS and restarts the app via PM2 over SSH (see repo for full workflow).

Required GitHub secrets: `TRUEHOST_HOST`, `TRUEHOST_USERNAME`, `TRUEHOST_PASSWORD`, `TRUEHOST_PORT`, `DATABASE_URL`, `DPO_COMPANY_TOKEN`.

### VPS bootstrap (once)

```bash
ssh root@your-truehost-ip
apt update && apt upgrade -y
apt install -y docker.io docker-compose nginx git python3-pip
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
npm install -g pm2
git clone https://github.com/yourusername/tweakhub.git /var/www/tweakhub
cd /var/www/tweakhub
# create .env.production with secrets
npm run build
pm2 start ecosystem.config.js
```

### Custom domain + SSL

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d tweakhub.com -d www.tweakhub.com
```

### Truehost VPS vs GitHub Pages

| Feature | Truehost VPS | GitHub Pages |
|---------|--------------|---------------|
| Cost | Ksh 1,999+/mo (M-Pesa) | Free |
| Deployment | Git push + Actions | Git push |
| Use case | Full web app w/ backend | Static frontend/docs |
| Payments | Yes (DPO) | No |
| Database | Yes (self-managed) | No |
| File storage | Yes (on VPS) | Limited |
| Custom domain | Yes | Yes |
| SSL | Let's Encrypt | Automatic |
| Support | Local, ~4 min | Community |

## SEO & Growth Strategy (TEMU-style)

1. **Paid search** — bid on competitor keywords ("best PDF editor", "TinyWow alternative", "SimpliPDF free"), predictive budget allocation per country.
2. **Content & semantic authority** — Semrush/Ahrefs with a ZA database, target KD ≤ 20 / volume ≥ 50, pillar+cluster content, local city/regional variations.
3. **Technical SEO** — GSC + GA4, Schema.org structured data, mobile-first (80%+ African traffic is mobile), monitor Core Web Vitals.
4. **Africa-specific growth hacks** — WhatsApp bot for tool recommendations, mobile-first PWA for low-connectivity areas, "share and get 50 free credits" referrals, partnerships with African universities/businesses.

## Security & Compliance Checklist

- [ ] HTTPS via Let's Encrypt
- [ ] File encryption at rest (AES-256)
- [ ] File auto-deletion after 24–48 hours
- [ ] Rate limiting (100 req/hr free tier)
- [ ] API key auth for paid users
- [ ] POPIA compliance (South Africa)
- [ ] GDPR compliance (EU users)
- [ ] Regular security audits (Snyk, OWASP)
- [ ] CSP headers
- [ ] DDoS protection (Truehost network-level)
- [ ] No logging of file contents (metadata only)
- [ ] PCI DSS via DPO Group (handles card data)

## Naming Rationale

"Tweak" communicates modification/processing; "Hub" suggests a central, comprehensive platform. Short (8 characters), professional yet approachable, easy to brand across Africa and globally.

## Open Risks / Decisions Needed (flagged during scaffolding)

- **iText licensing**: AGPL triggers source-disclosure obligations for a closed-source SaaS unless a commercial license is bought — decide per-tool whether to use iText, or standardize on PDFBox/php-pdf/TerraPDF instead. See `docs/licensing.md`.
- **JPedal** is commercial-only — budget for a license if pixel-accurate rendering/embedded viewer is actually required, or substitute an open renderer (e.g., pdf.js) for the viewer.
- **AVX / ConvertAgent / TerraPDF** are referenced by name in the plan but not linked to verifiable upstream projects — confirm the actual libraries/binaries before wiring the engine wrappers to real packages. See `docs/engines.md`.
- Backend language is stated as "Node.js/Python/Go" but all the sample service/route/model code in the plan is Python — the scaffold standardizes on **FastAPI (Python)** for `apps/api` to match the provided code, and Next.js/TypeScript for `apps/web`. Revisit if Node was actually intended for the API.
