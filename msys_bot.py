import json
import os
import base64
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client, Client

# Configurações
BASE_URL = "https://www.msysimob.com.br/msys-imob-web"
CREDENTIALS_FILE = "credentials.json"  # Mantido para compatibilidade, mas não será usado
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://new-backend.botconversa.com.br/api/v1/webhooks-automation/catch/147503/g8en0hO6l4RJ/")
API_KEY_BOTCONVERSA = os.getenv("API_KEY_BOTCONVERSA", "a33c54d2-5f92-4f29-b78d-5082b7b70518")

# Configurações Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rzkskovdlaktqidqeamp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ6a3Nrb3ZkbGFrdHFpZHFlYW1wIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2ODA4MzE3NCwiZXhwIjoyMDgzNjU5MTc0fQ.DJlNkDbT-0rYDm0RttPp-fe4lXMJFNFNfCxHe_xkCqo")

def get_supabase_client() -> Client:
    """Cria e retorna cliente Supabase"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_credentials():
    """Carrega o refresh_token do Supabase"""
    try:
        supabase = get_supabase_client()
        
        # Busca o primeiro registro da tabela credentials
        response = supabase.table("credentials").select("*").limit(1).execute()
        
        if response.data and len(response.data) > 0:
            refresh_token = response.data[0].get("refresh_token")
            if refresh_token:
                print(f"✓ Token carregado do Supabase")
                return {"refresh_token": refresh_token}
        
        print("⚠️  Nenhum refresh_token encontrado no Supabase!")
        print("   Por favor, insira um token inicial na tabela 'credentials'")
        return None
        
    except Exception as e:
        print(f"❌ Erro ao carregar token do Supabase: {e}")
        import traceback
        print(traceback.format_exc())
        return None

def atualizar_refresh_token_no_codigo(novo_token):
    """Atualiza o refresh_token no Supabase"""
    try:
        supabase = get_supabase_client()
        
        # Verifica se já existe registro
        response = supabase.table("credentials").select("id").limit(1).execute()
        
        if response.data and len(response.data) > 0:
            # Atualiza o registro existente
            record_id = response.data[0]["id"]
            supabase.table("credentials").update({
                "refresh_token": novo_token,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", record_id).execute()
            
            print(f"✓ Refresh token atualizado no Supabase (id: {record_id})")
        else:
            # Cria novo registro se não existir
            supabase.table("credentials").insert({
                "refresh_token": novo_token,
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            
            print(f"✓ Novo refresh token criado no Supabase")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao atualizar token no Supabase: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def atualizar_github_secret(secret_name, secret_value):
    """Atualiza um secret do GitHub usando a API"""
    try:
        from nacl import encoding, public
    except ImportError:
        print("⚠️  PyNaCl não instalado. Instale com: pip install PyNaCl")
        return False
    
    # Obtém informações do repositório e token do GitHub Actions
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")  # formato: owner/repo
    github_api_url = os.getenv("GITHUB_API_URL", "https://api.github.com")
    
    if not github_token or not github_repo:
        print("⚠️  GITHUB_TOKEN ou GITHUB_REPOSITORY não encontrado")
        return False
    
    try:
        # Passo 1: Obter a chave pública do repositório
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Obtém a chave pública do repositório
        public_key_url = f"{github_api_url}/repos/{github_repo}/actions/secrets/public-key"
        response = requests.get(public_key_url, headers=headers)
        response.raise_for_status()
        
        public_key_data = response.json()
        key_id = public_key_data["key_id"]
        public_key = public_key_data["key"]
        
        # Passo 2: Criptografar o valor do secret usando a chave pública
        public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key_obj)
        encrypted_value = sealed_box.encrypt(secret_value.encode("utf-8"))
        encrypted_value_b64 = base64.b64encode(encrypted_value).decode("utf-8")
        
        # Passo 3: Atualizar o secret
        update_url = f"{github_api_url}/repos/{github_repo}/actions/secrets/{secret_name}"
        payload = {
            "encrypted_value": encrypted_value_b64,
            "key_id": key_id
        }
        
        response = requests.put(update_url, json=payload, headers=headers)
        response.raise_for_status()
        
        return True
    except Exception as e:
        print(f"Erro ao atualizar secret do GitHub: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Resposta da API: {e.response.text}")
        return False

def salvar_credentials(credentials):
    """Salva o refresh_token atualizado no Supabase"""
    new_refresh_token = credentials.get("refresh_token")
    
    if not new_refresh_token:
        return
    
    print("\n🔄 Atualizando refresh_token no Supabase...")
    
    # Atualiza no Supabase
    if atualizar_refresh_token_no_codigo(new_refresh_token):
        print("✓ Refresh token atualizado no Supabase com sucesso!")
        print("💡 O novo refresh_token foi salvo no Supabase")
        print("   Na próxima execução, o novo token será usado automaticamente")
    else:
        print("❌ Falha ao atualizar refresh_token no Supabase")
        print(f"⚠️  Novo token: {new_refresh_token[:20]}...")
        print("⚠️  Verifique a conexão com o Supabase")

def renovar_refresh_token():
    """Renova apenas o refresh_token sem executar o resto do processo"""
    print("=" * 50)
    print("Renovação de Refresh Token")
    print("=" * 50)
    
    # 1. Carrega credentials
    print("\n[1/2] Carregando credentials...")
    credentials = carregar_credentials()
    if not credentials:
        return False
    
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        print("Erro: refresh_token não encontrado!")
        return False
    
    # 2. Obtém novo access token (e novo refresh_token)
    print("\n[2/2] Obtendo novo refresh_token...")
    access_token, new_refresh_token = obter_access_token(refresh_token)
    if not access_token or not new_refresh_token:
        print("❌ Falha ao renovar refresh_token!")
        return False
    
    print("✓ Novo refresh_token obtido com sucesso!")
    
    # 3. Atualiza o refresh_token no código
    credentials["refresh_token"] = new_refresh_token
    salvar_credentials(credentials)
    
    print("\n" + "=" * 50)
    print("Renovação concluída com sucesso!")
    print("=" * 50)
    return True

def obter_access_token(refresh_token):
    """Obtém um novo access token usando o refresh token"""
    url = f"{BASE_URL}/api/openapi/v1/login"
    params = {"refresh-token": refresh_token}
    
    try:
        response = requests.post(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        access_token = data.get("accesstoken")
        new_refresh_token = data.get("refreshtoken")
        
        if not access_token or not new_refresh_token:
            raise ValueError("Resposta da API não contém tokens válidos")
        
        return access_token, new_refresh_token
    except requests.exceptions.RequestException as e:
        print(f"Erro ao obter access token: {e}")
        if hasattr(e.response, 'text'):
            print(f"Resposta do servidor: {e.response.text}")
        return None, None

def buscar_pessoas(access_token, page_size=100, limite=None):
    """Busca pessoas ativas com paginação"""
    url = f"{BASE_URL}/api/openapi/v1/person"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    todas_pessoas = []
    first = 0
    
    while True:
        payload = {
            "indStatus": "A",  # Apenas ativos
            "pageSize": page_size,
            "first": first
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                break
            
            todas_pessoas.extend(items)
            print(f"✓ Página processada: {len(items)} pessoas (Total: {len(todas_pessoas)})")
            
            # Se há limite e já atingiu, para
            if limite and len(todas_pessoas) >= limite:
                todas_pessoas = todas_pessoas[:limite]
                break
            
            # Verifica se há mais páginas
            total_items = data.get("totalItens", 0)
            if len(todas_pessoas) >= total_items:
                break
            
            first += page_size
            
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar pessoas: {e}")
            if hasattr(e.response, 'text'):
                print(f"Resposta do servidor: {e.response.text}")
            break
    
    return todas_pessoas

def extrair_telefone(contact_vos):
    """Extrai o telefone principal dos contatos"""
    if not contact_vos:
        return ""
    
    # contactVOs é um objeto/dict, não uma lista!
    if not isinstance(contact_vos, dict):
        return ""
    
    # Acessa phoneVOs diretamente do objeto contactVOs
    phone_vos = contact_vos.get("phoneVOs", [])
    if phone_vos and isinstance(phone_vos, list) and len(phone_vos) > 0:
        phone = phone_vos[0]  # Pega o primeiro telefone
        if isinstance(phone, dict):
            ddd = phone.get("dddPhone", "")
            num = phone.get("numPhone", "")
            if ddd and num:
                return f"({ddd}) {num}"
    
    return ""

def buscar_data_nascimento(access_token, idt_person):
    """Busca a data de nascimento de uma pessoa usando o endpoint findForEdit"""
    url = f"{BASE_URL}/api/openapi/v1/person/findForEdit"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, params={"code": idt_person}, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Tenta encontrar a data de nascimento em vários lugares
        # Pode estar em personIndividualForm.birth ou personIndividual.birth
        person_individual_form = data.get("personIndividualForm")
        if person_individual_form and isinstance(person_individual_form, dict):
            birth = person_individual_form.get("birth")
            if birth:
                try:
                    if isinstance(birth, (int, float)):
                        return datetime.fromtimestamp(birth / 1000).strftime("%Y-%m-%d")
                    else:
                        return str(birth).split('T')[0]
                except:
                    return str(birth)
        
        person_individual = data.get("personIndividual")
        if person_individual and isinstance(person_individual, dict):
            birth = person_individual.get("birth")
            if birth:
                try:
                    if isinstance(birth, (int, float)):
                        return datetime.fromtimestamp(birth / 1000).strftime("%Y-%m-%d")
                    else:
                        return str(birth).split('T')[0]
                except:
                    return str(birth)
        
        # Tenta dtaBirth
        dta_birth = data.get("dtaBirth")
        if dta_birth:
            try:
                if isinstance(dta_birth, (int, float)):
                    return datetime.fromtimestamp(dta_birth / 1000).strftime("%Y-%m-%d")
                else:
                    return str(dta_birth).split('T')[0]
            except:
                return str(dta_birth)
            
    except requests.exceptions.RequestException:
        # Silencia erros individuais para não poluir o output
        return None
    except Exception:
        return None
    
    return None

def processar_pessoas(pessoas, access_token=None, buscar_datas_nascimento=False):
    """Processa todas as pessoas e extrai dados relevantes com otimização paralela"""
    pessoas_processadas = []
    total = len(pessoas)
    
    # FASE 1: Processa dados locais e identifica quem precisa buscar data
    pessoas_preparadas = []
    pessoas_para_buscar = []  # Lista de (índice, idt_person) para buscar datas
    
    for idx, pessoa in enumerate(pessoas):
        # Verifica se pessoa é um dicionário
        if not isinstance(pessoa, dict):
            continue
            
        # Extrai dados da pessoa
        nome = pessoa.get("namPerson", "")
        idt_person = pessoa.get("idtPerson")
        contact_vos = pessoa.get("contactVOs")
        
        # Garante que contact_vos é um dict (não lista!)
        if not isinstance(contact_vos, dict):
            contact_vos = None
            
        telefone = extrair_telefone(contact_vos)
        
        # Tipo de pessoa: usa firstType ou typesSeparate se personType for null
        tipo_pessoa = pessoa.get("personType")
        if not tipo_pessoa:
            tipo_pessoa = pessoa.get("firstType", "")
            if not tipo_pessoa:
                tipo_pessoa = pessoa.get("typesSeparate", "")
        
        # Extrai data de nascimento dos campos locais
        data_nascimento = ""
        
        # Primeiro tenta os campos locais
        dta_birth = pessoa.get("dtaBirth")
        if dta_birth:
            try:
                if isinstance(dta_birth, (int, float)):
                    data_nascimento = datetime.fromtimestamp(dta_birth / 1000).strftime("%Y-%m-%d")
                else:
                    data_nascimento = str(dta_birth).split('T')[0]
            except:
                data_nascimento = str(dta_birth)
        
        # Se não encontrou nos campos locais
        if not data_nascimento:
            person_individual = pessoa.get("personIndividualForm")
            if person_individual and isinstance(person_individual, dict):
                birth_str = person_individual.get("birth")
                if birth_str:
                    try:
                        data_nascimento = birth_str.split('T')[0]
                    except:
                        data_nascimento = str(birth_str)
        
        if not data_nascimento:
            person_individual = pessoa.get("personIndividual")
            if person_individual and isinstance(person_individual, dict):
                birth_str = person_individual.get("birth")
                if birth_str:
                    try:
                        data_nascimento = birth_str.split('T')[0]
                    except:
                        data_nascimento = str(birth_str)
        
        # Prepara dados da pessoa
        pessoa_dados = {
            "nome": nome,
            "telefone": telefone,
            "tipo_pessoa": tipo_pessoa,
            "data_nascimento": data_nascimento,
            "idt_person": idt_person
        }
        
        # Se precisa buscar data e tem condições, adiciona à lista para buscar em paralelo
        if not data_nascimento and buscar_datas_nascimento and access_token and idt_person:
            pessoas_para_buscar.append((len(pessoas_preparadas), idt_person))
        
        pessoas_preparadas.append(pessoa_dados)
    
    # FASE 2: Busca datas em paralelo (se necessário)
    if pessoas_para_buscar and access_token:
        print(f"\n📡 Buscando datas de nascimento para {len(pessoas_para_buscar)} pessoas em paralelo...")
        
        # Dicionário para armazenar resultados: índice -> data
        resultados_datas = {}
        
        # Usa ThreadPoolExecutor para fazer requisições em paralelo
        # max_workers=15 significa 15 requisições simultâneas
        with ThreadPoolExecutor(max_workers=15) as executor:
            # Submete todas as tarefas
            future_to_idx = {
                executor.submit(buscar_data_nascimento, access_token, idt_person): idx
                for idx, idt_person in pessoas_para_buscar
            }
            
            # Processa resultados conforme vão completando
            completadas = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                completadas += 1
                try:
                    data_encontrada = future.result()
                    if data_encontrada:
                        resultados_datas[idx] = data_encontrada
                except Exception:
                    # Ignora erros individuais
                    pass
                
                # Mostra progresso a cada 50 requisições completadas
                if completadas % 50 == 0:
                    print(f"  Progresso: {completadas}/{len(pessoas_para_buscar)} datas buscadas...")
        
        # Atualiza as datas encontradas
        for idx, data_encontrada in resultados_datas.items():
            pessoas_preparadas[idx]["data_nascimento"] = data_encontrada
        
        print(f"✓ Busca de datas concluída!")
    
    # FASE 3: Aplica filtros e gera lista final
    for pessoa_dados in pessoas_preparadas:
        nome = pessoa_dados["nome"]
        telefone = pessoa_dados["telefone"]
        tipo_pessoa = pessoa_dados["tipo_pessoa"]
        data_nascimento = pessoa_dados["data_nascimento"]
        
        # FILTRO 1: Pula pessoas com tipo "GUARANTOR"
        if tipo_pessoa and "GUARANTOR" in str(tipo_pessoa).upper():
            continue
        
        # FILTRO 2: Pula pessoas com tipo "BUYER"
        if tipo_pessoa and "BUYER" in str(tipo_pessoa).upper():
            continue
        
        # FILTRO 3: Pula pessoas que não têm telefone OU não têm data de aniversário
        # Precisa ter AMBOS para ser incluída
        telefone_vazio = not telefone or telefone.strip() == ""
        data_vazia = not data_nascimento or data_nascimento.strip() == ""
        
        if telefone_vazio or data_vazia:
            continue
        
        pessoas_processadas.append({
            "Nome": nome,
            "Data de Aniversário": data_nascimento,
            "Telefone": telefone,
            "Tipo de Pessoa": tipo_pessoa
        })
    
    return pessoas_processadas

def filtrar_aniversariantes_hoje(pessoas_processadas):
    """Filtra pessoas que fazem aniversário hoje (mesmo mês e dia) - usando timezone de Brasília"""
    from datetime import timezone, timedelta
    
    # Define timezone de Brasília (UTC-3)
    brasilia_tz = timezone(timedelta(hours=-3))
    
    # Pega a data atual no timezone de Brasília
    hoje = datetime.now(brasilia_tz)
    mes_atual = hoje.month
    dia_atual = hoje.day
    
    # Debug: mostra a data sendo usada
    print(f"📅 Verificando aniversariantes de: {dia_atual:02d}/{mes_atual:02d} (timezone Brasília)")
    
    aniversariantes = []
    
    for pessoa in pessoas_processadas:
        data_aniversario = pessoa.get("Data de Aniversário", "")
        
        if not data_aniversario or data_aniversario.strip() == "":
            continue
        
        try:
            # Tenta fazer parse da data (pode estar no formato YYYY-MM-DD)
            if "-" in data_aniversario:
                partes = data_aniversario.split("-")
                if len(partes) >= 3:
                    ano_aniversario = int(partes[0])
                    mes_aniversario = int(partes[1])
                    dia_aniversario = int(partes[2])
                    
                    if mes_aniversario == mes_atual and dia_aniversario == dia_atual:
                        aniversariantes.append({
                            "nome": pessoa.get("Nome", ""),
                            "telefone": pessoa.get("Telefone", "")
                        })
        except (ValueError, IndexError):
            # Se não conseguir fazer parse, ignora essa pessoa
            continue
    
    return aniversariantes

def formatar_telefone_botconversa(telefone):
    """
    Formata telefone para o padrão BotConversa: +5511912341234
    Formato: +55 + DDD + 9 + TELEFONE (total 13 dígitos após o +)
    """
    # Remove caracteres não numéricos
    telefone_limpo = "".join(filter(str.isdigit, telefone))
    
    # Garante que comece com 55 (DDI do Brasil)
    if not telefone_limpo.startswith('55'):
        telefone_limpo = '55' + telefone_limpo
    
    # Adiciona o + no início
    telefone_formatado = '+' + telefone_limpo
    
    return telefone_formatado

def enviar_webhook(nome, telefone, webhook_url, api_key):
    """Envia dados para webhook do BotConversa"""
    try:
        # Formata o telefone para padrão BotConversa: +5511912341234
        telefone_formatado = formatar_telefone_botconversa(telefone)
        
        payload = {
            "nome": nome,
            "telefone": telefone_formatado
        }
        
        headers = {
            "Content-Type": "application/json",
            "apikey": api_key
        }
        
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            return True
        else:
            print(f"  Status code: {response.status_code} - Resposta: {response.text[:100]}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  Erro ao enviar webhook para {nome}: {e}")
        return False
    except Exception as e:
        print(f"  Erro inesperado ao enviar webhook para {nome}: {e}")
        return False

def enviar_aniversariantes_webhook(aniversariantes, webhook_url, api_key):
    """Envia todos os aniversariantes via webhook (um por um)"""
    if not aniversariantes:
        print("\n📅 Nenhum aniversariante encontrado para hoje!")
        return
    
    print(f"\n🎂 Encontrados {len(aniversariantes)} aniversariante(s) hoje!")
    print(f"📤 Enviando para BotConversa (um por um)...")
    
    sucesso = 0
    falhas = 0
    
    for aniversariante in aniversariantes:
        nome = aniversariante.get("nome", "")
        telefone_original = aniversariante.get("telefone", "")
        telefone_formatado = formatar_telefone_botconversa(telefone_original)
        
        print(f"  Enviando: {nome} - {telefone_formatado}")
        
        if enviar_webhook(nome, telefone_original, webhook_url, api_key):
            sucesso += 1
            print(f"    ✓ Enviado com sucesso!")
        else:
            falhas += 1
            print(f"    ✗ Falha no envio")
    
    print(f"\n✓ Webhooks enviados: {sucesso} sucesso, {falhas} falhas")

def main():
    """Função principal"""
    print("=" * 50)
    print("MSYS Imob - Verificador de Aniversários")
    print("=" * 50)
    
    # 1. Carrega credentials
    print("\n[1/4] Carregando credentials...")
    credentials = carregar_credentials()
    if not credentials:
        return
    
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        print("Erro: refresh_token não encontrado!")
        return
    
    # 2. Obtém access token
    print("\n[2/4] Obtendo access token...")
    access_token, new_refresh_token = obter_access_token(refresh_token)
    if not access_token:
        return
    
    print("✓ Access token obtido com sucesso!")
    
    # Atualiza o refresh token (automaticamente no GitHub Actions ou localmente)
    credentials["refresh_token"] = new_refresh_token
    salvar_credentials(credentials)
    
    # 3. Busca pessoas ativas
    print("\n[3/4] Buscando pessoas ativas...")
    pessoas = buscar_pessoas(access_token)
    if not pessoas:
        print("Nenhuma pessoa encontrada!")
        return
    
    print(f"✓ Total de pessoas encontradas: {len(pessoas)}")
    
    # 4. Processa todas as pessoas
    print("\n[4/4] Processando dados das pessoas...")
    print("⚠️  Buscando datas de nascimento (pode demorar alguns minutos)...")
    pessoas_processadas = processar_pessoas(pessoas, access_token=access_token, buscar_datas_nascimento=True)
    
    # 5. Filtra e envia aniversariantes de hoje via webhook
    print("\n[5/5] Verificando aniversariantes de hoje...")
    aniversariantes = filtrar_aniversariantes_hoje(pessoas_processadas)
    enviar_aniversariantes_webhook(aniversariantes, WEBHOOK_URL, API_KEY_BOTCONVERSA)
    
    print("\n" + "=" * 50)
    print("Processo concluído com sucesso!")
    print("=" * 50)

def testar_atualizacao_token():
    """Função para testar a atualização automática do refresh_token"""
    print("=" * 70)
    print("TESTE: Atualização automática do refresh_token")
    print("=" * 70)
    
    # Token de teste (diferente do atual)
    token_teste = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.TESTE_TOKEN_PARA_VERIFICAR_ATUALIZACAO.AUTOMATICA"
    
    print(f"\n🔄 Testando atualização com token de teste...")
    print(f"   (Vai atualizar no Supabase)")
    
    # Simula atualização
    credentials_teste = {"refresh_token": token_teste}
    salvar_credentials(credentials_teste)
    
    print(f"\n" + "=" * 70)
    print("TESTE CONCLUÍDO")
    print("=" * 70)
    print("\n💡 Para testar no GitHub Actions:")
    print("   1. Execute o workflow manualmente")
    print("   2. O script vai atualizar o refresh_token no Supabase automaticamente")
    print("   3. Verifique os logs para confirmar a atualização")

if __name__ == "__main__":
    import sys
    
    # Se passar --renovar como argumento, apenas renova o token
    if len(sys.argv) > 1 and sys.argv[1] == "--renovar":
        renovar_refresh_token()
    # Se passar --teste-atualizar como argumento, executa o teste
    elif len(sys.argv) > 1 and sys.argv[1] == "--teste-atualizar":
        testar_atualizacao_token()
    else:
        main()
