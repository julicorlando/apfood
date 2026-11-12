/**
 * Cardápio público da loja: /{slug}
 * Passo 4: buscar GET /p/:slug/cardapio, carrinho com adicionais, checkout
 * (retirada/entrega com cálculo de taxa, forma de pagamento, troco).
 */
export default async function CardapioPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return (
    <main style={{ maxWidth: 640, margin: '0 auto', padding: 16, fontFamily: 'system-ui' }}>
      <h1>Cardápio — {slug}</h1>
      <p>Em construção (Passo 4).</p>
    </main>
  );
}
