import json
import os
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurações
BASE_URL = "https://www.msysimob.com.br/msys-imob-web"
CREDENTIALS_FILE = "credentials.json"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://new-backend.botconversa.com.br/api/v1/webhooks-automation/catch/147503/g8en0hO6l4RJ/")
API_KEY_BOTCONVERSA = os.getenv("API_KEY_BOTCONVERSA", "a33c54d2-5f92-4f29-b78d-5082b7b70518")

def carregar_credentials():
    """Carrega o refresh_token do arquivo credentials.json ou variável de ambiente"""
    # Primeiro tenta variável de ambiente (GitHub Actions)
    refresh_token_env = os.getenv("REFRESH_TOKEN")
    if refresh_token_env:
        return {"refresh_token": refresh_token_env}
    
    # Se não encontrar, tenta arquivo (desenvolvimento local)
    try:
        with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print(f"Erro: Arquivo {CREDENTIALS_FILE} está vazio!")
                print(f"\nPor favor, edite o arquivo com o seguinte formato:")
                print('{\n  "refresh_token": "SEU_REFRESH_TOKEN_AQUI"\n}')
                return None
            return json.loads(content)
    except FileNotFoundError:
        print(f"Erro: Arquivo {CREDENTIALS_FILE} não encontrado!")
        print(f"\nPor favor, crie o arquivo {CREDENTIALS_FILE} com o seguinte formato:")
        print('{\n  "refresh_token": "SEU_REFRESH_TOKEN_AQUI"\n}')
        return None
    except json.JSONDecodeError as e:
        print(f"Erro: Arquivo {CREDENTIALS_FILE} com formato inválido!")
        print(f"Detalhes do erro: {e}")
        print(f"\nO arquivo deve ter o seguinte formato JSON válido:")
        print('{\n  "refresh_token": "SEU_REFRESH_TOKEN_AQUI"\n}')
        print("\nVerifique se:")
        print("- As chaves estão entre aspas duplas")
        print("- Não há vírgulas extras")
        print("- O JSON está bem formatado")
        return None

def salvar_credentials(credentials):
    """Salva o refresh_token atualizado no arquivo credentials.json ou atualiza secret"""
    # Se estiver rodando no GitHub Actions, não salva (secrets não podem ser atualizados automaticamente)
    if os.getenv("REFRESH_TOKEN"):
        print("⚠️  Rodando no GitHub Actions - refresh_token não será salvo automaticamente")
        print("⚠️  Se o refresh_token mudou, atualize manualmente o secret REFRESH_TOKEN")
        return
    
    # Se estiver rodando localmente, salva no arquivo
    try:
        with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, indent=2, ensure_ascii=False)
        print("✓ Refresh token atualizado com sucesso!")
    except Exception as e:
        print(f"Erro ao salvar credentials: {e}")

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
    """Filtra pessoas que fazem aniversário hoje (mesmo mês e dia)"""
    hoje = datetime.now()
    mes_atual = hoje.month
    dia_atual = hoje.day
    
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
    
    # Atualiza o refresh token (se não estiver no GitHub Actions)
    if not os.getenv("REFRESH_TOKEN"):
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

if __name__ == "__main__":
    main()

