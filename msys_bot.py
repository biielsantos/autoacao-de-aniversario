import json
import os
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurações
BASE_URL = "https://www.msysimob.com.br/msys-imob-web"
CREDENTIALS_FILE = "credentials.json"
PLANILHAS_DIR = "planilhas"
WEBHOOK_URL = "https://new-backend.botconversa.com.br/api/v1/webhooks-automation/catch/147503/g8en0hO6l4RJ/"
API_KEY_BOTCONVERSA = "a33c54d2-5f92-4f29-b78d-5082b7b70518"

def carregar_credentials():
    """
    Carrega o refresh_token do arquivo credentials.json ou variável de ambiente.
    Se não encontrar refresh_token mas encontrar usuário/senha, faz login inicial.
    """
    # Primeiro tenta variável de ambiente (GitHub Actions)
    refresh_token_env = os.getenv("REFRESH_TOKEN")
    if refresh_token_env:
        print("✓ Usando REFRESH_TOKEN das variáveis de ambiente")
        return {"refresh_token": refresh_token_env}
    
    # Tenta variáveis de ambiente para login inicial
    usuario_env = os.getenv("MSYS_USUARIO")
    senha_env = os.getenv("MSYS_SENHA")
    
    # Se não encontrar, tenta arquivo (desenvolvimento local)
    try:
        with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print(f"⚠️  Arquivo {CREDENTIALS_FILE} está vazio!")
                # Tenta login com variáveis de ambiente
                if usuario_env and senha_env:
                    print("🔄 Tentando login inicial com variáveis de ambiente...")
                    access_token, refresh_token = fazer_login_inicial(usuario_env, senha_env)
                    if refresh_token:
                        return {"refresh_token": refresh_token}
                return None
            
            credentials = json.loads(content)
            
            # Se tiver refresh_token, mostra que está usando
            if credentials.get("refresh_token"):
                print("✓ Usando refresh_token existente do arquivo credentials.json")
                return credentials
            
            # Se não tiver refresh_token mas tiver usuário/senha, faz login inicial
            usuario = credentials.get("usuario") or credentials.get("username") or credentials.get("login")
            senha = credentials.get("senha") or credentials.get("password")
            
            if usuario and senha:
                print("\n🔄 Refresh token não encontrado, fazendo login inicial com usuário/senha...")
                print(f"   Usuário: {usuario}")
                access_token, refresh_token = fazer_login_inicial(usuario, senha)
                
                if refresh_token:
                    # Salva o refresh_token obtido para próxima vez
                    credentials["refresh_token"] = refresh_token
                    salvar_credentials(credentials)
                    print("✓ Login inicial realizado com sucesso! Refresh token salvo.")
                    return credentials
                else:
                    print("❌ Falha ao obter refresh_token do login inicial")
                    return None
            else:
                # Não tem refresh_token nem usuário/senha
                print("⚠️  Arquivo não contém refresh_token nem usuário/senha")
                print("\nFormato esperado:")
                print('{\n  "refresh_token": "SEU_REFRESH_TOKEN_AQUI"\n}')
                print("\nOu:")
                print('{\n  "usuario": "SEU_USUARIO",\n  "senha": "SUA_SENHA"\n}')
                return None
            
    except FileNotFoundError:
        print(f"⚠️  Arquivo {CREDENTIALS_FILE} não encontrado!")
        # Tenta fazer login com variáveis de ambiente se disponíveis
        if usuario_env and senha_env:
            print("🔄 Tentando login inicial com variáveis de ambiente...")
            access_token, refresh_token = fazer_login_inicial(usuario_env, senha_env)
            if refresh_token:
                # Salva no arquivo para próxima vez
                credentials = {"refresh_token": refresh_token}
                salvar_credentials(credentials)
                return credentials
        
        print(f"\nPor favor, crie o arquivo {CREDENTIALS_FILE} com um dos formatos:")
        print('\nOpção 1 (com refresh_token):')
        print('{\n  "refresh_token": "SEU_REFRESH_TOKEN_AQUI"\n}')
        print('\nOpção 2 (com usuário/senha):')
        print('{\n  "usuario": "SEU_USUARIO",\n  "senha": "SUA_SENHA"\n}')
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Erro: Arquivo {CREDENTIALS_FILE} com formato inválido!")
        print(f"Detalhes do erro: {e}")
        print("\nVerifique se:")
        print("- As chaves estão entre aspas duplas")
        print("- Não há vírgulas extras")
        print("- O JSON está bem formatado")
        return None

def salvar_credentials(credentials):
    """Salva o refresh_token atualizado no arquivo credentials.json"""
    try:
        with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, indent=2, ensure_ascii=False)
        print("✓ Refresh token atualizado com sucesso!")
    except Exception as e:
        print(f"Erro ao salvar credentials: {e}")

def fazer_login_inicial(usuario, senha):
    """
    Faz login inicial com usuário e senha para obter refresh_token.
    Tenta múltiplos formatos até encontrar o correto.
    Retorna (access_token, refresh_token) ou (None, None) em caso de erro
    """
    url = f"{BASE_URL}/api/openapi/v1/login"
    
    # Lista de formatos para tentar
    formatos = [
        # Formato 1: Parâmetros na URL com username/password
        {
            "method": "params",
            "data": {"username": usuario, "password": senha},
            "name": "Params: username/password"
        },
        # Formato 2: Parâmetros na URL com usuario/senha
        {
            "method": "params",
            "data": {"usuario": usuario, "senha": senha},
            "name": "Params: usuario/senha"
        },
        # Formato 3: Body JSON com username/password
        {
            "method": "json",
            "data": {"username": usuario, "password": senha},
            "name": "JSON Body: username/password"
        },
        # Formato 4: Body JSON com usuario/senha
        {
            "method": "json",
            "data": {"usuario": usuario, "senha": senha},
            "name": "JSON Body: usuario/senha"
        },
        # Formato 5: Body JSON com login/password
        {
            "method": "json",
            "data": {"login": usuario, "password": senha},
            "name": "JSON Body: login/password"
        },
    ]
    
    for formato in formatos:
        try:
            print(f"  Tentando: {formato['name']}...")
            
            if formato["method"] == "params":
                response = requests.post(url, params=formato["data"], timeout=10)
            else:  # json
                headers = {"Content-Type": "application/json"}
                response = requests.post(url, json=formato["data"], headers=headers, timeout=10)
            
            # Mostra detalhes da resposta
            print(f"     Status Code: {response.status_code}")
            print(f"     Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"     Resposta (primeiros 200 chars): {response.text[:200]}")
            
            # Verifica se obteve sucesso
            if response.status_code in [200, 201]:
                # Tenta fazer parse do JSON apenas se houver conteúdo
                if not response.text or response.text.strip() == "":
                    print(f"  ✗ Status {response.status_code} mas resposta vazia")
                    continue
                
                try:
                    data = response.json()
                except json.JSONDecodeError as json_err:
                    print(f"  ✗ Erro ao fazer parse do JSON: {json_err}")
                    print(f"     Resposta completa: {response.text[:500]}")
                    continue
                
                # Tenta extrair tokens com diferentes nomes de campos
                access_token = (
                    data.get("accesstoken") or 
                    data.get("access_token") or 
                    data.get("accessToken") or
                    data.get("token")
                )
                
                refresh_token = (
                    data.get("refreshtoken") or 
                    data.get("refresh_token") or 
                    data.get("refreshToken")
                )
                
                if access_token and refresh_token:
                    print(f"  ✓ Sucesso com: {formato['name']}")
                    return access_token, refresh_token
                else:
                    print(f"  ⚠️  Status 200 mas tokens não encontrados na resposta")
                    print(f"     Campos disponíveis: {list(data.keys())}")
            else:
                print(f"  ✗ Status {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"  ✗ Erro: Timeout - O servidor não respondeu em 10 segundos")
            continue
        except requests.exceptions.ConnectionError as e:
            print(f"  ✗ Erro de conexão: {str(e)[:100]}")
            continue
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Erro na requisição: {str(e)[:100]}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"     Status Code: {e.response.status_code}")
                print(f"     Resposta: {e.response.text[:200]}")
            continue
        except Exception as e:
            print(f"  ✗ Erro inesperado: {str(e)[:100]}")
            import traceback
            print(f"     Traceback: {traceback.format_exc()[:300]}")
            continue
    
    print("\n❌ Todos os formatos falharam. Verifique:")
    print("   - Usuário e senha estão corretos?")
    print("   - A API aceita login com usuário/senha?")
    print("   - Consulte a documentação da API do MSYS")
    return None, None

def testar_login():
    """Função para testar o login inicial com usuário/senha"""
    print("=" * 50)
    print("TESTE: Login inicial com usuário/senha")
    print("=" * 50)
    
    # Tenta carregar do arquivo credentials.json
    try:
        with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print(f"❌ Arquivo {CREDENTIALS_FILE} está vazio!")
                print("\nPor favor, adicione usuário e senha:")
                print('{\n  "usuario": "SEU_USUARIO",\n  "senha": "SUA_SENHA"\n}')
                return
            
            credentials = json.loads(content)
            usuario = credentials.get("usuario") or credentials.get("username") or credentials.get("login")
            senha = credentials.get("senha") or credentials.get("password")
            
            if not usuario or not senha:
                print("❌ Usuário ou senha não encontrados no credentials.json!")
                print("\nFormato esperado:")
                print('{\n  "usuario": "SEU_USUARIO",\n  "senha": "SUA_SENHA"\n}')
                return
            
            print(f"\n📋 Credenciais encontradas:")
            print(f"   Usuário: {usuario}")
            print(f"   Senha: {'*' * len(senha)}")
            
            print(f"\n🔄 Tentando fazer login inicial...\n")
            access_token, refresh_token = fazer_login_inicial(usuario, senha)
            
            if access_token and refresh_token:
                print(f"\n" + "=" * 50)
                print("✓ LOGIN BEM-SUCEDIDO!")
                print("=" * 50)
                print(f"\n📝 Tokens obtidos:")
                print(f"   Access Token: {access_token[:20]}...")
                print(f"   Refresh Token: {refresh_token[:20]}...")
                
                # Salva o refresh_token
                credentials["refresh_token"] = refresh_token
                salvar_credentials(credentials)
                print(f"\n✓ Refresh token salvo em {CREDENTIALS_FILE}")
                print(f"  Na próxima execução, o script usará o refresh_token automaticamente")
            else:
                print(f"\n" + "=" * 50)
                print("❌ LOGIN FALHOU")
                print("=" * 50)
                
    except FileNotFoundError:
        print(f"❌ Arquivo {CREDENTIALS_FILE} não encontrado!")
        print("\nPor favor, crie o arquivo com:")
        print('{\n  "usuario": "SEU_USUARIO",\n  "senha": "SUA_SENHA"\n}')
    except json.JSONDecodeError as e:
        print(f"❌ Erro: Arquivo {CREDENTIALS_FILE} com formato inválido!")
        print(f"Detalhes: {e}")

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

def extrair_email(contact_vos):
    """Extrai o email principal dos contatos"""
    if not contact_vos:
        return ""
    
    for contact in contact_vos:
        email_vos = contact.get("emailVOs", [])
        if email_vos:
            # Procura email principal (flgMain = 1)
            for email_vo in email_vos:
                if email_vo.get("flgMain") == 1:
                    return email_vo.get("email", "")
            # Se não encontrar principal, pega o primeiro
            if email_vos:
                return email_vos[0].get("email", "")
    
    return ""

def debug_dados_api(pessoas):
    """Função para debugar e ver a estrutura dos dados recebidos da API"""
    print("\n" + "=" * 50)
    print("DEBUG: Estrutura dos dados recebidos da API")
    print("=" * 50)
    
    if not pessoas:
        print("Nenhuma pessoa recebida!")
        return
    
    # Salva a resposta completa em JSON para análise
    debug_file = "debug_api_response.json"
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(pessoas, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Resposta completa salva em: {debug_file}")
    
    # Analisa a primeira pessoa como exemplo
    primeira_pessoa = pessoas[0] if pessoas else {}
    print(f"\n📋 Exemplo - Primeira pessoa recebida:")
    print(f"Tipo: {type(primeira_pessoa)}")
    print(f"Chaves disponíveis: {list(primeira_pessoa.keys()) if isinstance(primeira_pessoa, dict) else 'N/A'}")
    
    # Mostra estrutura detalhada
    if isinstance(primeira_pessoa, dict):
        print("\n🔍 Estrutura detalhada:")
        for key, value in primeira_pessoa.items():
            tipo = type(value).__name__
            if isinstance(value, dict):
                print(f"  {key}: dict com chaves: {list(value.keys())[:5]}...")
            elif isinstance(value, list):
                print(f"  {key}: list com {len(value)} itens")
                if value and isinstance(value[0], dict):
                    print(f"    Primeiro item tem chaves: {list(value[0].keys())[:5]}...")
            else:
                valor_str = str(value)[:50] if value else "None/vazio"
                print(f"  {key}: {tipo} = {valor_str}")
    
    # Verifica campos específicos que estamos procurando
    print("\n🔎 Verificando campos específicos:")
    print(f"  namPerson: {primeira_pessoa.get('namPerson', 'NÃO ENCONTRADO')}")
    print(f"  personType: {primeira_pessoa.get('personType', 'NÃO ENCONTRADO')}")
    print(f"  contactVOs: {type(primeira_pessoa.get('contactVOs', None)).__name__}")
    
    person_individual = primeira_pessoa.get('personIndividualForm')
    if person_individual:
        print(f"  personIndividualForm: {type(person_individual).__name__}")
        if isinstance(person_individual, dict):
            print(f"    Chaves: {list(person_individual.keys())}")
            print(f"    birth: {person_individual.get('birth', 'NÃO ENCONTRADO')}")
    else:
        print(f"  personIndividualForm: NÃO ENCONTRADO")
    
    contact_vos = primeira_pessoa.get('contactVOs')
    if contact_vos:
        print(f"  contactVOs tipo: {type(contact_vos).__name__}")
        if isinstance(contact_vos, list) and contact_vos:
            primeiro_contact = contact_vos[0]
            print(f"    Primeiro contato tipo: {type(primeiro_contact).__name__}")
            if isinstance(primeiro_contact, dict):
                print(f"    Chaves do contato: {list(primeiro_contact.keys())}")
                phone_vos = primeiro_contact.get('phoneVOs')
                print(f"    phoneVOs: {type(phone_vos).__name__ if phone_vos else 'None/vazio'}")
    
    print("\n" + "=" * 50)
    print("Fim do DEBUG")
    print("=" * 50 + "\n")

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
            
    except requests.exceptions.RequestException as e:
        # Silencia erros individuais para não poluir o output
        return None
    except Exception as e:
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
        
        # DEBUG: Primeira pessoa
        if idx == 0:
            print(f"\n🔍 DEBUG - Primeira pessoa:")
            print(f"  Nome: {nome}")
            print(f"  contactVOs tipo: {type(contact_vos)}")
            print(f"  contactVOs valor: {contact_vos}")
        
        # Garante que contact_vos é um dict (não lista!)
        if not isinstance(contact_vos, dict):
            contact_vos = None
            
        telefone = extrair_telefone(contact_vos)
        
        # DEBUG: Primeira pessoa
        if idx == 0:
            print(f"  Telefone extraído: '{telefone}'")
        
        # Tipo de pessoa: usa firstType ou typesSeparate se personType for null
        tipo_pessoa = pessoa.get("personType")
        if not tipo_pessoa:
            tipo_pessoa = pessoa.get("firstType", "")
            if not tipo_pessoa:
                tipo_pessoa = pessoa.get("typesSeparate", "")
        
        # DEBUG: Primeira pessoa
        if idx == 0:
            print(f"  personType: {pessoa.get('personType')}")
            print(f"  firstType: {pessoa.get('firstType')}")
            print(f"  typesSeparate: {pessoa.get('typesSeparate')}")
            print(f"  Tipo de pessoa extraído: '{tipo_pessoa}'")
        
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
        
        # DEBUG: Primeira pessoa
        if pessoa_dados == pessoas_preparadas[0] if pessoas_preparadas else False:
            print(f"\n🔍 DEBUG - Primeira pessoa após processamento:")
            print(f"  Nome: {nome}")
            print(f"  Telefone: {telefone}")
            print(f"  Tipo: {tipo_pessoa}")
            print(f"  Data: {data_nascimento}")
        
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

def testar_webhook():
    """Função para testar o webhook com dados específicos"""
    print("=" * 50)
    print("TESTE: Enviando webhook")
    print("=" * 50)
    
    nome = "Gabriel"
    telefone_original = "55(44)997355407"
    
    # Formata o telefone para padrão BotConversa: +5511912341234
    telefone_formatado = formatar_telefone_botconversa(telefone_original)
    
    webhook_url = WEBHOOK_URL
    api_key = API_KEY_BOTCONVERSA
    
    payload = {
        "nome": nome,
        "telefone": telefone_formatado
    }
    
    headers = {
        "Content-Type": "application/json",
        "apikey": api_key
    }
    
    print(f"\n📤 Enviando dados de teste para webhook:")
    print(f"  Nome: {nome}")
    print(f"  Telefone: {telefone_formatado}")
    print(f"  URL: {webhook_url}")
    
    try:
        print(f"\n⏳ Fazendo requisição...")
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        
        print(f"\n📥 Resposta recebida:")
        print(f"  Status Code: {response.status_code}")
        print(f"  Resposta: {response.text[:500]}")
        
        if response.status_code in [200, 201]:
            print(f"\n✓ Teste enviado com sucesso! Status: {response.status_code}")
        else:
            print(f"\n✗ Falha no teste! Status: {response.status_code}")
            print(f"  Resposta completa: {response.text}")
    except requests.exceptions.Timeout:
        print(f"\n✗ Erro: Timeout - O servidor não respondeu em 10 segundos")
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ Erro de conexão: {e}")
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Erro ao enviar: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Status Code: {e.response.status_code}")
            print(f"  Resposta: {e.response.text[:500]}")
    except Exception as e:
        print(f"\n✗ Erro inesperado: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")

def main():
    """Função principal"""
    print("=" * 50)
    print("MSYS Imob - Extrator de Pessoas com Aniversários")
    print("=" * 50)
    
    # 1. Carrega credentials
    print("\n[1/4] Carregando credentials...")
    credentials = carregar_credentials()
    if not credentials:
        return
    
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        print("Erro: refresh_token não encontrado no credentials.json!")
        return
    
    # 2. Obtém access token
    print("\n[2/4] Obtendo access token...")
    access_token, new_refresh_token = obter_access_token(refresh_token)
    if not access_token:
        return
    
    # Atualiza o refresh token
    credentials["refresh_token"] = new_refresh_token
    salvar_credentials(credentials)
    
    # 3. Busca pessoas ativas
    print("\n[3/4] Buscando pessoas ativas...")
    pessoas = buscar_pessoas(access_token)
    if not pessoas:
        print("Nenhuma pessoa encontrada!")
        return
    
    print(f"✓ Total de pessoas encontradas: {len(pessoas)}")
    
    # DEBUG: Ver estrutura dos dados
    debug_dados_api(pessoas)
    
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

if __name__ == "__main__":
    import sys
    
    # Se passar --teste-login como argumento, executa apenas o teste do login
    if len(sys.argv) > 1 and sys.argv[1] == "--teste-login":
        testar_login()
    # Se passar --teste como argumento, executa apenas o teste do webhook
    elif len(sys.argv) > 1 and sys.argv[1] == "--teste":
        testar_webhook()
    else:
        main()


