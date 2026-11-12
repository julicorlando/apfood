import type { NextConfig } from 'next';

const config: NextConfig = {
  // Compila o pacote compartilhado (TypeScript puro) junto com a app.
  transpilePackages: ['@apfood/shared'],
};

export default config;
