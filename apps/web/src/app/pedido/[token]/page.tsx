/**
 * Acompanhamento público do pedido: /pedido/{tokenRastreio}
 * Passo 4: GET /p/pedido/:token + Socket.IO ('pedido:acompanhar') para
 * atualizar a linha do tempo Recebido → Em preparo → Saiu p/ entrega → Concluído.
 */
export default async function AcompanharPedidoPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <main style={{ maxWidth: 640, margin: '0 auto', padding: 16, fontFamily: 'system-ui' }}>
      <h1>Seu pedido</h1>
      <p>Código de acompanhamento: {token}</p>
    </main>
  );
}
