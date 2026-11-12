/**
 * Seed de desenvolvimento: 1 loja, 3 usuários (um por papel), cardápio de
 * exemplo de hamburgueria com adicionais, insumos e ficha técnica.
 *
 * Senha de todos os usuários: "apfood123" (somente dev!)
 */
import { PrismaClient, Prisma } from '@prisma/client';
import argon2 from 'argon2';

const prisma = new PrismaClient();
const D = (n: number) => new Prisma.Decimal(n);

async function main() {
  const senhaHash = await argon2.hash('apfood123');

  const loja = await prisma.loja.upsert({
    where: { slug: 'burger-demo' },
    update: {},
    create: {
      nome: 'Burger Demo',
      slug: 'burger-demo',
      cidade: 'São Paulo',
      uf: 'SP',
      abertaParaPedidos: true,
      pedidoMinimoCentavos: 2000,
      tempoPreparoMin: 35,
    },
  });

  for (const [login, nome, papel] of [
    ['admin', 'Administrador', 'ADMIN'],
    ['gerente', 'Gerente', 'GERENTE'],
    ['caixa1', 'Operador Caixa 1', 'OPERADOR'],
  ] as const) {
    await prisma.usuario.upsert({
      where: { lojaId_login: { lojaId: loja.id, login } },
      update: {},
      create: { lojaId: loja.id, login, nome, papel, senhaHash },
    });
  }

  // Insumos
  const insumo = (nome: string, unidade: 'UN' | 'G' | 'KG', estoque: number, minimo: number) =>
    prisma.produto.create({
      data: {
        lojaId: loja.id,
        tipo: 'INSUMO',
        nome,
        unidade,
        controlaEstoque: true,
        estoqueAtual: D(estoque),
        estoqueMinimo: D(minimo),
        disponivelOnline: false,
      },
    });

  const pao = await insumo('Pão brioche', 'UN', 120, 30);
  const carne = await insumo('Blend bovino 150 g', 'UN', 100, 25);
  const queijo = await insumo('Queijo cheddar (fatia)', 'UN', 200, 50);
  const bacon = await insumo('Bacon', 'G', 3000, 500);
  const embalagem = await insumo('Embalagem hambúrguer', 'UN', 300, 80);

  const lanches = await prisma.categoria.create({
    data: { lojaId: loja.id, nome: 'Hambúrgueres', ordem: 1 },
  });
  const bebidas = await prisma.categoria.create({
    data: { lojaId: loja.id, nome: 'Bebidas', ordem: 2 },
  });

  const xBurger = await prisma.produto.create({
    data: {
      lojaId: loja.id,
      categoriaId: lanches.id,
      nome: 'X-Burger Clássico',
      descricao: 'Pão brioche, blend 150 g, cheddar e molho da casa.',
      precoCentavos: 2890,
      baixarInsumos: true,
      fichaTecnica: {
        create: [
          { insumoId: pao.id, quantidade: D(1) },
          { insumoId: carne.id, quantidade: D(1) },
          { insumoId: queijo.id, quantidade: D(2) },
          { insumoId: embalagem.id, quantidade: D(1) },
        ],
      },
    },
  });

  await prisma.produto.create({
    data: {
      lojaId: loja.id,
      categoriaId: bebidas.id,
      nome: 'Refrigerante lata 350 ml',
      precoCentavos: 700,
      controlaEstoque: true,
      estoqueAtual: D(48),
      estoqueMinimo: D(12),
    },
  });

  const ponto = await prisma.grupoAdicional.create({
    data: {
      lojaId: loja.id,
      nome: 'Ponto da carne',
      minSelecao: 1,
      maxSelecao: 1,
      adicionais: {
        create: [{ nome: 'Mal passado' }, { nome: 'Ao ponto' }, { nome: 'Bem passado' }],
      },
    },
  });

  const extras = await prisma.grupoAdicional.create({
    data: {
      lojaId: loja.id,
      nome: 'Turbine seu lanche',
      minSelecao: 0,
      maxSelecao: 5,
      adicionais: {
        create: [
          { nome: 'Bacon extra', precoCentavos: 500, maxPorItem: 3, insumoId: bacon.id, quantidadeInsumo: D(30) },
          { nome: 'Cheddar extra', precoCentavos: 400, maxPorItem: 2, insumoId: queijo.id, quantidadeInsumo: D(1) },
        ],
      },
    },
  });

  await prisma.produtoGrupoAdicional.createMany({
    data: [
      { produtoId: xBurger.id, grupoId: ponto.id, ordem: 1 },
      { produtoId: xBurger.id, grupoId: extras.id, ordem: 2 },
    ],
  });

  await prisma.zonaEntrega.createMany({
    data: [
      { lojaId: loja.id, tipo: 'RAIO_KM', nome: 'Até 3 km', raioMaxKm: D(3), taxaCentavos: 500, tempoEstimadoMin: 30 },
      { lojaId: loja.id, tipo: 'RAIO_KM', nome: 'Até 6 km', raioMaxKm: D(6), taxaCentavos: 900, tempoEstimadoMin: 45 },
    ],
  });

  await prisma.categoriaDespesa.createMany({
    data: ['Fornecedores', 'Aluguel', 'Energia', 'Motoboys', 'Outros'].map((nome) => ({ lojaId: loja.id, nome })),
    skipDuplicates: true,
  });

  console.log(`Seed concluído — loja "${loja.slug}" (${loja.id})`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
