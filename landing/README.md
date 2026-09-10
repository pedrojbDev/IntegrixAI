# Integrix AI Landing

Landing page publica da Integrix AI para deploy estatico na Vercel.

## Desenvolvimento

```bash
npm install
npm run dev
```

A landing fica em `http://localhost:5173`.

## Estrutura

- `src/App.tsx`: pagina publica, demonstracao ilustrativa, navegacao e FAQ.
- `src/ImpactCalculator.tsx`: simulador com controles deslizantes, entrada numerica
  e comparacao de custos.
- `src/estimate.ts`: premissas e calculo financeiro, com diferenca mensal
  arredondada em centavos para distinguir economia, equilibrio e custo maior.
- `src/index.css`: identidade visual, layout responsivo e movimento reduzido.
- `public/favicon.svg`: simbolo da marca para a aba do navegador.

A identidade combina azul-petroleo e cobre, com abertura escura, paineis claros
e resumo financeiro em contraste. A demonstracao anima as etapas uma unica vez;
com movimento reduzido, todo o fluxo aparece imediatamente.

A calculadora usa US$ 0,16/min como referencia de consumo, nao como preco
contratado. Impostos, telefonia, implantacao e integracoes ficam fora dessa
estimativa. O detalhamento das premissas esta disponivel na propria pagina.

## Variaveis

```env
VITE_OPS_CONSOLE_URL=/dashboard
```

Quando o servico completo estiver em uma VPS, configure na Vercel:

```env
VITE_OPS_CONSOLE_URL=https://ops.integrix.com.br/dashboard
```

## Deploy na Vercel

- Root Directory: `landing`
- Build Command: `npm run build`
- Output Directory: `dist`
- Dominio principal: `integrix.com.br`
- DNS apex: `A 76.76.21.21`
- `www`: use o `CNAME` indicado pela Vercel para o projeto

## Validacao local

```bash
npm run test
npm run typecheck
npm run lint
npm run build
```

Os testes renderizam a pagina e verificam os destinos de navegacao, os controles
do simulador e os cenarios financeiros, incluindo equilibrio e consumo superior
ao custo repetitivo. Para conferir a experiencia no navegador, verifique tambem
entrada numerica, sliders, restauracao de valores, menu movel e FAQ em larguras
de 320 px a desktop.
