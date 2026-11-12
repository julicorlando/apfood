import { formatarCentavos } from '@apfood/shared';

/**
 * Passo 3: login/PIN → abertura de caixa → telas de Pedidos online (fila),
 * Balcão, Delivery (busca por telefone), Estoque, Fechamento e Relatórios.
 */
export function App() {
  return (
    <main style={{ fontFamily: 'system-ui', padding: 24 }}>
      <h1>ApFood PDV</h1>
      <p>Estrutura inicial pronta. Exemplo de formatação compartilhada: {formatarCentavos(2890)}</p>
    </main>
  );
}
