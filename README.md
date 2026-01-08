# MSYS Imob - Extrator de Aniversariantes

Script Python automatizado para extrair aniversariantes do CRM MSYS Imob e salvar em planilha Excel.

## 📋 Requisitos

- Python 3.7 ou superior
- Bibliotecas: `requests`, `pandas`, `openpyxl`

## 🚀 Instalação

1. Instale as dependências:
```bash
pip install -r requirements.txt
```

## ⚙️ Configuração

1. Crie o arquivo `credentials.json` na raiz do projeto:
```json
{
  "refresh_token": "SEU_REFRESH_TOKEN_AQUI"
}
```

2. Substitua `SEU_REFRESH_TOKEN_AQUI` pelo seu refresh token da API MSYS Imob.

## 📖 Como Usar

Execute o script:
```bash
python msys_bot.py
```

O script irá:
1. ✅ Autenticar na API usando o refresh token
2. ✅ Atualizar automaticamente o refresh token
3. ✅ Buscar todas as pessoas ativas (com paginação automática)
4. ✅ Filtrar quem faz aniversário hoje
5. ✅ Gerar planilha Excel em `planilhas/aniversariantes_YYYY-MM-DD.xlsx`

## 📊 Estrutura da Planilha

A planilha gerada contém as seguintes colunas:
- **Nome**: Nome completo da pessoa
- **Email**: Email principal
- **Telefone**: Telefone formatado (DDD + Número)
- **Data de Nascimento**: Data de nascimento
- **Tipo de Pessoa**: Tipo de pessoa no sistema

## 📁 Estrutura do Projeto

```
MSYS/
├── credentials.json      # Arquivo com refresh token (criar manualmente)
├── msys_bot.py          # Script principal
├── requirements.txt     # Dependências
├── README.md           # Este arquivo
└── planilhas/          # Pasta onde as planilhas são salvas
    └── aniversariantes_YYYY-MM-DD.xlsx
```

## 🔒 Segurança

- O arquivo `credentials.json` está no `.gitignore` para não ser versionado
- As planilhas geradas também estão ignoradas

## ⚠️ Observações

- O refresh token é atualizado automaticamente a cada execução
- O script busca apenas pessoas com status "A" (Ativo)
- A paginação é automática (100 registros por página)
- Se não houver aniversariantes no dia, nenhuma planilha será gerada

