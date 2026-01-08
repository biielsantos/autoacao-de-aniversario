# MSYS Imob - Verificador de Aniversários (GitHub Actions)

Esta é a versão adaptada do script para rodar no GitHub Actions diariamente.

## 📋 Estrutura

```
github/
├── msys_bot.py              # Script adaptado para GitHub Actions
├── requirements.txt         # Dependências Python
├── README.md               # Este arquivo
└── .github/
    └── workflows/
        └── aniversarios.yml # Workflow do GitHub Actions
```

## 🚀 Configuração do GitHub Actions

### Passo 1: Criar o repositório no GitHub

1. Crie um repositório no GitHub (pode ser privado)
2. Faça push do código desta pasta `github/` para o repositório

### Passo 2: Configurar Secrets

Vá em: **Settings > Secrets and variables > Actions > New repository secret**

Adicione os seguintes secrets:

#### 1. REFRESH_TOKEN (OBRIGATÓRIO)
- **Nome**: `REFRESH_TOKEN`
- **Valor**: Seu refresh token do MSYS Imob
- Copie do arquivo `credentials.json` da versão local

#### 2. WEBHOOK_URL (OPCIONAL)
- **Nome**: `WEBHOOK_URL`
- **Valor**: URL do webhook do BotConversa
- Se não adicionar, usa o valor padrão do código

#### 3. API_KEY_BOTCONVERSA (OPCIONAL)
- **Nome**: `API_KEY_BOTCONVERSA`
- **Valor**: API key do BotConversa
- Se não adicionar, usa o valor padrão do código

### Passo 3: Fazer commit e push

```bash
cd github
git init
git add .
git commit -m "Adiciona GitHub Actions para verificar aniversários"
git remote add origin <URL_DO_SEU_REPOSITORIO>
git push -u origin main
```

### Passo 4: Verificar execução

1. Vá em **Actions** no GitHub
2. Você verá o workflow "Verificar Aniversários"
3. Pode executar manualmente clicando em "Run workflow"

## ⏰ Horário de execução

O workflow roda todo dia às **08:00 UTC** (05:00 horário de Brasília).

Para mudar o horário, edite o arquivo `.github/workflows/aniversarios.yml`:

```yaml
- cron: '0 8 * * *'  # Formato: minuto hora dia mês dia-da-semana
```

**Exemplos:**
- `'0 8 * * *'` = 08:00 UTC todo dia
- `'0 9 * * *'` = 09:00 UTC todo dia (06:00 Brasília)
- `'0 12 * * 1'` = 12:00 UTC toda segunda-feira

## 🔄 Atualizar Refresh Token

Se o refresh_token mudar (o script avisa quando isso acontece):

1. Vá em **Settings > Secrets and variables > Actions**
2. Clique em **REFRESH_TOKEN**
3. Clique em **Update**
4. Cole o novo refresh_token
5. Salve

**⚠️ Importante**: O refresh_token é atualizado automaticamente toda vez que o script roda. Se você ver o aviso no log do GitHub Actions, atualize o secret manualmente.

## 📊 Como funciona

1. **Busca todas as pessoas ativas** da API MSYS Imob
2. **Aplica filtros**:
   - Remove pessoas com tipo "GUARANTOR"
   - Remove pessoas com tipo "BUYER"
   - Remove pessoas sem telefone OU sem data de aniversário
3. **Busca datas de nascimento** (em paralelo, otimizado)
4. **Filtra aniversariantes de hoje** (mesmo mês e dia)
5. **Envia via webhook** para BotConversa (um por um)

## 🔍 Ver logs

Para ver os logs de execução:

1. Vá em **Actions** no GitHub
2. Clique no workflow mais recente
3. Clique em "verificar-aniversarios"
4. Veja os logs de cada etapa

## 🛠️ Diferenças da versão local

- Usa variáveis de ambiente (secrets) em vez de arquivo `credentials.json`
- Não salva arquivos CSV/XLSX
- Não tem função de debug
- Não tem função de teste (`--teste`)
- Focado apenas em verificar e enviar aniversariantes

## 📝 Notas

- O script roda em ambiente Linux (Ubuntu)
- Python 3.11 é usado
- Dependências são instaladas automaticamente
- Logs são salvos no GitHub Actions

