# Integrix AI Landing

Landing page publica da Integrix AI para deploy estatico na Vercel.

## Desenvolvimento

```bash
npm install
npm run dev
```

A landing fica em `http://localhost:5173`.

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
