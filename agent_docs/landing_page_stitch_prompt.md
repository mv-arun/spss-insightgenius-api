# Prompt para Google Stitch — Indico Crosstab Landing + App

> Genera todos los assets de diseño (wireframes, mockups, componentes) para un sitio web completo. El output se va a implementar en React + Vite + Tailwind + shadcn/ui, desplegado en Vercel. La autenticación será via Supabase Auth. Genera diseños que respeten una arquitectura de componentes reutilizables.

---

## Contexto del producto

**Indico Crosstab** es una herramienta web + API + MCP server que permite a investigadores de mercado procesar archivos SPSS (.sav), CSV y Excel para obtener tablas cruzadas profesionales con pruebas de significancia estadística.

**Producto live:** https://crosstab.indicolabs.io
**API Docs:** https://crosstab.indicolabs.io/docs
**MCP Docs:** https://crosstab.indicolabs.io/docs/mcp
**Privacy:** https://crosstab.indicolabs.io/privacy

### Tres modos de uso:

1. **Web UI (drag & drop):** Sube un archivo .sav/.csv/.xlsx, haz clic en "Auto-Analyze", descarga tu Excel con crosstabs profesionales. Sin configuración, sin instalación.

2. **MCP para Claude:** Conéctalo a Claude Desktop, Cursor, o Claude.ai y habla con tus datos en lenguaje natural. "¿Cuál es la satisfacción por región?" → tabla cruzada con letras de significancia.

3. **API REST + Automatización:** Conecta a n8n, Make, o Zapier. Un webhook recibe el .sav → se procesa automáticamente → el Excel se envía por email al cliente.

### Stack técnico (para que los diseños sean implementables):
- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui
- **Auth:** Supabase Auth (email + Google OAuth)
- **Backend API:** FastAPI (ya existe en https://crosstab.indicolabs.io)
- **Deploy:** Vercel (frontend) + Railway (backend API)
- **Pagos:** Stripe Checkout

---

## Audiencia objetivo (3 personas)

**Persona 1: "Ana, la Investigadora Práctica"**
- 35 años, ejecutiva de cuenta en agencia de investigación de mercados
- Tiene archivos .sav de Qualtrics/SurveyMonkey
- Actualmente usa PSPP (gratis pero difícil) o pide ayuda al equipo de procesamiento (tarda 2-3 días)
- QUIERE: subir su archivo, hacer clic, y descargar el Excel en 2 minutos
- DOLOR: "Cada vez que necesito unas tablas tengo que esperar al equipo de DP"

**Persona 2: "Carlos, el Analista con IA"**
- 28 años, data analyst junior que ya usa Claude/ChatGPT
- Quiere conectar sus datos de encuestas directamente a Claude
- QUIERE: hablar con sus datos y obtener insights con significancia real
- DOLOR: "Pego datos en ChatGPT y los resultados no tienen significancia estadística"

**Persona 3: "María, la Directora de Operaciones"**
- 45 años, dirige operaciones de una agencia MR con 20 personas
- Procesa 50+ estudios al mes. El equipo de DP es el cuello de botella
- QUIERE: automatizar el procesamiento de trackers mensuales
- DOLOR: "Tenemos 3 personas de DP que hacen lo mismo cada mes"

---

## Páginas a diseñar (6 páginas)

### Página 1: Landing Page (/)

#### Hero Section
- **Headline:** "De archivo SPSS a tablas profesionales en 2 minutos"
- **Sub-headline:** "Sube tu .sav, haz clic en Auto-Analyze, descarga tu Excel con pruebas de significancia. Sin PSPP, sin WinCross, sin esperar al equipo de DP."
- **CTA principal:** "Prueba gratis — Sube tu archivo" → va a /app (si logueado) o /signup (si no)
- **CTA secundario:** "Ver cómo funciona →" → scroll a sección demo
- **Visual:** Mockup: archivo .sav entrando por la izquierda → interfaz de Indico Crosstab → Excel con letras de significancia (A, B, C en rojo) saliendo por la derecha

#### Social Proof Bar
- "Procesa archivos SPSS de hasta 200MB · 14 tipos de análisis · Pruebas de significancia al 90/95/99% · Usado por agencias en 5 países"

#### Section: "Tres formas de usar Indico Crosstab"
Tres cards horizontales:

**Card 1: "Sube y descarga" (ícono: Upload + Download)**
"Arrastra tu archivo .sav, .csv o .xlsx. Haz clic en Auto-Analyze. En 60 segundos tienes un Excel profesional con tablas cruzadas, letras de significancia, nets (Top 2 Box), y medias con T-test."
→ Botón: "Probar ahora"

**Card 2: "Habla con tus datos" (ícono: Chat bubble + Chart)**
"Conecta Indico Crosstab a Claude Desktop o Claude.ai y haz preguntas en lenguaje natural: '¿Cuál es el NPS por región?' → obtén la tabla con significancia, el insight, y el contenido listo para presentación."
→ Botón: "Ver cómo funciona →" → /docs/mcp

**Card 3: "Automatiza tus trackers" (ícono: Gear + Repeat)**
"Conecta a n8n, Make o Zapier. Cuando llega un nuevo archivo de datos, se procesa automáticamente y el Excel se envía por email al cliente."
→ Botón: "Ver documentación API" → /docs

#### Section: "Lo que obtienes en tu Excel"
Visual grande mostrando un Excel abierto con callouts señalando:
- Letras de significancia en rojo (A, B, C)
- Fila de Base (N)
- Nets: Top 2 Box en verde
- Means con T-test
- Summary sheet con leyenda de columnas
- Texto: "El mismo formato que produce WinCross o Quantum, pero en 2 minutos."

#### Section: "¿Qué problema resuelve?"
Tres bloques problema → solución:

1. "PSPP es complicado y SPSS cuesta $99/mes" → "Sube tu archivo, haz clic. Sin instalación."
2. "Mi equipo de DP tarda 2-3 días" → "Auto-Analyze genera el Excel completo. En minutos."
3. "ChatGPT no tiene significancia estadística" → "Indico Crosstab calcula con scipy/pandas. Estadística real, no alucinaciones."

#### Section: "Análisis disponibles"
Grid de 14 items con íconos:
Frecuencias · Tablas cruzadas con significancia · Múltiples banners · MRS · Grid/Battery · Nets (T2B/B2B) · Medias con T-test · NPS · Correlación · ANOVA + Tukey · Gap Analysis · Satisfaction Summary · Auto-Analyze · Export multi-formato

#### Section: Pricing
4 columnas:

| | **Free** | **Pro** | **Business** | **Enterprise** |
|---|---|---|---|---|
| Precio | $0 | $29/mes | $99/mes | Contactar |
| Análisis/mes | 50 | 500 | 5,000 | Ilimitado |
| Tamaño máx. | 5 MB | 50 MB | 200 MB | 500 MB |
| Todas las features | Sí | Sí | Sí | Sí |
| IA (Haiku) | No | No | Sí | Sí |
| MCP + API | Sí | Sí | Sí | Sí |
| Soporte | Community | Email 48h | Email 24h | Dedicado + SLA |

CTAs: "Empezar gratis" / "Obtener Pro" / "Obtener Business" / "Contactar"

#### Section: FAQ
- "¿Mis datos son seguros?" → Procesados en memoria, eliminados en 30 min. No almacenamos datos. Ver /privacy
- "¿La estadística es real o la genera IA?" → scipy y pandas. Z-tests, chi-cuadrado, T-tests son cálculos exactos.
- "¿Funciona con CSV/Excel?" → Sí. Acepta .sav, .csv, .tsv, .xlsx, .xls
- "¿Puedo usarlo en español?" → Las etiquetas de tu SPSS se respetan tal cual.
- "¿Necesito saber programar?" → No para la web UI. Sí para API/MCP.
- "¿Qué es el MCP?" → Protocolo para conectar herramientas a Claude. Analiza encuestas con significancia real desde Claude.

#### Footer
- Links: Docs · API Reference · MCP Server · Privacy Policy
- "Built by Indico Labs · support@surveycoder.io"
- NO incluir link a GitHub (repo privado)

---

### Página 2: Sign Up (/signup)

- Email + password (Supabase Auth)
- Google OAuth button
- Campos: nombre, email, password, empresa (opcional), rol (dropdown: Researcher / Analyst / Director / Developer / Other)
- Al registrarse: se genera API key automáticamente (sk_test_...)
- Redirect a /app después de signup
- Link: "¿Ya tienes cuenta? Iniciar sesión"

---

### Página 3: Login (/login)

- Email + password
- Google OAuth
- "Olvidé mi contraseña" link
- Link: "¿No tienes cuenta? Registrarse"

---

### Página 4: App / Dashboard (/app)

Esta es la versión autenticada del procesador SPSS. Reemplaza el frontend embebido actual.

#### Layout
- **Sidebar izquierdo (colapsable):**
  - Logo Indico Crosstab
  - "New Analysis" (botón prominente)
  - "My API Keys" → /app/keys
  - "Usage" → /app/usage
  - "Plan & Billing" → /app/billing
  - "MCP Setup" → /app/mcp
  - "Docs" → /docs
  - Separador
  - User avatar + nombre
  - "Sign Out"

- **Área principal:**
  El procesador SPSS actual (misma funcionalidad que crosstab.indicolabs.io):
  1. Upload .sav/.csv/.xlsx (drag & drop)
  2. Auto-Analyze button (one-click)
  3. Manual config: banners, stubs, MRS, Grid, Custom Groups, Options
  4. Generate Excel → Download

  NUEVO: historial de análisis recientes (últimos 10) en un panel lateral o debajo:
  - Filename, fecha, stubs, banners, download link (si aún disponible)
  - "Los archivos se eliminan después de 30 min. Solo guardamos el registro del análisis."

---

### Página 5: API Keys (/app/keys)

- Lista de API keys del usuario
- Cada key muestra: nombre, plan, scopes, fecha de creación, último uso
- Botón "Create New Key" → genera key, la muestra UNA vez con botón de copiar
- Botón "Revoke" por key (con confirmación)
- Instrucciones de uso:
  - curl example
  - Python example
  - MCP config example (Claude Desktop JSON)

---

### Página 6: Usage & Billing (/app/billing)

- **Plan actual:** Free / Pro / Business con badge
- **Uso del mes:** barra de progreso (ej: 23/50 análisis usados)
- **Botón "Upgrade"** → Stripe Checkout (hosted, no embedded)
- **Historial de facturas** (si hay Stripe integration)
- Detalles del plan:
  - Análisis restantes
  - Tamaño máx. de archivo
  - Features incluidas

---

## Estilo visual

- **Color primario:** #2563EB (azul)
- **Color secundario:** #1E40AF (azul oscuro)
- **Color de acento:** #DC2626 (rojo — letras de significancia)
- **Color éxito:** #16A34A (verde — nets/T2B)
- **Fondo:** Blanco, sections alternando #F9FAFB
- **Tipografía:** Inter
- **Componentes:** shadcn/ui (Button, Card, Dialog, DropdownMenu, Input, Select, Table, Tabs, Badge, Avatar, Sidebar)
- **Iconos:** Lucide (consistente con shadcn/ui)
- **Estilo:** Limpio, profesional, data-focused. NO startup/tech-bro. Similar a Linear.app pero para investigadores de mercado.
- **Sin ilustraciones abstractas de IA.** En su lugar: screenshots reales del producto, mockups de Excel output, diagramas de flujo.

---

## Consideraciones técnicas para el implementador

1. **Routing:** React Router v6. Public routes (/, /signup, /login, /privacy, /docs/mcp). Protected routes (/app/*) requieren auth.

2. **Auth state:** Supabase `onAuthStateChange` → Context provider. Protected routes redirect a /login si no autenticado.

3. **API calls:** El frontend llama al backend existente en https://crosstab.indicolabs.io/v1/*. La API key del usuario se guarda en Supabase (tabla `api_keys`) y se envía como `Authorization: Bearer` header.

4. **Stripe:** Checkout Sessions creadas server-side. El frontend solo redirect a la URL de checkout. Webhook en el backend confirma el pago y upgradea el plan.

5. **Responsive:** Mobile-first para landing page. Dashboard es desktop-only (investigadores usan laptop/desktop).

6. **i18n:** Preparar para ES/EN. Empezar solo en español (mercado LATAM primero). Estructura: `translations/es.ts`, `translations/en.ts`.

---

## Entregables esperados de Stitch

1. Wireframes de las 6 páginas
2. Mockups en alta fidelidad con el sistema de colores
3. Componentes individuales (hero, pricing card, feature card, sidebar, etc.)
4. Mobile responsive para landing page
5. Flowchart del user journey: Landing → Signup → Dashboard → Upload → Download
